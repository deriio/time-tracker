import os
import json
import logging
import asyncio
import httpx
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, 
    ContentType, 
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    WebAppInfo, 
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    MenuButtonWebApp,
    ChatMemberUpdated
)
from typing import Callable, Dict, Any, Awaitable, Union

from sheets_manager import GoogleSheetManager
from validators import validate_webapp_data

# Load environment variables
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_JSON_PATH = os.getenv("GOOGLE_JSON_PATH")
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID")
TEMPLATE_FILE_ID = os.getenv("TEMPLATE_FILE_ID")
WEBAPP_URL = os.getenv("WEBAPP_URL")
WEBHOOK_SERVER_URL = os.getenv("WEBHOOK_SERVER_URL", "http://localhost:8000")

# Admin IDs handling
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(id_str.strip()) for id_str in ADMIN_IDS_STR.split(",") if id_str.strip().isdigit()]

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ],
    force=True
)
logger = logging.getLogger(__name__)

# Initialize dependencies
sheet_manager = None
USER_CACHE_ID = {} # TG ID (int) -> Full Name
USER_CACHE_UNAME = {} # Normalized Username -> Full Name
ALL_NAMES_SET = set() # Set of all valid names

# Initial Cache Load Helper
def refresh_user_cache():
    global USER_CACHE_ID, USER_CACHE_UNAME, ALL_NAMES_SET
    try:
        logger.info("Refreshing user cache from Google Sheet...")
        users_v2 = sheet_manager.get_users_v2()
        
        # New cache structure: store full user objects
        USER_CACHE_ID = {str(u["tg_id"]): u for u in users_v2 if u["tg_id"]}
        USER_CACHE_UNAME = {u["username"]: u for u in users_v2 if u["username"]}
        ALL_NAMES_SET = {u["name"] for u in users_v2 if u["status"] == "active"}
        
        logger.info(f"Cache Refreshed: {len(USER_CACHE_ID)} IDs, {len(USER_CACHE_UNAME)} usernames, {len(ALL_NAMES_SET)} names.")
        return True
    except Exception as e:
        logger.error(f"Cache refresh failed: {e}")
        return False

# Initialize Global Manager and Cache
try:
    if not all([BOT_TOKEN, GOOGLE_JSON_PATH, DRIVE_FOLDER_ID, TEMPLATE_FILE_ID]):
        logger.error("Missing critical environment variables.")
    
    sheet_manager = GoogleSheetManager(
        json_path=GOOGLE_JSON_PATH, 
        drive_folder_id=DRIVE_FOLDER_ID, 
        template_file_id=TEMPLATE_FILE_ID
    )
    refresh_user_cache()
except Exception as e:
    logger.critical(f"Initialization Failed: {e}")

# Middleware for Authorization & Identification
class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        user = event.from_user
        if not user or not sheet_manager:
            return await handler(event, data)

        if event.chat.type != "private":
            # In groups, only allow commands if they are from an admin
            if event.text and event.text.startswith("/") and user.id in ADMIN_IDS:
                return await handler(event, data)
            return

        tg_id = str(user.id)
        raw_username = user.username or ""
        norm_username = sheet_manager.normalize_username(raw_username)
        
        # 1. Check ID in cache
        user_data = USER_CACHE_ID.get(tg_id)
        
        # 2. Check Username in cache (and Auto-bind)
        if not user_data and norm_username:
            user_data = USER_CACHE_UNAME.get(norm_username)
            if user_data:
                # Auto-bind ID in Sheets and Update Cache
                bound_user = sheet_manager.auto_bind_user(norm_username, tg_id)
                if bound_user:
                    user_data = bound_user
                    USER_CACHE_ID[tg_id] = user_data
                    logger.info(f"Smart Auth: Auto-bound @{norm_username} to ID {tg_id}")

        if user_data:
            data["user_name"] = user_data["name"]
            data["user_role"] = user_data["role"]
            return await handler(event, data)

        # 3. Handle Unauthorized/Orphans (Private chats only)
        if event.photo or (event.text and not event.text.startswith("/")):
            await event.answer("⚠️ Вы не авторизованы. Нажмите на кнопку под сообщением терминала, чтобы привязать аккаунт.")
            return

        return await handler(event, data)

