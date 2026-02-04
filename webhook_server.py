import os
import json
import base64
import logging
import httpx
import uuid
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
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

# Photo cleanup configuration
PHOTO_TTL_MINUTES = 5
CLEANUP_INTERVAL_SECONDS = 60  # Run every 60 seconds

import hmac
import hashlib
from urllib.parse import parse_qs

# --- Security: Telegram WebApp Validation ---
def verify_telegram_data(init_data: str) -> dict:
    """Validates data received from Telegram WebApp via HMAC-SHA256."""
    if not init_data: return {}
    try:
        vals = {k: v[0] for k, v in parse_qs(init_data).items()}
        hash_val = vals.pop('hash', None)
        if not hash_val: return {}
        
        data_check_string = "\n".join([f"{k}={v}" for k, v in sorted(vals.items())])
        
        # HMAC secret is derived from bot token
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        if calculated_hash != hash_val:
            logger.error("Security Warning: Unauthorized access attempt with invalid hash.")
            return {}
        return json.loads(vals.get('user', '{}'))
    except Exception as e:
        logger.error(f"Telegram validation error: {e}")
        return {}

def get_verified_id(request_data: dict, headers: dict = None) -> str:
    """Helper to extract secure ID from JSON body OR headers."""
    # Priority 1: JSON Body (Most reliable for mobile)
    init_data = request_data.get("_initData")
    
    # Priority 2: Headers (Fallback)
    if not init_data and headers:
        init_data = headers.get("X-Telegram-Init-Data")
        
    if not init_data: return None
    
    user_info = verify_telegram_data(init_data)
    return str(user_info.get("id")) if user_info else None

app = FastAPI()

# Enable CORS with explicit settings for mobile browser compatibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS", "DELETE"],
    allow_headers=["X-Telegram-Init-Data", "Content-Type", "Bypass-Tunnel-Reminder"],
)

# Mount static files for photos
app.mount("/photos", StaticFiles(directory=str(PHOTOS_DIR)), name="photos")

# Initialize Sheets
sheet_manager = GoogleSheetManager(
    json_path=GOOGLE_JSON_PATH,
    drive_folder_id=DRIVE_FOLDER_ID,
    template_file_id=TEMPLATE_FILE_ID
)

# --- Background Photo Cleanup Task ---
async def cleanup_old_photos():
    """Background task to delete photos older than TTL."""
    while True:
        try:
            now = datetime.now()
            cutoff = now - timedelta(minutes=PHOTO_TTL_MINUTES)
            
            deleted_count = 0
            for photo_path in PHOTOS_DIR.glob("*.jpg"):
                # Get file modification time
                mtime = datetime.fromtimestamp(photo_path.stat().st_mtime)
                
                if mtime < cutoff:
                    photo_path.unlink()
                    deleted_count += 1
                    logger.debug(f"Auto-deleted expired photo: {photo_path.name}")
            
            if deleted_count > 0:
                logger.info(f"Cleanup cycle: Removed {deleted_count} expired photo(s)")
                
        except Exception as e:
            logger.error(f"Photo cleanup error: {e}")
        
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)

@app.on_event("startup")
async def startup_event():
    """Start background tasks on server startup."""
    asyncio.create_task(cleanup_old_photos())
    logger.info(f"Photo cleanup task started (TTL: {PHOTO_TTL_MINUTES} min, interval: {CLEANUP_INTERVAL_SECONDS}s)")


