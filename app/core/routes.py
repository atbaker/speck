from fastapi import APIRouter, WebSocket
import logging
import json
from typing import List
from sqlalchemy.exc import NoResultFound
from sqlmodel import Session, select

from config import db_engine
from emails.models import Mailbox

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    with Session(db_engine) as session:
        try:
            # TODO: Enhance to support multiple mailboxes
            mailbox = session.exec(select(Mailbox)).one()
            await websocket.send_json({ "type": "mailbox", "messages": mailbox.get_messages() })
        except NoResultFound:
            # If we didn't find a Mailbox, then do nothing
            return

    while True:
        data = await websocket.receive_text()
        await websocket.send_text(f"Message text was: {data}")

        message = json.loads(data)
        action = message.get('action')
        if action == "stop_recording":
            # Process and store recorded actions
            actions = message["actions"]
            # Convert actions to a script or function and store in database
            process_and_store_actions(actions)

def process_and_store_actions(actions: List[dict]):
    # Process actions into a script or function
    function_script = convert_actions_to_script(actions)

    print(function_script)

    # Store function script in database
    # function = Function(script=function_script)
    # session.add(function)
    # session.commit()

def convert_actions_to_script(actions: List[dict]) -> str:
    # Convert recorded actions to a script format
    script = ""
    for action in actions:
        if action["type"] == "click":
            script += f"document.querySelector('{action['target']}').click();\n"
        elif action["type"] == "input":
            script += f"document.querySelector('{action['target']}').value = '{action['value']}';\n"
    return script
