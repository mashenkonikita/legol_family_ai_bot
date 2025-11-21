# ================================
# 🤖 СЕМЕЙНЫЙ AI АГЕНТ (GIGACHAT)
# ПОЛНЫЙ КОД - ВЕРСИЯ 2.0
# ================================

import os
import logging
import requests
import base64
import uuid
from datetime import datetime
from typing import Optional, Dict, List
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction

# ================================
# КОНФИГУРАЦИЯ
# ================================

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GIGACHAT_CLIENT_ID = os.getenv('GIGACHAT_CLIENT_ID')
GIGACHAT_CLIENT_SECRET = os.getenv('GIGACHAT_CLIENT_SECRET')
PORT = int(os.getenv('PORT', 8443))
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://your-railway-app.up.railway.app')

GIGACHAT_AUTH_URL = 'https://ngw.devices.sberbank.ru:9443/api/v2/oauth'
GIGACHAT_API_URL = 'https://gigachat-api.neb.neb.neb.ru/api/v1/chat/completions'
GIGACHAT_MODEL = 'GigaChat'

MAX_DIALOG_HISTORY = 15
MAX_TOKENS = 512
TEMPERATURE = 0.7
TOP_P = 0.1
REQUEST_TIMEOUT = 30
TOKEN_TIMEOUT = 10

# ================================
# ЛОГИРОВАНИЕ
# ================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ================================
# МЕНЕДЖЕР ПАМЯТИ ДИАЛОГОВ
# ================================

class DialogMemory:
    def __init__(self):
        self.dialogs: Dict[int, List[Dict]] = {}
        self.token_cache: Dict[str, tuple] = {}
    
    def add_message(self, user_id: int, role: str, content: str):
        if user_id not in self.dialogs:
            self.dialogs[user_id] = []
        
        self.dialogs[user_id].append({"role": role, "content": content})
        
        if len(self.dialogs[user_id]) > MAX_DIALOG_HISTORY:
            self.dialogs[user_id] = self.dialogs[user_id][-MAX_DIALOG_HISTORY:]
    
    def get_history(self, user_id: int) -> List[Dict]:
        return self.dialogs.get(user_id, [])
    
    def clear_dialog(self, user_id: int):
        if user_id in self.dialogs:
            del self.dialogs[user_id]
            logger.info(f"🗑️ История диалога очищена для {user_id}")
    
    def cache_token(self, token: str):
        self.token_cache['gigachat'] = (token, datetime.now())
    
    def get_cached_token(self) -> Optional[str]:
        if 'gigachat' in self.token_cache:
            token, timestamp = self.token_cache['gigachat']
            if (datetime.now() - timestamp).seconds < 1800:
                return token
        return None

memory = DialogMemory()

# ================================
# API GIGACHAT
# ================================

