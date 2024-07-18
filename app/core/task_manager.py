import importlib
import multiprocessing
import threading
import time
import logging
import sys
from queue import Empty
from typing import Callable, Any, Optional
from logging.handlers import QueueHandler, QueueListener

from core.cache import initialize_cache

# Function to configure worker logging
def configure_worker_logging(log_queue):
    queue_handler = QueueHandler(log_queue)
    logger = logging.getLogger()
    if not logger.hasHandlers():  # Add this check to avoid duplicate handlers
        logger.setLevel(logging.INFO)
        logger.addHandler(queue_handler)

# Worker function
def worker(task_queue, stop_event, log_queue, cache_manager_dict, cache_manager_lock, task_manager_log_file):
    configure_worker_logging(log_queue)
    logger = logging.getLogger(f'worker-{multiprocessing.current_process().name}')

    # Initialize the cache and task_manager using our multiprocessing objects
    cache = initialize_cache(cache_manager_dict, cache_manager_lock)
    initialize_task_manager(
        cache_manager_dict=cache_manager_dict,
        cache_manager_lock=cache_manager_lock,
        task_queue=task_queue,
        log_queue=log_queue,
        stop_event=stop_event,
        log_file=task_manager_log_file
    )

    while not stop_event.is_set():
        try:
            task, args, kwargs = task_queue.get(timeout=1)
            logger.info(f"Executing task {task.__name__}")
            try:
                cache.set('last_task', task.__name__)
                task(*args, **kwargs)
                logger.info(f"Task {task.__name__} completed")
            except Exception as e:
                logger.error(f"Error executing task {task.__name__}: {e}", exc_info=True)
        except Empty:
            continue

# Scheduler function using threading
def scheduler(task_queue, stop_event, log_queue, recurring_tasks):
    configure_worker_logging(log_queue)
    logger = logging.getLogger(f'scheduler-{threading.current_thread().name}')

    next_run_times = {task: time.time() for task, interval, args, kwargs in recurring_tasks}

    while not stop_event.is_set():
        current_time = time.time()
        for task_name, interval, args, kwargs in recurring_tasks:
            if current_time >= next_run_times[task_name]:
                # Convert the task name into a function object
                module_name, function_name = task_name.rsplit('.', 1)
                module = importlib.import_module(module_name)
                task = getattr(module, function_name)

                logger.info(f"Scheduling recurring task {task.__name__}")
                task_queue.put((task, args, kwargs))
                next_run_times[task_name] = current_time + interval

        time.sleep(1)  # Sleep for a short duration to avoid busy-waiting

# Function to setup logging in the main process
def setup_main_logger(log_queue, log_file=None):
    logger = logging.getLogger()
    if not logger.hasHandlers():  # Add this check to avoid duplicate handlers
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
            cache_manager_dict,
            cache_manager_lock,
            log_file: Optional[str] = None,
            recurring_tasks: Optional[list] = None,
            task_queue = None,
            log_queue = None,
            stop_event = None
        ):
        self.task_queue = task_queue if task_queue is not None else multiprocessing.Queue()
        self.workers = []

        self.recurring_tasks = recurring_tasks if recurring_tasks is not None else []
        self.scheduler_thread = None

        self._stop_event = stop_event if stop_event is not None else multiprocessing.Event()
        self.log_queue = log_queue if log_queue is not None else multiprocessing.Queue()
        self.log_file = log_file
        self.logger, self.queue_listener = setup_main_logger(self.log_queue, self.log_file)

        # multiprocess Manager dict and lock for workers to use initializing the cache
        self.cache_manager_dict = cache_manager_dict
        self.cache_manager_lock = cache_manager_lock

    def add_task(self, task: Callable, *args, **kwargs):
        self.logger.info(f"Adding task {task.__name__}")
        self.task_queue.put((task, args, kwargs))

    def start(self, num_workers: int = 4):
        self.logger.info(f"Starting {num_workers} workers")
        for _ in range(num_workers):
            process = multiprocessing.Process(
                target=worker,
                args=(
                    self.task_queue,
                    self._stop_event,
                    self.log_queue,
                    self.cache_manager_dict,
                    self.cache_manager_lock,
                    self.log_file,
                )
            )
            process.start()
            self.workers.append(process)

        # Start the scheduler thread
        scheduler_thread = threading.Thread(
            target=scheduler,
            args=(self.task_queue, self._stop_event, self.log_queue, self.recurring_tasks)
        )
        scheduler_thread.start()
        self.scheduler_thread = scheduler_thread

    def stop(self):
        self.logger.info("Stopping all workers")
        self._stop_event.set()

        # Stop the scheduler thread
        if self.scheduler_thread:
            self.scheduler_thread.join()

        # Stop all workers
        for worker in self.workers:
            if isinstance(worker, multiprocessing.Process):
                worker.terminate()
                worker.join()

        self.queue_listener.stop()


task_manager = None

def initialize_task_manager(
        cache_manager_dict,
        cache_manager_lock,
        log_file: Optional[str] = None,
        recurring_tasks: Optional[list] = None,
        task_queue = None,
        log_queue = None,
        stop_event = None
    ):
    global task_manager
    task_manager = TaskManager(
        cache_manager_dict=cache_manager_dict,
        cache_manager_lock=cache_manager_lock,
        log_file=log_file,
        recurring_tasks=recurring_tasks,
        task_queue=task_queue,
        log_queue=log_queue,
        stop_event=stop_event
    )

    return task_manager
