"""Tests for API routes using FastAPI TestClient."""
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client with the FastAPI app."""
    from src.main import app
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    def test_health_includes_model_status(self, client):
        response = client.get("/api/health")
        data = response.json()
        assert "model_loaded" in data
        assert "llm_available" in data


class TestRootEndpoint:
    def test_root_returns_app_info(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "FlowCast API"
        assert "version" in data


class TestChatEndpoint:
    def test_chat_requires_llm(self, client):
        response = client.post(
            "/api/chat",
            json={"message": "Hello", "include_context": False}
        )
        # Will return 503 if LLM not configured, or 200 if it is
        assert response.status_code in [200, 503]

    def test_chat_validates_body(self, client):
        response = client.post("/api/chat", json={})
        assert response.status_code == 422  # Validation error


class TestSimulateEndpoint:
    def test_simulate_requires_llm(self, client):
        response = client.post(
            "/api/simulate",
            json={"scenario": "What if we discount pasta?"}
        )
        assert response.status_code in [200, 503]
