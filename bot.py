from dotenv import load_dotenv
load_dotenv()

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
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from weather import get_lipetsk_weather_data  # импорт из файла weather.py

# ============= КОНФИГУРАЦИЯ =============
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GIGACHAT_CLIENT_ID = os.getenv('GIGACHAT_CLIENT_ID')
GIGACHAT_CLIENT_SECRET = os.getenv('GIGACHAT_CLIENT_SECRET')
GIGACHAT_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGACHAT_API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
GIGACHAT_MODEL = "GigaChat"
MAX_DIALOG_HISTORY = 15
MAX_TOKENS = 512
TEMPERATURE = 0.7
TOP_P = 0.1
REQUEST_TIMEOUT = 30
TOKEN_TIMEOUT = 10

TRIGGERS = [
    "бот,", "@legol_family_bot_ai", "гига,", "вася,", "ai,"
]

# ============= ФУНКЦИЯ ОТПРАВКИ ДЛИННЫХ СООБЩЕНИЙ =============
async def send_long_message(update, text: str):
    max_length = 4096
    parts = [text[i:i+max_length] for i in range(0, len(text), max_length)]
    for part in parts:
        await update.message.reply_text(part)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ============= КЛАСС ДЛЯ ХРАНЕНИЯ ДИАЛОГОВ =============
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
        logger.info(f"Диалог пользователя {user_id} очищен")

    def cache_token(self, token: str):
        self.token_cache["gigachat"] = (token, datetime.now())

    def get_cached_token(self) -> Optional[str]:
        if "gigachat" in self.token_cache:
            token, timestamp = self.token_cache["gigachat"]
            if (datetime.now() - timestamp).seconds < 1800:
                return token
        return None

memory = DialogMemory()

# ============= ФУНКЦИИ GIGACHAT =============
def get_gigachat_token() -> Optional[str]:
    try:
        cached_token = memory.get_cached_token()
        if cached_token:
            logger.debug("Используется кэшированный токен GigaChat")
            return cached_token

        auth_str = f"{GIGACHAT_CLIENT_ID}:{GIGACHAT_CLIENT_SECRET}"
        auth_b64 = base64.b64encode(auth_str.encode()).decode()
        headers = {
            "Authorization": f"Basic {auth_b64}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }
        payload = 'scope=GIGACHAT_API_PERS'
        response = requests.post(
            GIGACHAT_AUTH_URL,
            headers=headers,
            data=payload,
            timeout=TOKEN_TIMEOUT,
            verify=False
        )
        if response.status_code == 200:
            token = response.json().get("access_token")
            memory.cache_token(token)
            logger.info("Токен GigaChat получен успешно")
            return token
        else:
            logger.error(f"Ошибка получения токена GigaChat: {response.status_code} - {response.text}")
            print("DEBUG:", response.text)
            return None
    except Exception as e:
        logger.error(f"Ошибка при получении токена: {e}")
        print("DEBUG ERROR:", e)
        return None

def ask_gigachat(message_text: str, user_id: int) -> str:
    try:
        token = get_gigachat_token()
        if not token:
            return "❌ Ошибка подключения к AI (GigaChat)"
        memory.add_message(user_id, "user", message_text)
        history = memory.get_history(user_id)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": GIGACHAT_MODEL,
            "messages": history,
            "temperature": TEMPERATURE,
            "top_p": TOP_P,
            "max_tokens": MAX_TOKENS
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
            assistant_message = result["choices"][0]["message"]["content"]
            memory.add_message(user_id, "assistant", assistant_message)
            logger.info(f"Ответ отправлен пользователю {user_id}")
            return assistant_message
        else:
            logger.error(f"Ошибка API GigaChat: {response.status_code} - {response.text}")
            print("DEBUG:", response.text)
            return f"❌ Ошибка API ({response.status_code})"
    except requests.exceptions.Timeout:
        logger.error("Таймаут при обращении к GigaChat")
        return "⏱️ Таймаут ответа от AI"
    except requests.exceptions.ConnectionError:
        logger.error("Ошибка подключения к GigaChat")
        return "🔴 Ошибка подключения к AI"
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        print("DEBUG ERROR:", e)
        return f"❌ Ошибка: {str(e)}"

# ============= ОБРАБОТЧИКИ КОМАНД =============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 Привет! Я AI помощник на основе GigaChat.\n\n"
        "🤖 Я могу помочь тебе с:\n"
        "- Ответами на вопросы\n"
        "- Написанием текстов\n"
        "- Объяснением сложных тем\n"
        "- И многим другим!\n"
        "Используй /help для списка команд"
    )
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 Доступные команды:\n\n"
        "/start - Начать работу с ботом\n"
        "/help - Показать это сообщение\n"
        "/clear - Очистить историю диалога\n"
        "/about - Информация о боте\n\n"
        "💬 В семейном чате я отвечаю только на обращения с триггером!"
    )
    await update.message.reply_text(help_text)

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    about_text = (
        "ℹ️ О боте:\n\n"
        "🤖 Family AI Бот\n"
        "AI помощник на основе GigaChat (Сбер)\n"
        "v2.0\nСоздано для помощи и развлечения семьи!"
    )
    await update.message.reply_text(about_text)

