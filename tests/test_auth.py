import pytest


@pytest.mark.asyncio
async def test_register_customer(client):
    response = await client.post("/api/auth/register", json={
        "email": "jon@example.is",
        "password": "secret123",
        "full_name": "Jón Jónsson",
        "phone": "+354 123 4567",
        "role": "customer",
    })
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["user"]["email"] == "jon@example.is"
    assert data["user"]["role"] == "customer"


@pytest.mark.asyncio
async def test_register_craftsman(client):
    response = await client.post("/api/auth/register", json={
        "email": "palli@rafvirkjun.is",
        "password": "secret123",
        "full_name": "Páll Pálsson",
        "role": "craftsman",
    })
    assert response.status_code == 201
    assert response.json()["user"]["role"] == "craftsman"


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await client.post("/api/auth/register", json={
        "email": "a@b.is",
        "password": "correct",
        "full_name": "A B",
        "role": "customer",
    })
    response = await client.post("/api/auth/login", json={
        "email": "a@b.is",
        "password": "wrong",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_duplicate_email(client):
    await client.post("/api/auth/register", json={
        "email": "dup@test.is",
        "password": "123456",
        "full_name": "Dup",
        "role": "customer",
    })
    response = await client.post("/api/auth/register", json={
        "email": "dup@test.is",
        "password": "123456",
        "full_name": "Dup Again",
        "role": "customer",
    })
    assert response.status_code == 400
