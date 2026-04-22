import requests

r = requests.get("http://localhost:8000")
print(f"Status: {r.status_code}")
print(f"Content-Type: {r.headers.get('content-type', '?')}")
print(f"Body length: {len(r.text)} chars")
print(f"Has title: {'HeyGen Video Generator' in r.text}")

# Test CSS
r2 = requests.get("http://localhost:8000/style.css")
print(f"\nCSS Status: {r2.status_code}")
print(f"CSS length: {len(r2.text)} chars")

# Test API endpoint exists
r3 = requests.post("http://localhost:8000/api/verify-key", json={"api_key": "test"})
print(f"\nVerify-key Status: {r3.status_code}")
print(f"Response: {r3.json()}")
