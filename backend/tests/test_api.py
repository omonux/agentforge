from fastapi.testclient import TestClient
from app import main

def test_health_and_core_records(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "test.db")
    with TestClient(main.app) as client:
        assert client.get("/health").json()["status"] == "ok"
        lead = client.post("/api/v1/crm/leads", json={
            "name": "Test Customer", "email": "test@example.com",
            "company": "Example Co", "stage": "new"
        })
        assert lead.status_code == 200
        assert lead.json()["name"] == "Test Customer"

        ticket = client.post("/api/v1/support/tickets", json={
            "customer": "Test Customer", "subject": "Need help",
            "message": "I need assistance", "priority": "high"
        })
        assert ticket.status_code == 200
        assert ticket.json()["status"] == "open"

        content = client.post("/api/v1/content", json={
            "title": "First short", "channel": "youtube",
            "format": "short_video"
        })
        assert content.status_code == 200
        assert content.json()["status"] == "draft"

        workflow = client.post("/api/v1/automations", json={
            "name": "Review new lead", "trigger_name": "New lead",
            "action_plan": "Draft a follow-up for human review"
        })
        assert workflow.status_code == 200
        assert workflow.json()["status"] == "draft"

        watch = client.post("/api/v1/trading/watchlist", json={"symbol": "BTCUSD"})
        assert watch.status_code == 200
        assert watch.json()["symbol"] == "BTCUSD"

        assert client.get("/api/v1/analytics/summary").json()["leads_total"] == 1

def test_invalid_stage_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "invalid.db")
    with TestClient(main.app) as client:
        response = client.post("/api/v1/crm/leads", json={
            "name": "Bad Stage", "stage": "invented"
        })
        assert response.status_code == 400
