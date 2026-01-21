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

try:
    if not all([BOT_TOKEN, GOOGLE_JSON_PATH, DRIVE_FOLDER_ID, TEMPLATE_FILE_ID]):
        logger.error("Missing environment variables. Please check .env file.")
    
    logger.info(f"DEBUG: Using Drive Folder ID: {DRIVE_FOLDER_ID}")
    
    sheet_manager = GoogleSheetManager(
        json_path=GOOGLE_JSON_PATH,
        drive_folder_id=DRIVE_FOLDER_ID,
        template_file_id=TEMPLATE_FILE_ID
    )
    
    # Initial Cache Load
    logger.info("Loading authorized users from Google Sheet...")
    # Load via v2 logic to get IDs
    users_v2 = sheet_manager.get_users_v2()
    USER_CACHE_ID = {int(u["tg_id"]): u["name"] for u in users_v2 if u["tg_id"].isdigit()}
    USER_CACHE_UNAME = {u["username"]: u["name"] for u in users_v2 if u["username"]}
    ALL_NAMES_SET = {u["name"] for u in users_v2 if u["status"] == "active"}
    
    logger.info(f"Loaded {len(USER_CACHE_ID)} IDs, {len(USER_CACHE_UNAME)} usernames, {len(ALL_NAMES_SET)} names.")
    
except Exception as e:
    logger.critical(f"Initialization Failed: {e}")

# Global Constants
DELEGATE_USERNAMES = ["michael_kostyuhjn", "r2d2kzn"]

# Middleware for Authorization
class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        # Skip auth for /update command if intended for admins to fix things
        # But we still need to know who is sending it.
        # Actually, let's process auth normally, but handle 'access denied' carefully.
        # However, for the /update command, if the admin is NOT in the user sheet, they can't run it?
        # Let's exempt ADMIN_IDS from the list check, OR ensure admins are in the sheet.
        # Better: Check ADMIN_IDS logic in the handler, but this middleware blocks everything.
        # Optimization: If it's a command /update, check ADMIN_IDS and bypass user cache.
        
        # HYPER-VERBOSE LOGGING FOR DEBUG
        update_info = f"Update:{event.message_id} from:{event.from_user.id}"
        if hasattr(event, 'text') and event.text: update_info += f" text:{event.text[:20]}"
        if hasattr(event, 'web_app_data') and event.web_app_data: update_info += " [WEB_APP_DATA PRESENT]"
        logger.info(f"MW START: {update_info}")

        user = event.from_user
        if not user:
            return await handler(event, data)

        # Exempt specific commands from middleware
        is_bypass = False
        if hasattr(event, "web_app_data") and event.web_app_data:
            logger.info(f"MW BYPASS: WebApp data detected")
            is_bypass = True
        
        try:
            if hasattr(event, "text") and event.text:
                if event.text.startswith(("/update", "/setup_checkin", "/debug_users")):
                    logger.info(f"MW BYPASS: Command {event.text.split()[0]} detected")
                    is_bypass = True
        except:
            pass

        if is_bypass:
            return await handler(event, data)

        # Priority 1: Check by Telegram ID
        if user.id in USER_CACHE_ID:
            data["user_name"] = USER_CACHE_ID[user.id]
            return await handler(event, data)

        # Priority 2: Check by Username
        if user.username:
            username = user.username.lower()
            if username in USER_CACHE_UNAME:
                name = USER_CACHE_UNAME[username]
                # Auto-bind ID for future
                if sheet_manager.bind_telegram_id(user.id, name):
                    USER_CACHE_ID[user.id] = name
                    logger.info(f"Auto-bound ID {user.id} to {name} via username @{username}")
                data["user_name"] = name
                return await handler(event, data)

        # Access Denied (Will be handled by WebApp "Claim" flow later)
        # For direct messages/photos, we still deny.
        if event.photo or (event.text and not event.text.startswith("/")):
            await event.answer(f"Access denied. Please use the Web App button to register.")
            logger.warning(f"Unauthorized access attempt: {user.id} (@{user.username})")
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
        # event is Update here
        logger.info(f"OUTER MW: Incoming Update {event.update_id}")
        if event.message:
            ct = event.message.content_type
            logger.info(f"OUTER MW: Message ContentType: {ct}")
            if event.message.web_app_data:
                logger.info(f"OUTER MW: WEB_APP_DATA detected: {event.message.web_app_data.data[:50]}...")
        return await handler(event, data)

