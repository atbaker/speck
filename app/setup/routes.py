from fastapi import APIRouter
import logging

from .llm_server_manager import llm_server_manager  # Import the server manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get('/start-server')
async def start_server():
    """Start the model server"""
    pid = llm_server_manager.start_server()
    if pid:
        return {'message': 'Model server ready', 'pid': pid}
    else:
        return {'message': 'Failed to start model server'}

@router.get('/stop-server')
async def stop_server():
    """Stop the model server if idle"""
    llm_server_manager.stop_server()
    return {'message': 'Model server stopping if idle'}

@router.get('/force-stop-server')
async def force_stop_server():
    """Forcefully stop the model server"""
    llm_server_manager.force_stop_server()
    return {'message': 'Model server forcefully stopped'}
