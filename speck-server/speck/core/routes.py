from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import logging
import json
from typing import List
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session
from sqlalchemy import select

from config import db_engine
from core.event_manager import event_manager
from core.task_manager import task_manager
from emails.models import Mailbox, Message

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await event_manager.connect(websocket)

    with Session(db_engine) as session:
        try:
            # Send the latest Mailbox state upon initial connection
            # TODO: Enhance to support multiple mailboxes
            mailbox = session.execute(select(Mailbox)).scalar_one()
            await event_manager.notify({ "type": "mailbox", "threads": mailbox.get_threads() })
        except NoResultFound:
            # If we didn't find a Mailbox, then do nothing
            return

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            action = message.get('action')

            if action == 'execute_function':
                thread_id = message['args']['thread_id']
                function_name = message['args']['function_name']

                from emails.tasks import execute_function_for_message
                task_manager.add_task(
                    task=execute_function_for_message,
                    thread_id=thread_id,
                    function_name=function_name
                )
                await websocket.send_text(f"Function {function_name} scheduled for thread {thread_id}.")

            elif action == 'get_thread_details':
                thread_id = message.get('threadId')
                if thread_id:
                    try:
                        mailbox = session.execute(select(Mailbox)).scalar_one()
                        thread = mailbox.get_thread(thread_id)
                        thread_data = {
                            "threadId": thread.id,
                            "summary": thread.summary,
                            "category": thread.category
                        }
                        await websocket.send_text(json.dumps({
                            "type": "thread_details",
                            "threadDetails": thread_data
                        }))
                    except NoResultFound:
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": f"Thread with ID {thread_id} not found."
                        }))
                else:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "No threadId provided in the request."
                    }))

    except WebSocketDisconnect:
        event_manager.disconnect(websocket)
        logger.info("WebSocket disconnected")