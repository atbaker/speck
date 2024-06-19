from config import celery_app


@celery_app.task
def send_email():
    from time import sleep
    sleep(15)
    print('Sending email')
