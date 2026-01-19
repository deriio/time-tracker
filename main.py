import os
import json
import logging
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.types import Message
from aiogram.filters import Command
from typing import Callable, Dict, Any, Awaitable, Union

from sheets_manager import GoogleSheetManager

# Load environment variables
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_JSON_PATH = os.getenv("GOOGLE_JSON_PATH")
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID")
TEMPLATE_FILE_ID = os.getenv("TEMPLATE_FILE_ID")

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
USER_CACHE = {} # Normalized Username -> Full Name
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
    USER_CACHE, _, ALL_NAMES_SET = sheet_manager.get_users_from_template()
    logger.info(f"Loaded {len(USER_CACHE)} users and {len(ALL_NAMES_SET)} names.")
    
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
        
        user = event.from_user
        if not user:
            return

        # Check if it is a command /update
        is_update_command = event.text and event.text.startswith("/update")

        if is_update_command:
            # Allow pass-through for handler to check admin rights
            return await handler(event, data)

        if not user.username:
            await event.answer(f"Access denied. You must have a Telegram Username set.")
            return

        username = user.username.lower()
        
        # Check against cache OR Delegates
        if username in USER_CACHE:
             data["user_name"] = USER_CACHE[username]
             return await handler(event, data)
        
        if username in DELEGATE_USERNAMES:
             data["user_name"] = f"Delegate (@{username})" # Fallback name
             return await handler(event, data)
        
        # Access Denied
        await event.answer(f"Access denied. Username: @{user.username}")
        logger.warning(f"Unauthorized access attempt: @{user.username}")
        return

# Bot initialization
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Apply middleware
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
            # Pass final_user_name instead of the sender's own name if delegated
            sheet_manager.append_log(final_user_name, user_id, final_username_log)
            
            time_str = sheet_manager._get_moscow_time().strftime('%H:%M')
            await message.reply(f"✅ Check-in/out recorded for {final_user_name} at {time_str}")
        else:
            await message.reply("⚠️ System Error: Database connection failed.")
            
    except Exception as e:
        logger.error(f"Error processing photo: {e}")
        await message.reply("❌ Error recording data. Please contact admin.")

# Handler for /update
@dp.message(Command("update"))
async def handle_update(message: Message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        # Ignore or deny
        # Since middleware skipped auth for /update, we must deny unauthorized users here
        # But if they are regular users, they shouldn't call it either.
        await message.reply("⛔ Admin access required.")
        return

    await message.reply("🔄 Updating users from Master Template...")
    try:
        global USER_CACHE, ALL_NAMES_SET
        # 1. Refresh Cache
        users_dict, raw_rows, all_names_set = sheet_manager.get_users_from_template()
        USER_CACHE = users_dict
        ALL_NAMES_SET = all_names_set
        
        # 2. Sync to Current Month
        sync_result = sheet_manager.sync_users_to_current_month(raw_rows)
        
        await message.reply(f"✅ Success.\nCache: {len(USER_CACHE)} users.\nNames: {len(ALL_NAMES_SET)}\nSync: {sync_result}")
        
    except Exception as e:
        await message.reply(f"❌ Update failed: {e}")
    

# Handler for Text
@dp.message(F.text & ~Command("update"))
async def handle_text(message: Message):
    await message.reply("Please send a photo to check in/out.")

async def main():
    logger.info("Starting bot...")
    logger.info(f"Admins: {ADMIN_IDS}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
