import os
import logging
import requests
import base64
import uuid
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Получаем переменные окружения
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GIGACHAT_CLIENT_ID = os.getenv('GIGACHAT_CLIENT_ID')
GIGACHAT_CLIENT_SECRET = os.getenv('GIGACHAT_CLIENT_SECRET')
PORT = int(os.getenv('PORT', 8443))
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://your-railway-app.up.railway.app')

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Хранилище диалогов в памяти
dialogs = {}

def get_gigachat_token():
    """Получить токен доступа к GigaChat"""
    try:
        auth_string = f"{GIGACHAT_CLIENT_ID}:{GIGACHAT_CLIENT_SECRET}"
        auth_bytes = auth_string.encode('utf-8')
        auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')
        
        headers = {
            'Authorization': f'Basic {auth_b64}',
            'RqUID': str(uuid.uuid4()),
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {'scope': 'GIGACHAT_API_PERS'}
        
        response = requests.post(
            'https://auth.api.sbercloud.ru/oauth',
            headers=headers,
            data=data,
            timeout=10
        )
        
        if response.status_code == 200:
            token = response.json()['access_token']
            logger.info("✅ Токен GigaChat успешно получен")
            return token
        else:
            logger.error(f"❌ Ошибка при получении токена: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"❌ Исключение при получении токена: {e}")
        return None

def ask_gigachat(message_text, user_id):
    """Отправить запрос в GigaChat с памятью диалога"""
    try:
        token = get_gigachat_token()
        if not token:
            return "❌ Ошибка подключения к GigaChat. Попробуйте позже."
        
        # Инициализируем историю пользователя
        if user_id not in dialogs:
            dialogs[user_id] = []
        
        # Добавляем сообщение пользователя
        dialogs[user_id].append({
            "role": "user",
            "content": message_text
        })
        
        # Ограничиваем историю последними 15 сообщениями
        history = dialogs[user_id][-15:]
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            "model": "GigaChat",
            "messages": history,
            "temperature": 0.7,
            "top_p": 0.1,
            "max_tokens": 512,
            "system_prompt": "Ты помощник в семейной группе Telegram. Отвечай дружелюбно, кратко и конструктивно. Помогай с советами, планированием и идеями."
        }
        
        response = requests.post(
            'https://gigachat-api.neb.neb.neb.ru/api/v1/chat/completions',
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            assistant_message = result['choices']['message']['content']
            
            # Добавляем ответ в историю
            dialogs[user_id].append({
                "role": "assistant",
                "content": assistant_message
            })
            
            logger.info(f"✅ Ответ получен для пользователя {user_id}")
            return assistant_message
        else:
            logger.error(f"❌ Ошибка GigaChat: {response.status_code} - {response.text}")
            return "Извините, не смог обработать ваш запрос. Попробуйте ещё раз."
    except Exception as e:
        logger.error(f"❌ Исключение при запросе: {e}")
        return f"Ошибка: {str(e)}"

# ОБРАБОТЧИКИ КОМАНД

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    welcome_message = (
        "👋 Привет! Я AI помощник вашей семьи.\n\n"
        "🤖 Я могу помочь с:\n"
        "• Советами и рекомендациями\n"
        "• Планированием и организацией\n"
        "• Ответами на вопросы\n"
        "• Генерацией идей\n\n"
        "Просто напишите мне любое сообщение!\n\n"
        "Команды:\n"
        "/help - справка\n"
        "/clear - очистить память\n"
        "/about - информация о боте"
    )
    await update.message.reply_text(welcome_message)
    logger.info(f"👤 Новый пользователь: {update.effective_user.id}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = (
        "📋 Справка по командам:\n\n"
        "/start - начать\n"
        "/help - эта справка\n"
        "/clear - очистить историю диалога\n"
        "/about - информация о боте\n\n"
        "💬 Просто пишите сообщения, я отвечу!"
    )
    await update.message.reply_text(help_text)

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /about"""
    about_text = (
        "ℹ️ О боте:\n\n"
        "🤖 Семейный AI агент\n"
        "⚙️ На основе: GigaChat (Sberbank)\n"
        "🌍 Работает: 24/7 в облаке Railway\n"
        "💾 Память: Запоминает контекст диалога\n"
        "🇷🇺 Язык: Русский\n\n"
        "Создан для семейного чата Telegram ❤️"
    )
    await update.message.reply_text(about_text)

async def clear_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очистить историю диалога пользователя"""
    user_id = update.effective_user.id
    if user_id in dialogs:
        dialogs[user_id] = []
        logger.info(f"🗑️ История диалога очищена для {user_id}")
        await update.message.reply_text("✅ История диалога очищена")
    else:
        await update.message.reply_text("История уже пуста")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик обычных сообщений"""
    user_id = update.effective_user.id
    message_text = update.message.text
    username = update.effective_user.username or f"user_{user_id}"
    
    logger.info(f"💬 Новое сообщение от @{username}: {message_text[:50]}...")
    
    # Показываем, что бот печатает
    await update.message.chat.send_action("typing")
    
    # Получаем ответ от GigaChat
    response = ask_gigachat(message_text, user_id)
    
    # Отправляем ответ
    await update.message.reply_text(response)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

def main():
    """Главная функция запуска бота"""
    logger.info("🚀 Запуск AI агента...")
    
    # Создаем приложение Telegram
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("clear", clear_dialog))
    
    # Обработчик обычных сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Используем Webhook вместо Polling (лучше для облака)
    # Railway автоматически устанавливает переменную PORT
    logger.info(f"⚙️ Запуск на порту {PORT}...")
    
    application.run_polling()


if __name__ == '__main__':
    try:
        logger.info("=" * 50)
        logger.info("СЕМЕЙНЫЙ AI АГЕНТ НА GIGACHAT")
        logger.info("=" * 50)
        main()
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        raise
