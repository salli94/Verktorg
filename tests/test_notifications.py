import pytest
from app.models import Notification


class TestNotifications:
    async def _register_customer(self, client):
        res = await client.post("/api/auth/register", json={
            "email": "customer@test.is",
            "password": "secret123",
            "full_name": "Jón Jónsson",
            "role": "customer",
        })
        return res.json()

    async def _register_craftsman(self, client):
        res = await client.post("/api/auth/register", json={
            "email": "craftsman@test.is",
            "password": "secret123",
            "full_name": "Páll Pálsson",
            "role": "craftsman",
        })
        return res.json()

    async def _create_job(self, client, token, category="rafvirkjun"):
        res = await client.post(
            "/api/jobs/",
            json={
                "title": "Laga rofa í eldhúsi",
                "description": "Þarf að laga rofa í eldhúsi sem virkar ekki",
                "category": category,
                "location": "Reykjavík",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        return res.json()

    async def _create_bid(self, client, token, job_id):
        res = await client.post(
            f"/api/bids/?job_id={job_id}",
            json={"amount": 15000, "message": "Get gert þetta"},
            headers={"Authorization": f"Bearer {token}"},
        )
        return res.json()

    async def test_notification_on_new_bid(self, client):
        cust = await self._register_customer(client)
        craft = await self._register_craftsman(client)
        job = await self._create_job(client, cust["access_token"])
        bid = await self._create_bid(client, craft["access_token"], job["id"])
        assert bid.get("id")

        res = await client.get(
            "/api/notifications/",
            headers={"Authorization": f"Bearer {cust['access_token']}"},
        )
        data = res.json()
        assert len(data) >= 1
        assert data[0]["type"] == "new_bid"
        assert "Laga rofa" in data[0]["message"]
        assert data[0]["is_read"] is False

    async def test_unread_count(self, client):
        cust = await self._register_customer(client)
        res = await client.get(
            "/api/notifications/unread-count",
            headers={"Authorization": f"Bearer {cust['access_token']}"},
        )
        data = res.json()
        assert "count" in data
        assert isinstance(data["count"], int)

    async def test_mark_notification_read(self, client):
        cust = await self._register_customer(client)
        craft = await self._register_craftsman(client)
        job = await self._create_job(client, cust["access_token"])
        await self._create_bid(client, craft["access_token"], job["id"])

        res = await client.get(
            "/api/notifications/",
            headers={"Authorization": f"Bearer {cust['access_token']}"},
        )
        notifs = res.json()
        assert len(notifs) > 0
        notif_id = notifs[0]["id"]

        res = await client.put(
            f"/api/notifications/{notif_id}/read",
            headers={"Authorization": f"Bearer {cust['access_token']}"},
        )
        assert res.json()["ok"] is True

        res = await client.get(
            "/api/notifications/",
            headers={"Authorization": f"Bearer {cust['access_token']}"},
        )
        updated = res.json()
        found = [n for n in updated if n["id"] == notif_id]
        assert len(found) == 1
        assert found[0]["is_read"] is True

    async def test_mark_all_read(self, client):
        cust = await self._register_customer(client)
        craft = await self._register_craftsman(client)
        job = await self._create_job(client, cust["access_token"])
        await self._create_bid(client, craft["access_token"], job["id"])

        res = await client.put(
            "/api/notifications/read-all",
            headers={"Authorization": f"Bearer {cust['access_token']}"},
        )
        assert res.json()["ok"] is True

        res = await client.get(
            "/api/notifications/unread-count",
            headers={"Authorization": f"Bearer {cust['access_token']}"},
        )
        assert res.json()["count"] == 0

    async def test_notification_on_bid_accepted(self, client):
        cust = await self._register_customer(client)
        craft = await self._register_craftsman(client)
        job = await self._create_job(client, cust["access_token"])
        bid = await self._create_bid(client, craft["access_token"], job["id"])

        res = await client.put(
            f"/api/bids/{bid['id']}/accept",
            headers={"Authorization": f"Bearer {cust['access_token']}"},
        )
        assert res.json()["ok"] is True

        res = await client.get(
            "/api/notifications/",
            headers={"Authorization": f"Bearer {craft['access_token']}"},
        )
        data = res.json()
        types = [n["type"] for n in data]
        assert "bid_accepted" in types

    async def test_no_notification_for_stranger(self, client):
        cust = await self._register_customer(client)
        other = await self._register_craftsman(client)
        res = await client.get(
            "/api/notifications/",
            headers={"Authorization": f"Bearer {other['access_token']}"},
        )
        assert res.json() == []
