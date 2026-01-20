import os
import json
import base64
import logging
import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from sheets_manager import GoogleSheetManager

# Load environment
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_JSON_PATH = os.getenv("GOOGLE_JSON_PATH")
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID")
TEMPLATE_FILE_ID = os.getenv("TEMPLATE_FILE_ID")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webhook_server")

app = FastAPI()

# Enable CORS (IMPORTANT for WebApp to talk to this server)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Sheets
sheet_manager = GoogleSheetManager(
    json_path=GOOGLE_JSON_PATH,
    drive_folder_id=DRIVE_FOLDER_ID,
    template_file_id=TEMPLATE_FILE_ID
)

@app.post("/api/checkin")
async def handle_checkin(request: Request):
    try:
        data = await request.json()
        photo_b64 = data.get("photo")
        user_id = data.get("user_id")
        group_id = data.get("group_id")
        action = data.get("action")
        employee_name = data.get("employee_name", "Сотрудник")
        target_info = data.get("target_user_id")
        
        logger.info(f"Received {action} from {employee_name} for group {group_id}")

        if not photo_b64:
            return {"ok": False, "error": "No photo"}

        # 1. Decode Image
        photo_bytes = base64.b64decode(photo_b64)

        # 2. Log to Google Sheets (without photo URL as requested)
        try:
            log_type = "Приход" if action == "check_in" else "Уход"
            sheet_manager.append_log(
                user_name=employee_name,
                telegram_id=user_id,
                log_type=log_type,
                photo_url="-" # No storage requested
            )
        except Exception as e_sheet:
            logger.error(f"Sheet log failed: {e_sheet}")

        # 3. Send to Telegram directly
        # We use standard Bot API via httpx
        status_emoji = "🟢" if action == "check_in" else "🔴"
        status_text = "НАЧАЛ РАБОТУ" if action == "check_in" else "ЗАКОНЧИЛ РАБОТУ"
        caption = f"{status_emoji} **{employee_name}** {status_text}"

        async with httpx.AsyncClient() as client:
            files = {'photo': ('photo.jpg', photo_bytes, 'image/jpeg')}
            payload = {
                'chat_id': group_id or user_id, 
                'caption': caption,
                'parse_mode': 'Markdown'
            }
            tg_resp = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                data=payload,
                files=files,
                timeout=30.0
            )
            
            if tg_resp.status_code != 200:
                logger.error(f"Telegram API Error: {tg_resp.text}")
                return {"ok": False, "error": "Telegram failed"}

        return {"ok": True}

    except Exception as e:
        logger.error(f"Server Error: {e}")
        return {"ok": False, "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