@app.get("/api/config")
async def get_config(request: Request):
    """Secure config fetch with identity verification."""
    try:
        # Check identity from headers for GET requests
        v_id = get_verified_id({}, headers=request.headers)
        logger.info(f"Config request from securely verified ID: {v_id}")
        
        users_v2 = sheet_manager.get_users_v2()
        
        # 1. Compact Active Users: [id, name, role_char, team, department]
        active_users = []
        for u in users_v2:
            if u["status"] == "active":
                tid = str(u["tg_id"]) if u["tg_id"] else ""
                role_char = "s" if u["role"] == "supervisor" else "e"
                active_users.append([tid, u["name"], role_char, u.get("team", "Цех"), u.get("department", "")])
        
        # 2. Orphans: Names without IDs (needed for the claim screen)
        orphan_names = [u["name"] for u in users_v2 if not u["tg_id"] and u["status"] == "active"]
        
        return {
            "ok": True,
            "users": active_users,
            "orphans": orphan_names
        }
    except Exception as e:
        logger.error(f"Config fetch failed: {e}")
        return {"ok": False, "error": str(e)}

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
    """Secure check-in/out handler with fallback identification."""
    try:
        data = await request.json()
        
        # Priority to verified cryptographic ID (Body or Headers)
        v_id = get_verified_id(data, headers=request.headers)
        user_id = v_id if v_id else str(data.get("user_id"))
        
        if not user_id or user_id == "None":
            logger.error("Security Fail: Checkin rejected - No valid identification found.")
            return {"ok": False, "error": "Identity verification failed. Please restart bot."}

        photo_b64 = data.get("photo")
        group_id = data.get("group_id")
        action = data.get("action")
        target_info = data.get("target_user_id") # Explicit target (supervisor mode)
        employee_name = data.get("employee_name") # Fallback
        
        # NEW: Get team and department from request (sent by frontend)
        request_team = data.get("team")
        request_dept = data.get("department")
        
        logger.info(f"Identity check: user_id={user_id}, action={action}, target={target_info}, req_team={request_team}")

        if not photo_b64:
            return {"ok": False, "error": "No photo"}

        # 1. Fetch user records for identification
        users = sheet_manager.get_users_v2()
        
        # 2. Identify Target Employee & Team Info
        final_employee_name = None
        target_tg_id = None
        user_team = "Цех" # Default
        user_dept = ""
        
        if target_info:
            # Supervisor mode: target_info is the Name of the employee selected
            final_employee_name = target_info
            t_user = next((u for u in users if u["name"] == final_employee_name), None)
            if t_user:
                target_tg_id = t_user["tg_id"]
                user_team = t_user.get("team", "Цех")
                user_dept = t_user.get("department", "")
        else:
            # Self mode: Prioritize ID lookup
            u_user = next((u for u in users if str(u["tg_id"]) == user_id), None)
            if u_user:
                final_employee_name = u_user["name"]
                target_tg_id = user_id
                user_team = u_user.get("team", "Цех")
                user_dept = u_user.get("department", "")
            else:
                # FIXED: Fallback now uses team/dept from request instead of default
                final_employee_name = employee_name or "Сотрудник"
                target_tg_id = user_id
                user_team = request_team or "Цех"
                user_dept = request_dept or ""
                logger.warning(f"User {user_id} not found in DB. Using request data: team={user_team}, dept={user_dept}")

        # 3. Identify Submitter
        submitted_by = ""
        if target_info:
            s_user = next((u for u in users if str(u["tg_id"]) == user_id), None)
            submitted_by = s_user["name"] if s_user else f"ID:{user_id}"

        # 4. Log to Google Sheets
        try:
            log_type = "Приход" if action == "check_in" else "Уход"
            sheet_manager.append_log(
                user_name=final_employee_name,
                telegram_id=target_tg_id or user_id,
                log_type=log_type,
                photo_url="-",
                submitted_by=submitted_by,
                team=user_team
            )
        except Exception as e_sheet:
            logger.error(f"Sheet log failed: {e_sheet}")

        # 5. Route Report to Correct Telegram Group
        from datetime import datetime
        now_time = datetime.now().strftime("%H:%M")
        status_emoji = "🟢" if action == "check_in" else "🔴"
        status_text = "НАЧАЛ РАБОТУ" if action == "check_in" else "ЗАКОНЧИЛ РАБОТУ"
        
        # Add Hashtags for Office-style teams (Robust check)
        hashtag = ""
        team_lower = str(user_team).lower().strip()
        office_teams = ["офис", "цех(офис)", "ташкент(офис)"]
        if team_lower in office_teams:
            # 1. Action hashtag
            action_tag = " #приход" if action == "check_in" else " #уход"
            hashtag += action_tag

            # 2. Department hashtag
            if user_dept:
                import re
                clean_dept = str(user_dept).strip().lower().replace(" ", "_")
                # Remove any characters that are not letters, digits or underscores
                clean_dept = re.sub(r'[^а-яёa-z0-9_]', '', clean_dept)
                if clean_dept:
                    hashtag += f" #{clean_dept}"
            
            logger.info(f"Hashtags generated: {hashtag} for {final_employee_name}")
        
        caption = f"{status_emoji} <b>{final_employee_name}</b> {status_text}{hashtag}\n🕒 Время: {now_time}"
        if submitted_by:
            caption += f"\n✅ Подтвердил бригадир: {submitted_by}"

        # Determine target group ID from .env
        groups_mapping = {
            "цех": os.getenv("WORKSHOP_GROUP_ID"),
            "офис": os.getenv("OFFICE_GROUP_ID"),
            "цех(офис)": os.getenv("CEH_OFFICE_GROUP_ID"),
            "ташкент(офис)": os.getenv("TASHKENT_GROUP_ID")
        }
        
        env_group_id = groups_mapping.get(team_lower)
        target_group = env_group_id or group_id or user_id

        
        logger.info(f"Routing debug: team='{user_team}', lower='{team_lower}', env_val='{env_group_id}', final_target='{target_group}'")


        async with httpx.AsyncClient() as client:
            photo_bytes = base64.b64decode(photo_b64)
            files = {'photo': ('photo.jpg', photo_bytes, 'image/jpeg')}
            payload = {
                'chat_id': target_group, 
                'caption': caption,
                'parse_mode': 'HTML'
            }
            tg_resp = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                data=payload,
                files=files,
                timeout=30.0
            )
            
            if tg_resp.status_code != 200:
                logger.error(f"Telegram API Error: {tg_resp.text}")
                return {"ok": True, "warning": "Log saved, but Telegram delivery failed"}

        return {"ok": True}

    except Exception as e:
        logger.error(f"Critical error in handle_checkin: {e}")
        return {"ok": False, "error": str(e)}

