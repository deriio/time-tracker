import os
import httpx
import asyncio
from dotenv import load_dotenv

async def check_telegram_access():
    load_dotenv()
    token = os.getenv("BOT_TOKEN")
    base_url = os.getenv("TELEGRAM_API_BASE_URL", "https://api.telegram.org").rstrip("/")
    
    if not token:
        print("[ERROR] BOT_TOKEN not found in .env")
        return

    print(f"--- Checking Telegram API Reachability ---")
    print(f"Target Base URL: {base_url}")
    
    api_url = f"{base_url}/bot{token}/getMe"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            print(f"Sending test request to {base_url}/bot[HIDDEN]/getMe...")
            response = await client.get(api_url)
            
            if response.status_code == 200:
                print("[SUCCESS] Telegram API (via mirror) is REACHABLE and TOKEN is VALID.")
                data = response.json()
                bot_info = data.get('result', {})
                print(f"Bot info: @{bot_info.get('username')} (ID: {bot_info.get('id')})")
            elif response.status_code == 401:
                print("[ERROR] API reached, but BOT_TOKEN is INVALID (401 Unauthorized).")
            else:
                print(f"[ERROR] HTTP Status {response.status_code}")
                print(f"Response: {response.text}")
                
    except httpx.ConnectTimeout:
        print("[BLOCK DETECTED] Connection Timeout! The mirror might also be blocked or unreachable.")
    except httpx.ConnectError as e:
        print(f"[CONNECTION ERROR] Could not connect: {e}")
    except Exception as e:
        print(f"[UNEXPECTED ERROR] {e}")

if __name__ == "__main__":
    asyncio.run(check_telegram_access())