# Outer Middleware for Raw Updates
class OuterLoggerMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any]
    ) -> Any:
        # logging excluded for brevity
        return await handler(event, data)

# Bot initialization
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Apply middleware
dp.update.outer_middleware(OuterLoggerMiddleware())
dp.message.middleware(AuthMiddleware())

# Fresh Cache Command
@dp.message(Command("update"))
async def handle_update(message: Message):
    if message.from_user.id not in ADMIN_IDS: return
    if refresh_user_cache():
        await message.reply("✅ База пользователей обновлена.")
    else:
        await message.reply("❌ Ошибка обновления базы.")

# Admin Tools
@dp.message(Command("debug_users"))
async def handle_debug_users(message: Message):
    if message.from_user.id not in ADMIN_IDS: return
    users = sheet_manager.get_users_v2()
    logger.info(f"--- USER DEBUG DUMP ---")
    for u in users:
        logger.info(f"Name: [{u['name']}], ID: [{u['tg_id']}], Role: [{u['role']}]")
    await message.reply(f"Dumped {len(users)} users to log.")

@dp.message(Command("update"))
async def handle_update_full(message: Message):
    if message.from_user.id not in ADMIN_IDS: return
    await message.reply("🔄 Обновление базы из таблиц...")
    if refresh_user_cache():
        # Sync users to current month folders for both departments
        try:
            users_list = sheet_manager.get_users_v2()
            sync_result = sheet_manager.sync_users_to_current_month(users_list)
            await message.reply(f"✅ Успешно.\nПользователей: {len(ALL_NAMES_SET)}\n{sync_result}")
        except Exception as e:
            await message.reply(f"✅ Кэш обновлен, но синхронизация не удалась: {e}")
    else:
        await message.reply("❌ Ошибка при обновлении кэша.")

# Helper for dynamic WebApp URL
def get_webapp_url(user_id, chat_id=None):
    if not WEBAPP_URL or not WEBHOOK_SERVER_URL:
        return None
    base_url = WEBAPP_URL.rstrip("/")
    uid = str(user_id)
    cid = str(chat_id) if chat_id else uid
    import time
    return f"{base_url}/index.html?g={cid}&w={WEBHOOK_SERVER_URL}/api/checkin&u={uid}&v={int(time.time())}"

def get_main_keyboard(user_id, chat_id=None):
    url = get_webapp_url(user_id, chat_id)
    if not url: return None
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📸 Сделать отчет", web_app=WebAppInfo(url=url))]
        ],
        resize_keyboard=True,
        is_persistent=True
    )

