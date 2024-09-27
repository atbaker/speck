import asyncio
import importlib
import multiprocessing
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

# Worker function
def worker(
        queue_name,
        task_queues,
        stop_event,
        log_queue,
        task_manager_log_file,
        pipe_conn
    ):
    configure_worker_logging(log_queue)
    logger = logging.getLogger(f'worker-{queue_name}')

    # Initialize the task manager so workers can schedule tasks themselves
    initialize_task_manager(
        task_queues=task_queues,
        log_queue=log_queue,
        stop_event=stop_event,
        log_file=task_manager_log_file
    )

    # Identify which queue we're working
    task_queue = task_queues[queue_name]

    # Work the queue
    while not stop_event.is_set():
        try:
            task, args, kwargs = task_queue.get(timeout=1)
            logger.info(f"Executing task {task.__name__} with args {args} and kwargs {kwargs}")
            try:
                cache.set('last_task', task.__name__)
                task(*args, **kwargs)
                logger.info(f"Task {task.__name__} completed")

                # Send a message through the pipe when the task is completed
                pipe_conn.send(task.__name__)

            except Exception as e:
                logger.error(f"Error executing task {task.__name__}: {e}", exc_info=True)
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

    def add_task(self, task: Callable, queue_name: str = 'general', *args, **kwargs):
        self.logger.info(f"Adding task {task.__name__} to {queue_name} queue")
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
                            message = { "type": "mailbox", "threads": mailbox.get_threads() }
                            asyncio.run(event_manager.notify(message))
            time.sleep(0.1)

task_manager = None

def initialize_task_manager(
        log_file: Optional[str] = None,
        recurring_tasks: Optional[list] = None,
        task_queues=None,
        log_queue=None,
        stop_event=None
    ):
    global task_manager
    task_manager = TaskManager(
        log_file=log_file,
        recurring_tasks=recurring_tasks,
        task_queues=task_queues,
        log_queue=log_queue,
        stop_event=stop_event
    )

    return task_manager
