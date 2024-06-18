from app.config import huey


@huey.task()
def send_email():
    print('Sending email')
