import os
import logging

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
    url = 'https://huggingface.co/bartowski/gemma-2-9b-it-GGUF/resolve/main/gemma-2-9b-it-Q6_K.gguf?download=true'
    output_path = os.path.join(settings.models_dir, 'gemma-2-9b-it-Q6_K.gguf')
    download_file(url, output_path)

    logger.info('LLM service setup complete')
