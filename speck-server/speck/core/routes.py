from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import logging
import json
from typing import List
from sqlalchemy.exc import NoResultFound
from sqlmodel import Session, select

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
            mailbox = session.exec(select(Mailbox)).one()
            await event_manager.notify({ "type": "mailbox", "messages": mailbox.get_messages() })
        except NoResultFound:
            # If we didn't find a Mailbox, then do nothing
            return

    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Message text was: {data}")

            message = json.loads(data)
            action = message.get('action')

            if action == 'execute_function':
                message_id = message['args']['message_id']
                function_name = message['args']['function_name']

                from emails.tasks import execute_function_for_message
                task_manager.add_task(
                    task=execute_function_for_message,
                    message_id=message_id,
                    function_name=function_name
                )

    except WebSocketDisconnect:
        event_manager.disconnect(websocket)