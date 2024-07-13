import os
import sys


def run_server():
    import uvicorn
    from server import app
    uvicorn.run(app, host="127.0.0.1", port=7725)

def run_worker():
    # https://stackoverflow.com/questions/67023208/run-celery-worker-with-a-compiled-python-module-compiled-using-pyinstaller
    from config import celery_app
    celery_app.worker_main(
        argv=['worker', '--loglevel=info', '--pool=threads', '--concurrency=1']
    )

def run_scheduler():
    from config import celery_app
    celery_app.Beat(loglevel='info').run()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: speck [server|worker|scheduler]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "server":
        run_server()
    elif command == "worker":
        run_worker()
    elif command == "scheduler":
        run_scheduler()
    else:
        print(f"Unknown command: {command}")
        print("Usage: main.py [server|worker|scheduler]")
        sys.exit(1)
