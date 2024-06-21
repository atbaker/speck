import os

from config import celery_app, settings

from .utils import download_file


@celery_app.task
def set_up_llm_server():
    """
    A task run on startup to prepare the LLM server.

    For now, simply ensures the model file is downloaded and ready.
    """
    # Ensure the model is downloaded
    url = 'https://huggingface.co/QuantFactory/Meta-Llama-3-8B-Instruct-GGUF/resolve/main/Meta-Llama-3-8B-Instruct.Q4_0.gguf?download=true'
    output_path = os.path.join(settings.models_dir, 'Meta-Llama-3-8B-Instruct.Q4_0.gguf')
    download_file(url, output_path)

    print('LLM setup complete')
