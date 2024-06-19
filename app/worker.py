from config import celery_app

# https://stackoverflow.com/questions/67023208/run-celery-worker-with-a-compiled-python-module-compiled-using-pyinstaller
if __name__ == '__main__':
    celery_app.worker_main(
        argv=['worker', '--beat', '--loglevel=info', '--concurrency=1']
    )