@dp.message(Command("setup_checkin"))
async def handle_setup(message: Message, bot: Bot):
    if message.from_user.id not in ADMIN_IDS:
        logger.warning(f"Admin access denied for {message.from_user.id}")
        return

    webapp_final_url = get_webapp_url(message.from_user.id, message.chat.id)
    if not webapp_final_url:
        return await message.answer("❌ WEBAPP_URL or WEBHOOK_SERVER_URL not set in .env")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📸 Сделать отчет", 
            web_app=WebAppInfo(url=webapp_final_url)
        )]
    ])

    msg = await message.answer(
        "🏰 **Терминал Учёта Времени**\n\n"
        "Чтобы отметиться, нажмите кнопку ниже.\n"
        "Камера откроется прямо здесь.",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    logger.info(f"Generated secure MiniApp button for Chat:{message.chat.id}")
    if message.chat.type != "private":
        try: await msg.pin(disable_notification=True)
        except: pass

@dp.message(CommandStart())
async def handle_start(message: Message, bot: Bot):
    url = get_webapp_url(message.from_user.id, message.chat.id)
    if not url:
        return await message.answer("❌ Бот не настроен (URL).")

    # 1. Reply Keyboard (Persistent big button)
    kb = get_main_keyboard(message.from_user.id, message.chat.id)

    # 2. Menu Button (Button next to paperclip)
    try:
        await bot.set_chat_menu_button(
            chat_id=message.chat.id,
            menu_button=MenuButtonWebApp(text="Сделать отчет", web_app=WebAppInfo(url=url))
        )
    except Exception as e:
        logger.warning(f"Failed to set menu button: {e}")

    await message.answer(
        "👋 **Добро пожаловать!**\n\n"
        "Чтобы начать или закончить смену, нажмите кнопку ниже **«Сделать отчет»**.\n"
        "Она всегда доступна в этом чате.",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@dp.message(lambda m: m.web_app_data is not None)
async def handle_webapp_data(message: Message):
    logger.info(f"RECEIVED WebApp Data from {message.from_user.id}")
    try:
        data = json.loads(message.web_app_data.data)
        user_id = message.from_user.id
        action = data.get("action")

        if action in ["check_in", "check_out"]:
            await process_web_check(message, data, user_id)
        elif action == "claim":
            await process_web_claim(message, data, user_id)
    except Exception as e:
        logger.error(f"WebAppData error: {e}")
        await message.answer("❌ Ошибка обработки данных WebApp.")

async def process_web_check(message: Message, data: dict, user_id: int):
    from aiogram.types import ReplyKeyboardRemove
    
    image_data = data.get("image")
    target_info = data.get("target_user_id") or user_id
    action = data["action"]

    status_msg = await message.answer("⌛ Обработка...")
    
    photo_url = None
    if image_data and image_data.startswith("http"):
        photo_url = image_data
    else:
        logger.error(f"Invalid photo data: {type(image_data)}")
        await message.answer("❌ Ошибка: фото должно быть загружено на сервер.")
        return

    # 2. Get Employee Info
    employee_name = None
    target_tg_id = None

    if isinstance(target_info, str) and not target_info.isdigit():
        # It's a name (from Supervisor dropdown)
        employee_name = target_info
        # Try to find their TG ID in cache
        for tid, u_obj in USER_CACHE_ID.items():
            if u_obj["name"] == employee_name:
                target_tg_id = tid
                break
    else:
        # It's a TG ID
        target_tg_id = str(target_info)
        u_obj = USER_CACHE_ID.get(target_tg_id)
        if u_obj:
            employee_name = u_obj["name"]
        else:
            # Fallback search by ID if not in cache (fresh user)
            users_v2 = sheet_manager.get_users_v2()
            for u in users_v2:
                if str(u["tg_id"]) == target_tg_id:
                    employee_name = u["name"]
                    break
    
    if not employee_name:
        await message.answer("❌ Ошибка: Сотрудник не найден в базе.")
        return

    # 3. Determine submitter (Supervisor mode)
    submitted_by = ""
    if str(target_tg_id) != str(user_id):
        submitter_obj = USER_CACHE_ID.get(str(user_id))
        submitted_by = submitter_obj["name"] if submitter_obj else f"ID:{user_id}"

    # 4. Log to Sheets with Team Routing
    log_type = "Приход" if action == "check_in" else "Уход"
    try:
        # Determine team for routing
        target_user = USER_CACHE_ID.get(str(target_tg_id))
        team = target_user["team"] if target_user else "Цех"
        dept = target_user["department"] if target_user else ""
        
        sheet_manager.append_log(
            user_name=employee_name,
            telegram_id=target_tg_id,
            log_type=log_type,
            photo_url=photo_url,
            submitted_by=submitted_by,
            team=team
        )
    except Exception as log_err:
        logger.error(f"Append log failed: {log_err}")
        await message.answer("⚠️ Ошибка записи в таблицу, но я попробую отправить фото.")

    # 5. Notify Group/User with Routing and Hashtags
    time_str = sheet_manager._get_moscow_time().strftime('%H:%M')
    status_emoji = "🟢" if action == "check_in" else "🔴"
    status_text = "НАЧАЛ РАБОТУ" if action == "check_in" else "ЗАКОНЧИЛ РАБОТУ"
    
    # Add Hashtags for Office team
    hashtag = ""
    target_user = USER_CACHE_ID.get(str(target_tg_id))
    user_team = target_user["team"] if target_user else "Цех"
    if user_team == "Офис":
        dept = target_user.get("department", "")
        if dept:
            hashtag = f" #{dept.strip().lower().replace(' ', '_')}"
            
    caption = f"{status_emoji} **{employee_name}** {status_text}{hashtag}\n🕒 {time_str}"
    if submitted_by:
        caption += f"\n✅ Подтверждено бригадиром: {submitted_by}"
    
    # Routing determine target chat
    env_suffix = "WORKSHOP" if user_team == "Цех" else "OFFICE"
    target_chat = os.getenv(f"{env_suffix}_GROUP_ID") or data.get("group_id") or message.chat.id
    photo_filename = data.get("photo_filename")
    
    try:
        await message.bot.send_photo(chat_id=target_chat, photo=photo_url, caption=caption, parse_mode="Markdown")
        if str(target_chat) != str(message.chat.id):
            await message.answer("✅ Отчет успешно отправлен в группу.")
        
        # Cleanup server storage
        if photo_filename and WEBHOOK_SERVER_URL:
            async with httpx.AsyncClient() as client:
                await client.delete(f"{WEBHOOK_SERVER_URL.rstrip('/')}/api/photos/{photo_filename}", timeout=5.0)
    except Exception as e_photo:
        logger.error(f"Report delivery failed: {e_photo}")
        await message.answer(caption + "\n⚠️ (Ошибка отправки в группу)", parse_mode="Markdown")
    
    try: await status_msg.delete()
    except: pass

async def process_web_claim(message: Message, data: dict, user_id: int):
    from aiogram.types import ReplyKeyboardRemove
    selected_name = data.get("full_name")
    if not selected_name: return

    if sheet_manager.bind_telegram_id(user_id, selected_name):
        # Refresh local cache for this user
        refresh_user_cache()
        
        await message.answer(
            f"✅ Аккаунт успешно привязан к: **{selected_name}**", 
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(user_id, message.chat.id)
        )
        logger.info(f"User {user_id} claimed {selected_name}")
    else:
        await message.answer("❌ Ошибка привязки аккаунта.", reply_markup=get_main_keyboard(user_id, message.chat.id))
    


@dp.message(Command("id"))
async def handle_id_command(message: Message):
    """Returns the current chat ID."""
    chat_type = message.chat.type
    await message.answer(
        f"🆔 **ID этого чата:** `{message.chat.id}`\n"
        f"👤 **Ваш ID:** `{message.from_user.id}`\n"
        f"Тип чата: {chat_type}",
        parse_mode="Markdown"
    )
    logger.info(f"ID Request: Chat:{message.chat.id}, User:{message.from_user.id}")

@dp.my_chat_member()
async def on_bot_added(event: ChatMemberUpdated):
    """Triggered when bot is added to a group."""
    if event.new_chat_member.status in ["member", "administrator"]:
        await bot.send_message(
            event.chat.id, 
            f"👋 Привет! Я добавлен в эту группу.\n🆔 **ID этой группы:** `{event.chat.id}`\n"
            "Скопируйте этот ID и вставьте его в .env файл.",
            parse_mode="Markdown"
        )

# Handler for all other text messages (Private chats only)
@dp.message(F.chat.type == "private", F.text)
async def handle_text(message: Message):
    # Only reply if it's not a command (usually handled by other handlers)
    if message.text.startswith("/"):
        return
    await message.reply("Пожалуйста, отправьте фото, чтобы отметиться, или используйте кнопку в меню.")

@dp.message(F.chat.type == "private")
async def handle_fallback(message: Message):
    logger.warning(f"FALLBACK: Unhandled message from {message.from_user.id}. Type: {message.content_type}")
    if message.web_app_data:
         logger.warning("FALLBACK: IT WAS WEB APP DATA! ROUTING FAILED.")

async def main():
    logger.info("Starting bot...")
    logger.info(f"Admins: {ADMIN_IDS}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
