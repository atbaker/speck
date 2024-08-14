import os
import logging
import subprocess

from config import settings

from .utils import download_file

logger = logging.getLogger(__name__)


def download_models():
    """
    A task run on startup to download the models Llamafile will use. For now,
    downloads two models: one for generating embeddings and one for generating
    completions.
    """
    embedding_model_url = 'https://huggingface.co/mixedbread-ai/mxbai-embed-large-v1/resolve/main/gguf/mxbai-embed-large-v1-f16.gguf?download=true'
    embedding_model_output_path = os.path.join(settings.models_dir, 'mxbai-embed-large-v1-f16.gguf')
    download_file(embedding_model_url, embedding_model_output_path)

    # url = 'https://huggingface.co/QuantFactory/Meta-Llama-3-8B-Instruct-GGUF/resolve/main/Meta-Llama-3-8B-Instruct.Q4_0.gguf?download=true'
    # output_path = os.path.join(settings.models_dir, 'Meta-Llama-3-8B-Instruct.Q4_0.gguf')
    # url = 'https://huggingface.co/bartowski/gemma-2-9b-it-GGUF/resolve/main/gemma-2-9b-it-Q6_K.gguf?download=true'
    completion_model_url = 'https://huggingface.co/bartowski/gemma-2-9b-it-GGUF/resolve/main/gemma-2-9b-it-Q5_K_M.gguf?download=true'
    # url = 'https://huggingface.co/bartowski/gemma-2-9b-it-GGUF/resolve/main/gemma-2-9b-it-Q4_K_M.gguf?download=true'
    completion_model_output_path = os.path.join(settings.models_dir, 'gemma-2-9b-it-Q5_K_M.gguf')
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
