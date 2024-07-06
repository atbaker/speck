from fastapi import APIRouter
import logging

from .llm_service_manager import llm_service_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get('/start-llm-service')
async def start_llm_service():
    """Start the LLM service"""
    pid = llm_service_manager.start_server()
    if pid:
        return {'message': 'LLM service ready', 'pid': pid}
    else:
        return {'message': 'Failed to start LLM service'}

@router.get('/stop-llm-service')
async def stop_llm_service():
    """Stop the LLM service if idle"""
    llm_service_manager.stop_server()
    return {'message': 'LLM service stopping if idle'}

@router.get('/force-stop-llm-service')
async def force_stop_llm_service():
    """Forcefully stop the LLM service"""
    llm_service_manager.force_stop_server()
    return {'message': 'LLM service forcefully stopped'}
