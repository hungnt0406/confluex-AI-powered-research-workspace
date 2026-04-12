import pytest


@pytest.mark.asyncio
async def test_register_returns_access_token(client) -> None:
    response = await client.post(
        "/auth/register",
        json={"email": "new.user@example.com", "password": "strongpass123"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["user"]["email"] == "new.user@example.com"
    assert payload["access_token"]


@pytest.mark.asyncio
async def test_login_returns_access_token(client, sample_user) -> None:
    response = await client.post(
        "/auth/login",
        json={"email": sample_user["email"], "password": "supersecret123"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["user"]["email"] == sample_user["email"]


@pytest.mark.asyncio
async def test_login_rejects_invalid_password(client, sample_user) -> None:
    response = await client.post(
        "/auth/login",
        json={"email": sample_user["email"], "password": "wrong-password"},
    )

    assert response.status_code == 401
