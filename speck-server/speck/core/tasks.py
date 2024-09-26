import os
import logging
import subprocess

from config import settings

from .utils import download_file

logger = logging.getLogger(__name__)


def download_models():
    """
    A task run on startup to download the model Llamafile will use. For now,
    downloads just a single model for generating embeddings.
    """
    embedding_model_url = 'https://huggingface.co/leliuga/all-MiniLM-L6-v2-GGUF/resolve/main/all-MiniLM-L6-v2.F16.gguf?download=true'
    embedding_model_output_path = os.path.join(settings.models_dir, 'all-MiniLM-L6-v2.F16.gguf')
    download_file(embedding_model_url, embedding_model_output_path)

    if settings.use_local_completions:
        completion_model_url = 'https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_S.gguf?download=true'
        completion_model_output_path = os.path.join(settings.models_dir, 'Meta-Llama-3.1-8B-Instruct-Q4_K_S.gguf')
        download_file(completion_model_url, completion_model_output_path)

    logger.info('Model download complete')

def install_browser():
    """
    A task run on startup to install the Playwright browser.
    """
    logger.info('Installing browser...')

    # Adapted from Playwright's __main__.py, to call the Playwright CLI directly
    # https://github.com/microsoft/playwright-python/blob/main/playwright/__main__.py
    from playwright._impl._driver import compute_driver_executable, get_driver_env
    driver_executable, driver_cli = compute_driver_executable()

    try:
        subprocess.run(
            [
                driver_executable,
                driver_cli,
            'install',
                'chromium'
                'firefox'
            ],
            check=True,
            capture_output=True,
            text=True,
            env=get_driver_env().update({
                'PLAYWRIGHT_BROWSERS_PATH': settings.playwright_browsers_dir
            })
        )
        logger.info(f'Browser installed successfully')
    except subprocess.CalledProcessError as e:
        logger.error(f'Failed to install browser: {e.stderr}')

    logger.info('Browser installed')
