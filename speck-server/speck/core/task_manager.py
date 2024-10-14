import asyncio
import hashlib
import importlib
import multiprocessing
import pickle
import threading
import time
import logging
import sys
from queue import Empty
from typing import Callable, Optional
from logging.handlers import QueueHandler, QueueListener
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import cache, db_engine
from core.event_manager import event_manager

# Function to configure worker logging
def configure_worker_logging(log_queue):
    queue_handler = QueueHandler(log_queue)
    logger = logging.getLogger()
    if not logger.hasHandlers():
        logger.setLevel(logging.INFO)
        logger.addHandler(queue_handler)

def get_task_key(task: Callable, args: tuple, kwargs: dict):
    """
    Generate a unique key for a task.
    """
    # Create a tuple with task function name and arguments
    task_tuple = (task.__module__, task.__name__, args, tuple(sorted(kwargs.items())))

    # Serialize and hash it
    task_bytes = pickle.dumps(task_tuple)
    task_hash = hashlib.md5(task_bytes).hexdigest()

    return task_hash

# Worker function
def worker(
        queue_name,
        task_queues,
        stop_event,
        log_queue,
        task_manager_log_file,
        pipe_conn,
        pending_tasks
    ):
    configure_worker_logging(log_queue)
    logger = logging.getLogger(f'worker-{queue_name}')

    # Initialize the task manager so workers can schedule tasks themselves
    initialize_task_manager(
        task_queues=task_queues,
        log_queue=log_queue,
        stop_event=stop_event,
        log_file=task_manager_log_file,
        pending_tasks=pending_tasks
    )

    # Identify which queue we're working
    task_queue = task_queues[queue_name]

    # Work the queue
    while not stop_event.is_set():
        try:
            # Get the task and the task_key
            task, args, kwargs = task_queue.get(timeout=1)
            task_key = get_task_key(task, args, kwargs)

            logger.info(f"Executing task {task.__name__} with args {args} and kwargs {kwargs}")
            try:
                cache.set('last_task', task.__name__)
                task(*args, **kwargs)
                logger.info(f"Task {task.__name__} completed")

                # Send a message through the pipe when the task is completed
                pipe_conn.send(task.__name__)

            except Exception as e:
                logger.error(f"Error executing task {task.__name__}: {e}", exc_info=True)
            finally:
                if task_key in pending_tasks:
                    del pending_tasks[task_key]
        except Empty:
            continue

# Scheduler function using threading
def scheduler(task_queues, stop_event, log_queue, recurring_tasks):
    configure_worker_logging(log_queue)
    logger = logging.getLogger(f'scheduler-{threading.current_thread().name}')

    # Schedule the initial next run times
    next_run_times = {task: time.time() + 5 for task, interval, args, kwargs in recurring_tasks}

    while not stop_event.is_set():
        current_time = time.time()
        for task_name, interval, args, kwargs in recurring_tasks:
            if current_time >= next_run_times[task_name]:
                module_name, function_name = task_name.rsplit('.', 1)
                module = importlib.import_module(module_name)
                task = getattr(module, function_name)

                logger.info(f"Scheduling recurring task {task.__name__}")
                queue_name = kwargs.pop('queue_name', 'general')
                task_queues[queue_name].put((task, args, kwargs))
                next_run_times[task_name] = current_time + interval

        time.sleep(1)

# Function to setup logging in the main process
def setup_main_logger(log_queue, log_file=None):
    logger = logging.getLogger()
    if not logger.hasHandlers():
        logger.setLevel(logging.INFO)

        if log_file:
            handler = logging.FileHandler(log_file)
        else:
            handler = logging.StreamHandler(sys.stdout)

        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    queue_listener = QueueListener(log_queue, *logger.handlers)
    queue_listener.start()
    return logger, queue_listener

