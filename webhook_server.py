import os
import json
import base64
import logging
import httpx
import uuid
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from sheets_manager import GoogleSheetManager

# Load environment
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_JSON_PATH = os.getenv("GOOGLE_JSON_PATH")
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID")
TEMPLATE_FILE_ID = os.getenv("TEMPLATE_FILE_ID")
WEBHOOK_SERVER_URL = os.getenv("WEBHOOK_SERVER_URL", "http://localhost:8000")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webhook_server")

# Create photos directory if it doesn't exist
PHOTOS_DIR = Path("photos")
PHOTOS_DIR.mkdir(exist_ok=True)

app = FastAPI()

# Enable CORS (IMPORTANT for WebApp to talk to this server)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for photos
app.mount("/photos", StaticFiles(directory=str(PHOTOS_DIR)), name="photos")

# Initialize Sheets
sheet_manager = GoogleSheetManager(
    json_path=GOOGLE_JSON_PATH,
    drive_folder_id=DRIVE_FOLDER_ID,
    template_file_id=TEMPLATE_FILE_ID
)

@app.post("/api/upload")
async def upload_photo(request: Request):
    """
    Загружает фото в Base64, сохраняет временно на сервере,
    возвращает публичный URL для доступа к фото.
    """
    try:
        data = await request.json()
        photo_b64 = data.get("image") or data.get("photo")
        
        if not photo_b64:
            raise HTTPException(status_code=400, detail="No photo data provided")
        
        # Remove data URL prefix if present (data:image/jpeg;base64,...)
        if photo_b64.startswith("data:image"):
            photo_b64 = photo_b64.split(",", 1)[1]
        
        # Generate unique filename
        filename = f"{uuid.uuid4().hex}.jpg"
        filepath = PHOTOS_DIR / filename
        
        # Decode and save photo
        try:
            photo_bytes = base64.b64decode(photo_b64)
            filepath.write_bytes(photo_bytes)
            logger.info(f"Photo saved: {filename} ({len(photo_bytes)} bytes)")
        except Exception as e:
            logger.error(f"Failed to decode/save photo: {e}")
            raise HTTPException(status_code=400, detail="Invalid base64 image data")
        
        # Return public URL
        photo_url = f"{WEBHOOK_SERVER_URL.rstrip('/')}/photos/{filename}"
        return {"ok": True, "url": photo_url, "filename": filename}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return {"ok": False, "error": str(e)}

@app.delete("/api/photos/{filename}")
async def delete_photo(filename: str):
    """
    Удаляет фото с сервера после успешной отправки в Telegram.
    """
    try:
        filepath = PHOTOS_DIR / filename
        
        if not filepath.exists():
            logger.warning(f"Photo not found for deletion: {filename}")
            return {"ok": False, "error": "Photo not found"}
        
        filepath.unlink()
        logger.info(f"Photo deleted: {filename}")
        return {"ok": True, "message": "Photo deleted successfully"}
        
    except Exception as e:
        logger.error(f"Delete error: {e}")
        return {"ok": False, "error": str(e)}

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
