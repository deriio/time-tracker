import hashlib
import hmac
import json
from urllib.parse import parse_qsl

def validate_webapp_data(init_data: str, bot_token: str) -> dict | None:
    """
    Validates the signature of data received from the Telegram Web App.
    Returns the parsed user dictionary if valid, otherwise None.
    """
    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
        if "hash" not in parsed:
            return None
            
        received_hash = parsed.pop("hash")
        
        # Data-check-string is a sorted list of all key-value pairs
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(parsed.items())
        )
        
        # Secret key is the HMAC-SHA256 hash of the bot token with "WebAppData"
        secret_key = hmac.new(
            b"WebAppData", bot_token.encode(), hashlib.sha256
        ).digest()
        
        # Computed hash of the data-check-string with the secret key
        calculated_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()
        
        if calculated_hash == received_hash:
            # The 'user' field in init_data is a JSON string
            user_json = parsed.get("user")
            return json.loads(user_json) if user_json else {}
        
        return None
    except Exception:
        return None