class TaskManager:
    def __init__(
            self,
            log_file: Optional[str] = None,
            recurring_tasks: Optional[list] = None,
            task_queues=None,
            log_queue=None,
            pending_tasks=None,
            stop_event=None
        ):
        self.task_queues = task_queues if task_queues is not None else {
            'general': multiprocessing.Queue(),
            'completion': multiprocessing.Queue(),
            'embedding': multiprocessing.Queue()
        }
        self.workers = []

        self.recurring_tasks = recurring_tasks if recurring_tasks is not None else []
        self.scheduler_thread = None

        self._stop_event = stop_event if stop_event is not None else multiprocessing.Event()
        self.log_queue = log_queue if log_queue is not None else multiprocessing.Queue()
        self.log_file = log_file
        self.logger, self.queue_listener = setup_main_logger(self.log_queue, self.log_file)

        # Create pipes for each worker
        self.parent_conns = {}
        self.child_conns = {}

        # Create a Manager and a shared dict for pending tasks
        if pending_tasks is None:
            self.manager = multiprocessing.Manager()
            self.pending_tasks = self.manager.dict()
        else:
            self.pending_tasks = pending_tasks

    def add_task(self, task: Callable, queue_name: str = 'general', *args, **kwargs):
        """
        Add a task to a queue. Checks if the task is already pending before adding it.
        """
        # Get a unique key for the task and check if it's already pending
        task_key = get_task_key(task, args, kwargs)
        if task_key in self.pending_tasks:
            self.logger.info(f"Task {task.__name__} with args {args} and kwargs {kwargs} is already pending, ignoring.")
            return

        # Add the task to the pending tasks dict and the queu
        self.logger.info(f"Adding task {task.__name__} to {queue_name} queue")
        self.pending_tasks[task_key] = True
        self.task_queues[queue_name].put((task, args, kwargs))

    def start(self):
        self.logger.info("Starting workers for each queue")
        for queue_name in self.task_queues.keys():
            parent_conn, child_conn = multiprocessing.Pipe()
            self.parent_conns[queue_name] = parent_conn
            self.child_conns[queue_name] = child_conn
            process = multiprocessing.Process(
                target=worker,
                args=(
                    queue_name,
                    self.task_queues,
                    self._stop_event,
                    self.log_queue,
                    self.log_file,
                    child_conn,
                    self.pending_tasks
                )
            )
            process.start()
            self.workers.append(process)

        # Start the scheduler thread
        scheduler_thread = threading.Thread(
            target=scheduler,
            args=(self.task_queues, self._stop_event, self.log_queue, self.recurring_tasks)
        )
        scheduler_thread.start()
        self.scheduler_thread = scheduler_thread

        # Start the pipe watcher thread
        watcher_thread = threading.Thread(target=self.watch_pipes)
        watcher_thread.start()
        self.watcher_thread = watcher_thread

    def stop(self):
        self.logger.info("Stopping all workers")
        self._stop_event.set()

        # Stop the scheduler thread
        if self.scheduler_thread:
            self.scheduler_thread.join()

        # Stop the watcher thread
        if self.watcher_thread:
            self.watcher_thread.join()

        # Stop all workers
        for worker in self.workers:
            if isinstance(worker, multiprocessing.Process):
                worker.terminate()
                worker.join()

    def watch_pipes(self):
        while not self._stop_event.is_set():
            for queue_name, parent_conn in self.parent_conns.items():
                if parent_conn.poll(1):
                    task_name = parent_conn.recv()

                    if task_name in ("process_inbox_thread", "execute_function_for_message"):
                        from emails.models import Mailbox
                        with Session(db_engine) as session:
                            mailbox = session.execute(select(Mailbox)).scalar_one()
                            asyncio.run(event_manager.broadcast({
                                "type": "mailbox",
                                "payload": mailbox.get_state()
                            }))
            time.sleep(0.1)

task_manager = None

def initialize_task_manager(
        log_file: Optional[str] = None,
        recurring_tasks: Optional[list] = None,
        task_queues=None,
        log_queue=None,
        pending_tasks=None,
        stop_event=None
    ):
    global task_manager
    task_manager = TaskManager(
        log_file=log_file,
        recurring_tasks=recurring_tasks,
        task_queues=task_queues,
        log_queue=log_queue,
        pending_tasks=pending_tasks,
        stop_event=stop_event
    )

    return task_manager
