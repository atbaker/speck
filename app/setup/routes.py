from fastapi import APIRouter
import logging

from .tasks import download_model
from .utils import start_model_server

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get('/start-download-model')
async def start_download_model():
    """Download the model from HuggingFace."""
    download_model.delay()
    return {'message': 'Model downloading'}


@router.get('/start-server')
async def start_server():
    """Start the model server"""
    start_model_server()
    return {'message': 'Model server starting'}
