import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session

from emails.models import Mailbox
from core.event_manager import event_manager
from config import db_engine

router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await event_manager.connect(websocket)

    try:
        # Send the latest Mailbox state upon initial connection
        with Session(db_engine) as session:
            try:
                # Assuming a single mailbox for MVP; adapt if multiple mailboxes are needed
                mailbox = session.execute(select(Mailbox)).scalar_one()
                mailbox_state = mailbox.get_state()
                await websocket.send_json({
                    "type": "mailbox",
                    "payload": mailbox_state
                })
            except NoResultFound:
                # If no Mailbox exists, send an empty state or an appropriate message
                await websocket.send_json({
                    "type": "error",
                    "message": "No mailbox found."
                })
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "message": f"An error occurred while sending mailbox state: {str(e)}"
        })

    try:
        while True:
            # For MVP, we're not handling incoming actions yet
            data = await websocket.receive_text()
            message = json.loads(data)

            # Chat messages
            if message.get("type") == "chat_message":
                # Get our create a Conversation object
                from chat.models import Conversation
                with Session(db_engine) as session:
                    try:
                        conversation = session.execute(
                            select(Conversation)
                            .filter(Conversation.mailbox_id == mailbox.id)
                            .order_by(Conversation.created_at.desc())
                            .limit(1)
                        ).scalar_one()
                    except NoResultFound:
                        conversation = Conversation(mailbox_id=mailbox.id)
                        session.add(conversation)
                        session.commit()

                    # Process the user message
                    content = message['payload']
                    reply = conversation.process_user_message(content)

                    # Save the conversation state
                    session.add(conversation)
                    session.commit()

                await websocket.send_json({
                    "type": "chat_message",
                    "payload": reply.content
                })

    except WebSocketDisconnect:
        event_manager.disconnect(websocket)
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "message": f"An unexpected error occurred: {str(e)}"
        })
        await websocket.close()
        event_manager.disconnect(websocket)