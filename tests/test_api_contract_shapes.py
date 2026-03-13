from fastapi.testclient import TestClient

from app.main import app


def test_state_route_returns_contract_shape():
    client = TestClient(app)

    response = client.get("/api/v1/state")

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"]
    assert "state" in body
    assert set(body["state"]).issuperset(
        {
            "mental_energy",
            "physical_energy",
            "focus_mode",
            "do_not_disturb_until",
            "recent_context",
            "last_updated_at",
        }
    )
