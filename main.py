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
    CallbackQuery
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
        
        logger.info(f"Cache Refreshed: {len(USER_CACHE_ID)} IDs, {len(USER_CACHE_UNAME)} usernames.")
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

        # Bypass for system commands
        if hasattr(event, "text") and event.text and event.text.startswith(("/update", "/setup_checkin")):
            return await handler(event, data)

        tg_id = str(user.id)
        username = user.username.lower() if user.username else ""
        
        # 1. Check ID in cache
        user_data = USER_CACHE_ID.get(tg_id)
        
        # 2. Check Username in cache (and Auto-bind)
        if not user_data and username:
            user_data = USER_CACHE_UNAME.get(username)
            if user_data:
                # Auto-bind ID in Sheets and Update Cache
                bound_user = sheet_manager.auto_bind_user(username, tg_id)
                if bound_user:
                    user_data = bound_user
                    USER_CACHE_ID[tg_id] = user_data
                    logger.info(f"Smart Auth: Auto-bound @{username} to ID {tg_id}")

        if user_data:
            data["user_name"] = user_data["name"]
            data["user_role"] = user_data["role"]
            return await handler(event, data)

        # 3. Handle Unauthorized/Orphans
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
        # Optionally sync to current month too as requested in legacy
        try:
            users_list = sheet_manager.get_users_v2()
            raw_rows = [[u["name"], "@"+u["username"]] for u in users_list]
            sync_result = sheet_manager.sync_users_to_current_month(raw_rows)
            await message.reply(f"✅ Успешно.\nПользователей: {len(ALL_NAMES_SET)}\n{sync_result}")
        except Exception as e:
            await message.reply(f"✅ Кэш обновлен, но синхронизация месяца не удалась: {e}")
    else:
        await message.reply("❌ Ошибка при обновлении кэша.")

@dp.message(Command("setup_checkin"))
async def handle_setup(message: Message, bot: Bot):
    if message.from_user.id not in ADMIN_IDS:
        logger.warning(f"Admin access denied for {message.from_user.id}")
        return

    import json
    import base64
    
    # Refresh cache to ensure we have latest IDs and Orphans
    refresh_user_cache()
    
    def b64_safe(data):
        j = json.dumps(data, separators=(',', ':'), ensure_ascii=False)
        return base64.urlsafe_b64encode(j.encode('utf-8')).decode('ascii').rstrip('=')

    params = []
    
    # 1. Active Users with roles
    users_v2 = sheet_manager.get_users_v2()
    active_users = []
    for u in users_v2:
        if u["status"] == "active":
            tid = str(u["tg_id"]) if u["tg_id"] else ""
            role_char = "s" if u["role"] == "supervisor" else "e"
            active_users.append([tid, u["name"], role_char])
    
    # Add Admins as Supervisors just in case
    reg_ids = {u[0] for u in active_users if u[0]}
    for aid in ADMIN_IDS:
        if str(aid) not in reg_ids:
            active_users.append([str(aid), "АДМИНИСТРАТОР", "s"])

    params.append(f"users={b64_safe(active_users)}")
    
    # 2. Orphans (names without IDs)
    orphan_names = [u["name"] for u in users_v2 if not u["tg_id"] and u["status"] == "active"]
    params.append(f"orphans={b64_safe(orphan_names)}")
    
    # 3. Context
    params.append(f"g={message.chat.id}")
    if WEBHOOK_SERVER_URL:
        params.append(f"w={WEBHOOK_SERVER_URL.rstrip('/')}/api/checkin")

    query_str = "v=11.0&" + "&".join(params) # Upgraded to 11.0
    final_url = f"{WEBAPP_URL.rstrip('/')}/?{query_str}"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 Открыть терминал учета", url=final_url)]
    ])
    
    msg = await message.answer(
        "🏭 **Терминал Учёта Времени**\n\nЧтобы отметиться, нажмите кнопку ниже.\nКамера откроется прямо здесь.",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    if message.chat.type != "private":
        try: await msg.pin(disable_notification=True)
        except: pass

@dp.message(CommandStart())
async def handle_start(message: Message):
    await message.answer("Бот запущен. Пожалуйста, используйте кнопку в своей группе.")

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

    status_msg = await message.answer("⌛ Обработка...", reply_markup=ReplyKeyboardRemove())
    
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

    # 4. Log to Sheets
    log_type = "Приход" if action == "check_in" else "Уход"
    try:
        sheet_manager.append_log(
            user_name=employee_name,
            telegram_id=target_tg_id,
            log_type=log_type,
            photo_url=photo_url,
            submitted_by=submitted_by
        )
    except Exception as log_err:
        logger.error(f"Append log failed: {log_err}")
        await message.answer("⚠️ Ошибка записи в таблицу, но я попробую отправить фото.")

    # 5. Notify Group/User
    time_str = sheet_manager._get_moscow_time().strftime('%H:%M')
    status_emoji = "🟢" if action == "check_in" else "🔴"
    status_text = "НАЧАЛ РАБОТУ" if action == "check_in" else "ЗАКОНЧИЛ РАБОТУ"
    
    caption = f"{status_emoji} **{employee_name}** {status_text}\n🕒 {time_str}"
    if submitted_by:
        caption += f"\n✅ Подтверждено бригадиром: {submitted_by}"
    
    target_chat = data.get("group_id") or message.chat.id
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
            reply_markup=ReplyKeyboardRemove()
        )
        logger.info(f"User {user_id} claimed {selected_name}")
    else:
        await message.answer("❌ Ошибка привязки аккаунта.", reply_markup=ReplyKeyboardRemove())
    


# Handler for all other text messages
@dp.message(F.text)
async def handle_text(message: Message):
    # Only reply if it's not a command (usually handled by other handlers)
    if message.text.startswith("/"):
        return
    await message.reply("Пожалуйста, отправьте фото, чтобы отметиться, или используйте кнопку в меню.")

@dp.message()
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
