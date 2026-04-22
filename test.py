import os
import time
import requests
from dotenv import load_dotenv
from pathlib import Path

# Load API key from .env
load_dotenv(Path(__file__).parent / ".env")
HEYGEN_API_KEY = os.getenv("HEYGEN_API_KEY")

if not HEYGEN_API_KEY:
    print("Error: HEYGEN_API_KEY not found in .env")
    exit(1)

video_id = "a3d0b45a8bfc4e878bf56395b4ac7c44"
BASE_URL = "https://api.heygen.com"

headers = {
    "x-api-key": HEYGEN_API_KEY,
    "Content-Type": "application/json"
}

print(f"Checking status for video: {video_id}\n")

while True:
    try:
        response = requests.get(
            f"{BASE_URL}/v3/videos/{video_id}",
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        
        result = response.json()
        data = result.get("data", result)
        
        status = data.get("status", "unknown")
        print(f"Status: {status}")
        
        if status == "completed":
            video_url = data.get("video_url") or data.get("url")
            print(f"\n✅ Video is ready!")
            print(f"URL: {video_url}")
            break
            
        if status == "failed":
            print(f"\n❌ Generation failed")
            print(f"Error: {data.get('error', 'Unknown error')}")
            break
            
    except Exception as e:
        print(f"Error checking status: {e}")
        
    print("Waiting 10 seconds...\n")
    time.sleep(10)