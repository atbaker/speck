from huey.bin.huey_consumer import consumer_main
import sys

# Adapted from https://github.com/coleifer/huey/blob/master/huey/bin/huey_consumer.py
if __name__ == '__main__':
    # Add the path to our huey object manually
    sys.argv.append('app.config.huey')

    if sys.version_info >= (3, 8) and sys.platform == 'darwin':
        import multiprocessing
        try:
            multiprocessing.set_start_method('fork')
        except RuntimeError:
            pass
    consumer_main()
