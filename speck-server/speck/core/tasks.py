import os
import logging
import subprocess

from config import settings

from .utils import download_file

logger = logging.getLogger(__name__)


def set_up_llm_service():
    """
    A task run on startup to prepare the LLM service.

    For now, simply ensures the model file is downloaded and ready.
    """
    # url = 'https://huggingface.co/QuantFactory/Meta-Llama-3-8B-Instruct-GGUF/resolve/main/Meta-Llama-3-8B-Instruct.Q4_0.gguf?download=true'
    # output_path = os.path.join(settings.models_dir, 'Meta-Llama-3-8B-Instruct.Q4_0.gguf')
    # url = 'https://huggingface.co/bartowski/gemma-2-9b-it-GGUF/resolve/main/gemma-2-9b-it-Q6_K.gguf?download=true'
    url = 'https://huggingface.co/bartowski/gemma-2-9b-it-GGUF/resolve/main/gemma-2-9b-it-Q5_K_M.gguf?download=true'
    # url = 'https://huggingface.co/bartowski/gemma-2-9b-it-GGUF/resolve/main/gemma-2-9b-it-Q4_K_M.gguf?download=true'
    output_path = os.path.join(settings.models_dir, 'gemma-2-9b-it-Q5_K_M.gguf')
    download_file(url, output_path)

    logger.info('LLM service setup complete')

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
                # 'chromium'
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