async def clear_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    memory.clear_dialog(user_id)
    await update.message.reply_text("✨ История диалога очищена!")

# ============= ОБРАБОТКА СООБЩЕНИЙ С ТРИГГЕРАМИ =============
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text.strip().lower()
    is_triggered = any(message_text.startswith(trigger) for trigger in TRIGGERS)
    if not (is_triggered or message_text.startswith("/")):
        return

    # Курс доллара — ответ как раньше
    if "курс доллара" in message_text or "курс usd" in message_text:
        try:
            resp = requests.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=10)
            data = resp.json()
            usd = data["Valute"]["USD"]
            value = usd["Value"]
            prev = usd["Previous"]
            diff = round(value - prev, 2)
            arrow = "▲" if diff > 0 else "▼" if diff < 0 else "="
            await update.message.reply_text(
                f"💵 Курс доллара (USD/RUB): {value:.2f} руб. ({arrow}{diff:+.2f} руб. за день)"
            )
        except Exception as e:
            await update.message.reply_text(f"Ошибка получения курса: {e}")
        return

    # Погода в Липецке — ответ с живой генерацией
    if "погода" in message_text and "липецк" in message_text:
        temp, feels_like, condition = get_lipetsk_weather_data()
        if "Ошибка" in str(condition):
            await update.message.reply_text(condition)
            return

        condition_human = {
            "clear": "ясно", "partly-cloudy": "малооблачно", "cloudy": "облачно с прояснениями",
            "overcast": "пасмурно", "drizzle": "морось", "light-rain": "небольшой дождь",
            "rain": "дождь", "moderate-rain": "умеренный дождь", "heavy-rain": "сильный дождь",
            "wet-snow": "дождь со снегом", "light-snow": "небольшой снег", "snow": "снег",
            "hail": "град", "thunderstorm": "гроза", "fog": "туман"
        }.get(condition, condition)

        prompt = (
            f"Сделай уникальный, свежий и атмосферный текст о погоде в Липецке прямо сейчас: "
            f"температура {temp}°C, ощущается как {feels_like}°C, состояние: {condition_human}. "
            "Добавь лёгкий юмор, семейную нотку, краткую рекомендацию (без повторов типа тапочки!), чтобы сообщение каждый раз было новым. "
            "Формат — 1-2 абзаца, ярко, живо, не банально."
        )
        reply = ask_gigachat(prompt, update.effective_user.id)
        if len(reply) > 4096:
            await send_long_message(update, reply)
        else:
            await update.message.reply_text(reply)
        return

    # --- Другие вопросы —
    user_id = update.effective_user.id
    try:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=ChatAction.TYPING
        )
        response = ask_gigachat(message_text, user_id)
        if len(response) > 4096:
            await send_long_message(update, response)
        else:
            await update.message.reply_text(response)
    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {e}")
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)

# ============= ПРЕДУСТАНОВКА КОМАНД =============
async def post_init(application: Application):
    try:
        commands = [
            BotCommand("start", "🚀 Начать"),
            BotCommand("help", "📖 Помощь"),
            BotCommand("clear", "✨ Очистить диалог"),
            BotCommand("about", "ℹ️ О боте"),
        ]
        await application.bot.set_my_commands(commands)
        logger.info("Команды бота установлены")
    except Exception as e:
        logger.error(f"Ошибка при установке команд: {e}")

# ============= ОСНОВНОЙ ЗАПУСК =============
def main():
    logger.info("-" * 60)
    logger.info("Запуск Family AI Bot на long polling")
    logger.info("-" * 60)

    if not all([TELEGRAM_TOKEN, GIGACHAT_CLIENT_ID, GIGACHAT_CLIENT_SECRET]):
        logger.error("❌ Не установлены необходимые переменные окружения!")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("clear", clear_dialog))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    application.post_init = post_init
    logger.info(f"✅ Бот запущен в режиме polling")
    application.run_polling()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        raise
