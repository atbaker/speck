import os

from config import celery_app, settings

from .utils import download_file


@celery_app.task
def set_up_llm_service():
    """
    A task run on startup to prepare the LLM service.

    For now, simply ensures the model file is downloaded and ready.
    """
    # Ensure the model is downloaded
    url = 'https://huggingface.co/bartowski/gemma-2-9b-it-GGUF/resolve/main/gemma-2-9b-it-Q6_K.gguf?download=true'
    output_path = os.path.join(settings.models_dir, 'gemma-2-9b-it-Q6_K.gguf')
    download_file(url, output_path)

    print('LLM service setup complete')