# Bot initialization
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Apply middleware
dp.update.outer_middleware(OuterLoggerMiddleware())
dp.message.middleware(AuthMiddleware())

# Handler for Photos
@dp.message(F.photo)
async def handle_photo(message: Message, user_name: str):
    try:
        user_id = message.from_user.id
        username = message.from_user.username
        
        # Delegate logic (DELEGATE_USERNAMES is global)
        final_user_name = user_name
        final_username_log = f"@{username}"

        if username and username.lower() in DELEGATE_USERNAMES:
            caption = message.caption or ""
            # Check if any known user's name is in the caption
            # Sort by length descending to match longest name first (to avoid partial matches if names overlap)
            # We filter out empty names just in case
            all_names = sorted([name for name in ALL_NAMES_SET if name], key=len, reverse=True)
            
            for name in all_names:
                if name.lower() in caption.lower():
                    final_user_name = name
                    final_username_log = f"@{username} (for {name})"
                    logger.info(f"Delegate {username} reporting for {name}")
                    break
        
        logger.info(f"Received photo from {final_user_name} ({final_username_log})")
        
        if sheet_manager:
            # We no longer allow logging via direct photo in chat to avoid errors/shifts
            await message.reply("⚠️ Прямая отправка фото отключена. \nПожалуйста, используйте кнопку **📸 Отметить Приход/Уход** выше.")
            logger.info(f"Blocked direct photo log attempt from {user_name}")
        else:
            await message.reply("⚠️ System Error: Database connection failed.")
            
    except Exception as e:
        logger.error(f"Error processing photo: {e}")
        await message.reply("❌ Error recording data. Please contact admin.")

@dp.message(Command("debug_users"))
async def handle_debug_users(message: Message):
    if message.from_user.id not in ADMIN_IDS: return
    users = sheet_manager.get_users_v2()
    logger.info(f"--- USER DEBUG DUMP ---")
    active_count = 0
    for u in users:
        status_norm = u['status'].strip().lower()
        if status_norm == "active": active_count += 1
        logger.info(f"Name: [{u['name']}], Status: [{u['status']}], Role: [{u['role']}]")
    logger.info(f"--- END DUMP. Total: {len(users)}, Active: {active_count} ---")
    await message.reply(f"Dumped {len(users)} users. Active: {active_count}.")