@app.post("/api/claim")
async def handle_claim(request: Request):
    """Secure account binding."""
    try:
        data = await request.json()
        
        # Security: Get verified ID from body or headers
        v_id = get_verified_id(data, headers=request.headers)
        user_id = v_id if v_id else str(data.get("user_id"))
        
        full_name = data.get("full_name")
        group_id = data.get("group_id")
        username = data.get("username", "Unknown")

        if not user_id or not full_name:
            logger.error(f"Claim failed: Missing credentials (ID: {user_id}, Name: {full_name})")
            return {"ok": False, "error": "Identification failed. Restart bot and try again."}

        logger.info(f"Claim request: {user_id} (@{username}) -> {full_name}")

        if sheet_manager.bind_telegram_id(user_id, full_name):
            # API Consistency: ensure we return 'name' to the frontend
            role = "employee"
            try:
                users = sheet_manager.get_users_v2()
                user_record = next((u for u in users if str(u['tg_id']) == str(user_id)), None)
                if user_record:
                    role = user_record['role']
            except:
                pass

            # Send notification to Telegram
            user_display = f"@{username}" if username != "Unknown" else f"ID:{user_id}"
            caption = (f"✅ <b>Аккаунт привязан</b>\n\n"
                      f"Сотрудник: <b>{full_name}</b>\n"
                      f"Аккаунт: {user_display}\n\n"
                      f"Теперь вы имеете доступ к терминалу.")
            
            async with httpx.AsyncClient() as client:
                payload = {
                    'chat_id': group_id or user_id,
                    'text': caption,
                    'parse_mode': 'HTML'
                }
                await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    data=payload,
                    timeout=10.0
                )
            
            # CRITICAL: Return 'name' to match app.js expectation
            return {"ok": True, "name": full_name, "role": role}
        else:
            return {"ok": False, "error": "Failed to bind ID in sheet"}

    except Exception as e:
        logger.error(f"Claim error: {e}")
        return {"ok": False, "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
