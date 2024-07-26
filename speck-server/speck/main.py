import multiprocessing
import os
import signal
import sys


def handle_exit(*args):
    # Stop the background task manager
    from core.task_manager import task_manager
    task_manager.stop()

    # Force stop the LLM service before shutdown
    from core.llm_service_manager import llm_service_manager
    llm_service_manager.force_stop_server()

    sys.exit(0)


if __name__ == "__main__":
    # Must be imported and set first, for PyInstaller
    # https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#multi-processing
    multiprocessing.freeze_support()
    multiprocessing.set_start_method('spawn')

    # Create a multiprocessing Manager to use for the cache and task manager
    from multiprocessing import Manager
    manager = Manager()

    # Initialize the cache
    from core.cache import initialize_cache
    initialize_cache(manager=manager)

    # Define the recurring tasks
    recurring_tasks = [
        ('emails.tasks.sync_inbox', 60, (), {})  # (task, interval in seconds, args, kwargs)
    ]

    # Import and initialize the settings
    from config import settings

    # Initialize the task manager
    from core.task_manager import initialize_task_manager
    task_manager = initialize_task_manager(
        log_file=settings.task_manager_log_file,
        recurring_tasks=recurring_tasks
    )

    # Create the database tables
    from sqlmodel import SQLModel
    from config import db_engine
    from emails import models as email_models
    SQLModel.metadata.create_all(db_engine)

    # Start the task manager
    task_manager.start(
        num_workers=1
    )

    # Schedule a task to install the Playwright browser
    from core.tasks import install_browser
    task_manager.add_task(
        task=install_browser
    )

    # Schedule a task to set up the LLM server
    from core.tasks import set_up_llm_service
    task_manager.add_task(
        task=set_up_llm_service
    )

    # Register signal handlers
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    # Start the FastAPI server
    from server import app
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=17725)
