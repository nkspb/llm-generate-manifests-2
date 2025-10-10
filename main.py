import os
import uvicorn
import logging
import asyncio

from dialog_bot_sdk.bot import DialogBot
from dialog_bot_sdk.entities.messaging import CommandHandler, MessageHandler, UpdateMessage, MessageContentType

from fastapi import FastAPI

# Import LLM-bot components
from core.config import llm, vector_store
from core.session_manager import SessionStore
from models import ChatRequest
from routes.chat import chat as chat_handler
import routes.chat as chat

# В значения нужно передать путь до сертификата минцифр
os.environ["REQUESTS_CA_BUNDLE"] = "certs/X.pem"
os.environ["GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"] = "certs/X.pem"

bot_config = {
    "endpoint": "X",
    # сюда нужно подставить токен бота, который вы получили
    "token": "X",
    "is_secure": True,
    "logger_config": {
        "level": "error"
    }
}

logger = logging.getLogger(__name__)

bot = DialogBot.create_bot(bot_config)

# Inject dependencies. Same as in app.py
session_store = SessionStore()
chat.llm = llm
chat.vector_store = vector_store
chat.session_store = session_store

peer_sessions = {}

app = FastAPI()

def start(message: UpdateMessage) -> None:
    # Метод срабатывает при выполнении команды /start в окне бота
    # bot.messaging.send_message(message.peer, f"def start -> message.peer: {message.peer}, message.sender_peer: {message.sender_peer}")
    bot.messaging.send_message(message.peer, f'Я - бот для генерации манифестов настройки service mesh:\n \
        def start -> message.peer: {message.peer}, message.sender_peer: {message.sender_peer} ')

def sync_text_wrapper(message: UpdateMessage):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(text(message))
    else:
        loop.create_task(text(message))

async def text(message: UpdateMessage) -> None:
    # Метод срабатывает при отправке сообщения в окне бота
    # print(f"[DEBUG] Объект message: {message}")
    # print(f"[DEBUG] Отправитель: {message.peer.id}, Текст сообщения: {message.message.text_message.text}")
    # logger.info(f"Отправитель: {message.peer.id}, Текст сообщения: {message.message.text_message.text}")

    # bot.messaging.send_message(message.peer, f'Ваше сообщение было: {message.message.text_message.text}')
    user_id = message.peer.id
    user_text = message.message.text_message.text
   
    # session_id = None
    # prior_session_id = peer_sessions.get(user_id)
    prior_session_id = session_store.get_latest_for_user(user_id)
    
    print(f"[MAIN] user_id = {user_id}, peer_sessions = {peer_sessions}")

    if prior_session_id and session_store.get(prior_session_id):
        print(f"[DEBUG] Using session: {prior_session_id}")
        session_id = prior_session_id
    else:
        print(f"[DEBUG] No valid session for user {user_id}")
        session_id = None

    print(f"[MAIN] Incoming message from {user_id}: {user_text}")
    print(f"[MAIN] peer_sessions BEFORE: {peer_sessions}")
    print(f"[MAIN] Prior session_id used in ChatRequest: {session_id}")

    chat_request = ChatRequest(message=user_text, session_id=session_id)
    chat_response = await chat_handler(chat_request)

    print(f"[MAIN] chat_response.session_id = {chat_response.session_id}")

    if chat_response.session_id:
        peer_sessions[user_id] = chat_response.session_id
        print(f"[MAIN] Updated session for {user_id}: {chat_response.session_id}")
    else:
        peer_sessions.pop(user_id, None)
        print(f"[MAIN] Cleared session for {user_id}")

    bot.messaging.send_message(
        message.peer,
        chat_response.reply
    )

bot.messaging.command_handler([CommandHandler(start, "start", description="Расскажу о себе")])   
bot.messaging.message_handler([MessageHandler(sync_text_wrapper, MessageContentType.TEXT_MESSAGE)])

bot.updates.on_updates(do_read_messages=True, do_register_commands=True,in_thread=True)

if __name__ == '__main__':
    uvicorn.run("main:app", host="0.0.0.0", port=5001, log_level="info") # filename:fastapi app instance
