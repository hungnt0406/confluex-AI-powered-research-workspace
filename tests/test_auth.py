import pytest


@pytest.mark.asyncio
async def test_register_returns_access_token(client) -> None:
    response = await client.post(
        "/auth/register",
        json={
            "email": "new.user@example.com",
            "password": "strongpass123",
            "agreed_to_terms": True,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["user"]["email"] == "new.user@example.com"
    assert payload["access_token"]


@pytest.mark.asyncio
async def test_register_requires_terms_agreement(client) -> None:
    response = await client.post(
        "/auth/register",
        json={"email": "no.terms@example.com", "password": "strongpass123"},
    )

    assert response.status_code == 400
    assert "Terms of Service" in response.json()["detail"]


@pytest.mark.asyncio
async def test_register_rejects_explicit_false_agreement(client) -> None:
    response = await client.post(
        "/auth/register",
        json={
            "email": "no.terms2@example.com",
            "password": "strongpass123",
            "agreed_to_terms": False,
        },
    )

    assert response.status_code == 400


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
