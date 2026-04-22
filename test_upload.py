import os
from PIL import Image
from io import BytesIO
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("HEYGEN_API_KEY")

img = Image.new('RGB', (512, 512), color = 'red')
buffer = BytesIO()
img.save(buffer, format="JPEG")
buffer.seek(0)

upload_headers = {"x-api-key": api_key}
print("Uploading asset...")
resp = requests.post(
    "https://api.heygen.com/v3/assets",
    headers=upload_headers,
    files={"file": ("test.jpg", buffer, "image/jpeg")}
)
print(resp.status_code)
print(resp.json())

asset_id = resp.json().get("data", {}).get("id") or resp.json().get("data", {}).get("asset_id")
print("Asset ID:", asset_id)

if asset_id:
    print("Creating avatar...")
    avatar_resp = requests.post(
        "https://api.heygen.com/v3/avatars",
        headers={"x-api-key": api_key, "Content-Type": "application/json"},
        json={
            "type": "photo",
            "name": "Test Avatar",
            "file": {
                "type": "asset_id",
                "asset_id": asset_id
            }
        }
    )
    print(avatar_resp.status_code)
    print(avatar_resp.json())
