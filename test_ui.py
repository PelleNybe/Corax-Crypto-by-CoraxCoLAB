from fastapi.testclient import TestClient
from main import app

client = TestClient(app)
response = client.get("/")
print("Response Status:", response.status_code)
# Let's inspect the UI
html_content = response.text
print("HTML length:", len(html_content))
