import asyncio
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

response = client.post("/auth/register", json={"email": "test_crash@example.com", "password": "password123"})
print(f"Status Code: {response.status_code}")
print(f"Response: {response.json()}")
