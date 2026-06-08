import pytest


@pytest.mark.asyncio
async def test_create_job(client):
    # Register first
    await client.post("/api/auth/register", json={
        "email": "test@verktorg.is",
        "password": "123456",
        "full_name": "Test User",
        "role": "customer",
    })

    login = await client.post("/api/auth/login", json={
        "email": "test@verktorg.is",
        "password": "123456",
    })
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "title": "Tenging á ljósum",
        "description": "Mig vantar rafvirkja til að tengja 8 ljós.",
        "category": "rafvirkjun",
        "budget_min": 30000.0,
        "budget_max": 50000.0,
        "location": "Reykjavík",
    }
    response = await client.post("/api/jobs/", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Tenging á ljósum"
    assert data["category"] == "rafvirkjun"
    assert data["status"] == "open"


@pytest.mark.asyncio
async def test_list_jobs_paginated(client):
    # Create a job first
    await client.post("/api/auth/register", json={
        "email": "user@v.is",
        "password": "123456",
        "full_name": "User",
        "role": "customer",
    })
    login = await client.post("/api/auth/login", json={"email": "user@v.is", "password": "123456"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    await client.post("/api/jobs/", json={
        "title": "Laga leka í vaski",
        "description": "Er að leita að pípara til að skoða og laga leka.",
        "category": "pipulagnir",
        "budget_min": 10000.0,
        "budget_max": 20000.0,
        "location": "Kópavogur",
    }, headers=headers)

    response = await client.get("/api/jobs/?page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["total_pages"] >= 1


@pytest.mark.asyncio
async def test_search_jobs_by_category(client):
    response = await client.get("/api/jobs/?category=rafvirkjun")
    assert response.status_code == 200
    assert "items" in response.json()
