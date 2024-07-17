import multiprocessing
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
def worker(task_queue, stop_event, log_queue, cache_manager_dict, cache_manager_lock):
    configure_worker_logging(log_queue)
    logger = logging.getLogger(f'worker-{multiprocessing.current_process().name}')

    # Initialize the cache using our multiprocessing Manager dict and lock
    cache = initialize_cache(cache_manager_dict, cache_manager_lock)

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
    def __init__(self, cache_manager_dict, cache_manager_lock, log_file: Optional[str] = None):
        self.task_queue = multiprocessing.Queue()
        self.workers = []
        self._stop_event = multiprocessing.Event()
        self.log_queue = multiprocessing.Queue()
        self.logger, self.queue_listener = setup_main_logger(self.log_queue, log_file)

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
                args=(self.task_queue, self._stop_event, self.log_queue, self.cache_manager_dict, self.cache_manager_lock)
            )
            process.start()
            self.workers.append(process)

    def stop(self):
        self.logger.info("Stopping all workers")
        self._stop_event.set()
        for worker in self.workers:
            worker.terminate()
            worker.join()
        self.queue_listener.stop()


task_manager = None

def initialize_task_manager(cache_manager_dict, cache_manager_lock, log_file: Optional[str] = None):
    global task_manager
    task_manager = TaskManager(cache_manager_dict=cache_manager_dict, cache_manager_lock=cache_manager_lock, log_file=log_file)

    return task_manager