@dp.message(Command("setup_checkin"))
async def handle_setup(message: Message, bot: Bot):
    if message.from_user.id not in ADMIN_IDS:
        logger.warning(f"Admin access denied for User ID: {message.from_user.id} (@{message.from_user.username})")
        await message.reply(f"⛔ Admin access required.\n(Your ID: {message.from_user.id})")
        return

    import json
    import base64
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
    
    # 1. Prepare Data
    user_id = message.from_user.id
    users_v2 = sheet_manager.get_users_v2()
    super_ids = [u["tg_id"] for u in users_v2 if u["role"].lower() == "supervisor" and u["tg_id"]]
    all_super_ids = list(set(super_ids + [str(i) for i in ADMIN_IDS]))
    is_super = str(user_id) in all_super_ids
    
    def b64_safe(data):
        j = json.dumps(data, separators=(',', ':'), ensure_ascii=False)
        return base64.urlsafe_b64encode(j.encode('utf-8')).decode('ascii').rstrip('=')

    # Pass everything in the URL
    final_params = []
    if is_super:
        active_names = [u["name"] for u in users_v2 if u["status"].strip().lower() == "active"]
        final_params.append(f"e={b64_safe(active_names)}")
        final_params.append("s=1")
    else:
        orphan_names = sheet_manager.get_orphan_users()
        final_params.append(f"o={b64_safe(orphan_names)}")
    
    # CRITICAL: Pass current Group ID
    final_params.append(f"g={message.chat.id}")
    
    # Pass webhook server URL for photo upload
    if WEBHOOK_SERVER_URL:
        webhook_endpoint = WEBHOOK_SERVER_URL.rstrip('/') + "/api/checkin"
        final_params.append(f"w={webhook_endpoint}")

    
    query_str = "v=5.0&" + "&".join(final_params)
    final_url = f"{WEBAPP_URL}?{query_str}"

    # Use URL button for group compatibility (web_app not allowed in inline keyboards in groups)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 Открыть терминал учета", url=final_url)]
    ])
    
    msg = await message.answer(
        "🏭 **Терминал Учёта Времени**\n\n"
        "Чтобы отметиться, нажмите кнопку ниже.\n"
        "Камера откроется прямо здесь.",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    try:
        if message.chat.type != "private":
            await msg.pin(disable_notification=True)
    except:
        pass

# /start handler
@dp.message(CommandStart())
async def handle_start(message: Message):
    await message.answer("Бот запущен. Пожалуйста, используйте кнопку в группе.")

# Cleanup legacy handlers
@dp.callback_query(F.data == "start_flow")
async def handle_start_flow(callback: CallbackQuery):
    await callback.answer("Пожалуйста, используйте основную кнопку в закрепе.", show_alert=True)

# Handler for /update
@dp.message(Command("update"))
async def handle_update(message: Message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.reply("⛔ Admin access required.")
        return

    await message.reply("🔄 Updating users from Master Template...")
    try:
        global USER_CACHE_ID, USER_CACHE_UNAME, ALL_NAMES_SET
        users_v2 = sheet_manager.get_users_v2()
        USER_CACHE_ID = {int(u["tg_id"]): u["name"] for u in users_v2 if u["tg_id"].isdigit()}
        USER_CACHE_UNAME = {u["username"]: u["name"] for u in users_v2 if u["username"]}
        ALL_NAMES_SET = {u["name"] for u in users_v2 if u["status"] == "active"}
        
        # Sync to Current Month (legacy rows support)
        raw_rows = [[u["name"], "@"+u["username"]] for u in users_v2]
        sync_result = sheet_manager.sync_users_to_current_month(raw_rows)
        
        await message.reply(f"✅ Success.\nIDs: {len(USER_CACHE_ID)}\nUsernames: {len(USER_CACHE_UNAME)}\nNames: {len(ALL_NAMES_SET)}\n{sync_result}")
    except Exception as e:
        await message.reply(f"❌ Update failed: {e}")

# Handler for WebApp Data (Robust Filter)
@dp.message(lambda m: m.web_app_data is not None)
async def handle_webapp_data(message: Message):
    logger.info(f"RECEIVED WebApp Data from {message.from_user.id}: {message.web_app_data.data[:100]}...")
    try:
        data = json.loads(message.web_app_data.data)
        user_id = message.from_user.id
        action = data.get("action")

        if action in ["check_in", "check_out"]:
            await process_web_check(message, data, user_id)
        elif action == "claim":
            await process_web_claim(message, data, user_id)
        else:
            await message.answer("❌ Unknown action")
    except Exception as e:
        logger.error(f"WebAppData error: {e}")
        await message.answer("❌ Error processing Web App data.")

async def process_web_check(message: Message, data: dict, user_id: int):
    # Import RemoveKeyboard here
    from aiogram.types import ReplyKeyboardRemove
    
    image_data = data.get("image")
    target_info = data.get("target_user_id") or user_id
    action = data["action"]

    # 1. Handle Photo (only HTTP URL supported now)
    status_msg = await message.answer("⌛ Обработка...", reply_markup=ReplyKeyboardRemove()) # REMOVE KEYBOARD HERE
    
    photo_url = None
    if image_data and image_data.startswith("http"):
        photo_url = image_data
        logger.info(f"Using direct photo URL: {photo_url}")
    else:
        logger.error(f"Invalid photo data: expected HTTP URL, got: {type(image_data)}")
        await message.answer("❌ Ошибка: фото должно быть загружено на сервер. Попробуйте еще раз.")
        return

    # 2. Get Employee Info
    employee_name = None
    target_tg_id = None

    if isinstance(target_info, str) and not target_info.isdigit():
        # It's a name (from Supervisor dropdown)
        employee_name = target_info
        # Try to find their TG ID in cache
        for tid, name in USER_CACHE_ID.items():
            if name == employee_name:
                target_tg_id = tid
                break
    else:
        # It's a TG ID
        target_tg_id = int(target_info)
        employee_name = USER_CACHE_ID.get(target_tg_id)
        if not employee_name:
            # Fallback to DB fetch
            users = sheet_manager.get_users_v2()
            for u in users:
                if u["tg_id"] == str(target_tg_id):
                    employee_name = u["name"]
                    break
    
    if not employee_name:
        await message.answer("❌ Error: Employee not found in database.")
        return

    # 3. Determine submitter (Supervisor mode)
    submitted_by = ""
    if str(target_tg_id) != str(user_id):
        submitter_name = USER_CACHE_ID.get(user_id, f"ID:{user_id}")
        submitted_by = submitter_name

    # 4. Log to Sheets
    log_type = "Приход" if action == "check_in" else "Уход"
    sheet_manager.append_log(
        user_name=employee_name,
        telegram_id=target_tg_id,
        log_type=log_type,
        photo_url=photo_url,
        submitted_by=submitted_by
    )

    # 5. Notify Group/User
    time_str = sheet_manager._get_moscow_time().strftime('%H:%M')
    status_emoji = "🟢" if action == "check_in" else "🔴"
    status_text = "НАЧАЛ РАБОТУ" if action == "check_in" else "ЗАКОНЧИЛ РАБОТУ"
    
    caption = f"{status_emoji} **{employee_name}** {status_text}\n🕒 {time_str}"
    if submitted_by:
        caption += f"\n✅ Подтверждено: {submitted_by}"
    
    # Determine where to send the report
    target_chat = data.get("group_id") or message.chat.id
    photo_filename = data.get("photo_filename")  # Get filename for deletion after sending
    
    try:
        await message.bot.send_photo(chat_id=target_chat, photo=photo_url, caption=caption, parse_mode="Markdown")
        if str(target_chat) != str(message.chat.id):
            await message.answer("✅ Отчет успешно отправлен в группу.")
        
        # Delete photo from webhook server after successful send
        if photo_filename and WEBHOOK_SERVER_URL:
            try:
                async with httpx.AsyncClient() as client:
                    delete_url = f"{WEBHOOK_SERVER_URL.rstrip('/')}/api/photos/{photo_filename}"
                    delete_resp = await client.delete(delete_url, timeout=5.0)
                    if delete_resp.status_code == 200:
                        logger.info(f"Photo deleted from server: {photo_filename}")
                    else:
                        logger.warning(f"Failed to delete photo {photo_filename}: {delete_resp.status_code}")
            except Exception as e_delete:
                logger.error(f"Error deleting photo {photo_filename}: {e_delete}")
                # Non-critical error, continue
    except Exception as e_photo:
        logger.error(f"Failed to send photo back: {e_photo}")
        # Fallback to text only
        caption_fallback = caption + "\n⚠️ (Фото сохранено в архиве)"
        await message.answer(caption_fallback, parse_mode="Markdown")
    
    # Cleanup status message if possible
    try:
        await status_msg.delete()
    except:
        pass

async def process_web_claim(message: Message, data: dict, user_id: int):
    from aiogram.types import ReplyKeyboardRemove # Import for cleanup
    
    selected_name = data.get("full_name")
    if not selected_name: return

    if sheet_manager.bind_telegram_id(user_id, selected_name):
        USER_CACHE_ID[user_id] = selected_name
        
        # Notify Group
        user_display = f"@{message.from_user.username}" if message.from_user.username else f"ID:{user_id}"
        await message.answer(
            f"✅ Аккаунт успешно привязан к: **{selected_name}**", 
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove() # Clean up keyboard
        )
        
        # Public notification in current chat (group)
        claim_msg = (f"⚠️ **Системное уведомление**\n"
                     f"Пользователь {user_display} привязал свой аккаунт к сотруднику: **{selected_name}**")
        await message.answer(claim_msg, parse_mode="Markdown")
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
