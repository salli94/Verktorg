import pytest


async def register_user(client, email, role, full_name):
    response = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "secret123",
            "full_name": full_name,
            "role": role,
        },
    )
    return response.json()


async def create_craftsman_profile(client, token, category="rafvirkjun"):
    response = await client.post(
        "/api/craftsmen/profile",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "trade_category": category,
            "description": "Löggiltur iðnaðarmaður",
            "location": "Reykjavík",
            "hourly_rate": 12000,
        },
    )
    return response


@pytest.mark.asyncio
async def test_private_request_flow(client):
    customer = await register_user(client, "customer.messages@test.is", "customer", "Jón Jónsson")
    craftsman = await register_user(client, "craftsman.messages@test.is", "craftsman", "Páll Pálsson")
    profile_res = await create_craftsman_profile(client, craftsman["access_token"])
    assert profile_res.status_code == 201

    thread_res = await client.post(
        "/api/conversations/",
        headers={"Authorization": f"Bearer {customer['access_token']}"},
        json={
            "craftsman_user_id": craftsman["user"]["id"],
            "title": "Beiðni um einkatilboð",
            "project_summary": "Mig vantar tilboð í tengingu á ljósum í eldhúsi.",
            "category": "rafvirkjun",
            "location": "Reykjavík",
            "budget_min": 30000,
            "budget_max": 50000,
        },
    )
    assert thread_res.status_code == 201
    thread = thread_res.json()
    assert thread["title"] == "Beiðni um einkatilboð"
    assert len(thread["messages"]) == 1

    reply_res = await client.post(
        f"/api/conversations/{thread['id']}/messages",
        headers={"Authorization": f"Bearer {craftsman['access_token']}"},
        json={"body": "Ég get skoðað þetta og sent þér tilboð í dag."},
    )
    assert reply_res.status_code == 201

    quote_res = await client.post(
        f"/api/conversations/{thread['id']}/quotes",
        headers={"Authorization": f"Bearer {craftsman['access_token']}"},
        json={"amount": 45000, "note": "Verð miðað við heimsókn og vinnu", "estimated_hours": 4},
    )
    assert quote_res.status_code == 201
    quote = quote_res.json()
    assert quote["status"] == "pending"

    accept_res = await client.put(
        f"/api/conversations/quotes/{quote['id']}/accept",
        headers={"Authorization": f"Bearer {customer['access_token']}"},
    )
    assert accept_res.status_code == 200
    assert accept_res.json()["ok"] is True


@pytest.mark.asyncio
async def test_blocks_contact_info_in_first_private_request(client):
    customer = await register_user(client, "customer.block@test.is", "customer", "Anna")
    craftsman = await register_user(client, "craftsman.block@test.is", "craftsman", "Bjarni")
    profile_res = await create_craftsman_profile(client, craftsman["access_token"])
    assert profile_res.status_code == 201

    thread_res = await client.post(
        "/api/conversations/",
        headers={"Authorization": f"Bearer {customer['access_token']}"},
        json={
            "craftsman_user_id": craftsman["user"]["id"],
            "title": "Hringdu í mig",
            "project_summary": "Endilega hringdu í mig í 8881234 eða sendu á anna@test.is.",
            "category": "rafvirkjun",
        },
    )
    assert thread_res.status_code == 400
    assert "VerkTorg" in thread_res.json()["detail"]