def get_gigachat_token() -> Optional[str]:
    try:
        cached_token = memory.get_cached_token()
        if cached_token:
            logger.debug("✅ Токен из кэша")
            return cached_token
        
        auth_string = f"{GIGACHAT_CLIENT_ID}:{GIGACHAT_CLIENT_SECRET}"
        auth_bytes = auth_string.encode('utf-8')
        auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')
        
        headers = {
            'Authorization': f'Basic {auth_b64}',
            'RqUID': str(uuid.uuid4()),
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        response = requests.post(
            GIGACHAT_AUTH_URL,
            headers=headers,
            data={'scope': 'GIGACHAT_API_PERS'},
            timeout=TOKEN_TIMEOUT,
            verify=True
        )
        
        if response.status_code == 200:
            token = response.json().get('access_token')
            memory.cache_token(token)
            logger.info("✅ Новый токен получен")
            return token
        else:
            logger.error(f"❌ Ошибка токена: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"❌ Ошибка при получении токена: {e}")
        return None

def ask_gigachat(message_text: str, user_id: int) -> str:
    try:
        token = get_gigachat_token()
        if not token:
            return "❌ Ошибка подключения к GigaChat"
        
        memory.add_message(user_id, "user", message_text)
        history = memory.get_history(user_id)
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            "model": GIGACHAT_MODEL,
            "messages": history,
            "temperature": TEMPERATURE,
            "top_p": TOP_P,
            "max_tokens": MAX_TOKENS,
            "system_prompt": "Ты полезный семейный AI помощник. Отвечай дружелюбно и конструктивно."
        }
        
        response = requests.post(
            GIGACHAT_API_URL,
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT,
            verify=False
        )
        
        if response.status_code == 200:
            result = response.json()
            assistant_message = result['choices']['message']['content']
            memory.add_message(user_id, "assistant", assistant_message)
            logger.info(f"✅ Ответ получен для {user_id}")
            return assistant_message
        else:
            logger.error(f"❌ Ошибка API: {response.status_code}")
            return f"⚠️ Ошибка сервиса ({response.status_code})"
    
    except requests.exceptions.Timeout:
        logger.error("❌ Таймаут")
        return "⏱️ Истёк таймаут. Попробуйте позже."
    except requests.exceptions.ConnectionError:
        logger.error("❌ Ошибка подключения")
        return "🌐 Ошибка подключения"
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return f"❌ Ошибка: {str(e)}"

# ================================
# ОБРАБОТЧИКИ КОМАНД
# ================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 Привет! Я семейный AI помощник на GigaChat."

        "🤖 Я помогу с:"
        "• Советами и рекомендациями"
        "• Планированием"
        "• Ответами на вопросы"
        "• Генерацией идей"
        "📝 Просто напишите сообщение!"
        "/help - справка"
        "/clear - новый диалог"
        "/about - о боте"
    )
    await update.message.reply_text(welcome_text)
    logger.info(f"👤 Новый пользователь: {update.effective_user.id}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📋 СПРАВКА"
        "/start - начало"
        "/help - справка"
        "/clear - очистить историю"
        "/about - о боте"
        "💡 Просто пишите сообщения!"
    )
    await update.message.reply_text(help_text)

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    about_text = (
        "ℹ️ О БОТЕ"
        "🤖 Семейный AI помощник"
        "⚙️ GigaChat (Сбербанк)"
        "☁️ Railway.app"
        "💾 Память: 15 сообщений"
        "🇷🇺 Русский язык"
        "✨ v2.0"
    )
    await update.message.reply_text(about_text)

async def clear_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    memory.clear_dialog(user_id)
    await update.message.reply_text("✅ История очищена! 🚀")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message_text = update.message.text.strip()
    
    if not message_text:
        await update.message.reply_text("⚠️ Напишите сообщение")
        return
    
    if len(message_text) > 2000:
        await update.message.reply_text("⚠️ Сообщение слишком длинное")
        return
    
    logger.info(f"💬 От @{update.effective_user.username}: {message_text[:50]}")
    
    try:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=ChatAction.TYPING
        )
        
        response = ask_gigachat(message_text, user_id)
        
        if len(response) > 4096:
            parts = [response[i:i+4096] for i in range(0, len(response), 4096)]
            for part in parts:
                await update.message.reply_text(part)
        else:
            await update.message.reply_text(response)
        
        logger.info(f"✅ Ответ отправлен {user_id}")
    
    except Exception as e:
        logger.error(f"❌ Ошибка обработки: {e}")
        await update.message.reply_text("❌ Ошибка. Попробуйте позже.")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"❌ Ошибка: {context.error}", exc_info=context.error)

# ================================
# ИНИЦИАЛИЗАЦИЯ
# ================================

async def post_init(application: Application):
    try:
        commands = [
            BotCommand("start", "Начало работы"),
            BotCommand("help", "Справка"),
            BotCommand("clear", "Новый диалог"),
            BotCommand("about", "О боте"),
        ]
        await application.bot.set_my_commands(commands)
        logger.info("✅ Команды установлены")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации: {e}")

def main():
    logger.info("=" * 60)
    logger.info("🚀 ЗАПУСК СЕМЕЙНОГО AI АГЕНТА")
    logger.info("=" * 60)
    
    if not all([TELEGRAM_TOKEN, GIGACHAT_CLIENT_ID, GIGACHAT_CLIENT_SECRET]):
        logger.error("❌ Не заданы переменные окружения!")
        return
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("clear", clear_dialog))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    application.add_error_handler(error_handler)
    
    application.post_init = post_init
    
    logger.info(f"⚙️ Запуск на порту {PORT}...")
    logger.info(f"📍 Webhook: {WEBHOOK_URL}")
    
    application.run_polling()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("⏹️ Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        raise