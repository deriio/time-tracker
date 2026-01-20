import httpx
import base64
import logging

logger = logging.getLogger(__name__)

async def upload_to_imgbb(image_base64: str, api_key: str) -> str | None:
    """
    Uploads a Base64 encoded image to ImgBB and returns the URL.
    """
    if not api_key:
        logger.error("IMGBB_API_KEY is missing!")
        return None

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.imgbb.com/1/upload",
                data={
                    "key": api_key,
                    "image": image_base64,
                    "expiration": 15552000  # 180 days
                },
                timeout=30.0
            )
            
            if response.status_code == 200:
                res_data = response.json()
                return res_data["data"]["url"]
            else:
                logger.error(f"ImgBB upload failed: {response.status_code} - {response.text}")
                return None
    except Exception as e:
        logger.error(f"ImgBB upload error: {e}")
        return None
