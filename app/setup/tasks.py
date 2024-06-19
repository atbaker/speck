import os

from config import celery_app, settings

from .utils import download_file


@celery_app.task
def download_model():
    """Download the model from HuggingFace."""
    url = 'https://huggingface.co/QuantFactory/Meta-Llama-3-8B-Instruct-GGUF/resolve/main/Meta-Llama-3-8B-Instruct.Q4_0.gguf?download=true'
    output_path = os.path.join(settings.models_dir, 'Meta-Llama-3-8B-Instruct.Q4_0.gguf')
    download_file(url, output_path)
