from dataclasses import dataclass, field
import threading
import sched
import time
import logging
import sys
from queue import PriorityQueue, Empty
from typing import Callable, Any, Optional


@dataclass(order=True)
class PrioritizedItem:
    priority: int
    item: Any=field(compare=False)


class PriorityTaskManager:
    def __init__(self, log_file: Optional[str] = None):
        self.task_queue = PriorityQueue()
        self.workers = []
        self._stop_event = threading.Event()
        self.scheduler = sched.scheduler(time.time, time.sleep)
        self.scheduler_thread = threading.Thread(target=self.run_scheduler)
        self.scheduler_thread.daemon = True

        # Set up logging
        self.logger = logging.getLogger('worker')
        self.logger.setLevel(logging.DEBUG)
        
        if log_file:
            handler = logging.FileHandler(log_file)
        else:
            handler = logging.StreamHandler(sys.stdout)
        
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def add_task(self, priority: int, task: Callable, *args, **kwargs):
        self.logger.info(f"Adding task {task.__name__} with priority {priority}")
        new_task_entry = PrioritizedItem(priority, (task, args, kwargs))
        self.task_queue.put(new_task_entry)

    def worker(self):
        while not self._stop_event.is_set():
            try:
                prioritized_task = self.task_queue.get(timeout=1)
                task, args, kwargs = prioritized_task.item
                self.logger.info(f"Executing task {task.__name__} with priority {prioritized_task.priority}")
                task(*args, **kwargs)
                self.task_queue.task_done()
                self.logger.info(f"Task {task.__name__} completed")
            except Empty:
                continue

    def start(self, num_workers: int = 4):
        self.logger.info(f"Starting {num_workers} workers")
        for _ in range(num_workers):
            thread = threading.Thread(target=self.worker)
            thread.start()
            self.workers.append(thread)
        self.scheduler_thread.start()

    def stop(self):
        self.logger.info("Stopping all workers")
        self._stop_event.set()
        for worker in self.workers:
            worker.join()
        self.scheduler_thread.join()

    def add_recurring_task(self, interval: int, priority: int, task: Callable, *args, **kwargs):
        """Schedule a recurring task to run at a specific interval."""
        def wrapper():
            self.add_task(priority, task, *args, **kwargs)
            self.scheduler.enter(interval, 1, wrapper)

        self.logger.debug(f"Adding recurring task with interval {interval} and priority {priority}")
        self.scheduler.enter(interval, 1, wrapper)

    def run_scheduler(self):
        """Run the scheduler in a separate thread."""
        self.logger.info("Scheduler started")
        while not self._stop_event.is_set():
            self.scheduler.run(blocking=False)
            time.sleep(1)
        self.logger.info("Scheduler stopped")

# Example tasks
def example_task(manager: PriorityTaskManager, message: str):
    manager.logger.info(f"Task started: {message}")
    # Simulate task processing
    time.sleep(2)
    manager.logger.info(f"Task completed: {message}")

if __name__ == "__main__":
    manager = PriorityTaskManager()
    manager.start(num_workers=1)
    
    manager.add_task(1, example_task, "Task 1")
    manager.add_task(3, example_task, "Task 2")
    manager.add_task(2, example_task, "Task 3")
    
    # Add a recurring task to run every minute
    manager.add_recurring_task(interval=10, priority=1, task=example_task, message="Recurring Task")
    
    time.sleep(180)  # Run the program for 3 minutes to observe recurring tasks
    
    manager.stop()