import pytest
from datetime import datetime, timedelta
from tortoise.contrib.test import initializer, finalizer
from certainty.models import CertificateMonitor, MonitorState
from certainty.monitor import (
    create_certificate_monitor,
    get_certificate_monitor,
    refresh_certificate_monitor,
)
from fastapi.testclient import TestClient
from certainty import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
async def initialize_tests(request):
    await initializer(["certainty.models"])
    yield
    await finalizer()


@pytest.mark.asyncio
async def test_create_certificate_monitor():
    monitor = await create_certificate_monitor("example.com", "test@example.com", 7)
    assert monitor.domain == "example.com"
    assert monitor.email == "test@example.com"
    assert monitor.warning_days == 7
    assert monitor.state == MonitorState.UNKNOWN


@pytest.mark.asyncio
async def test_get_certificate_monitor():
    created_monitor = await create_certificate_monitor("test.com", "test@test.com", 14)
    retrieved_monitor = await get_certificate_monitor(created_monitor.uuid)
    assert retrieved_monitor.domain == "test.com"
    assert retrieved_monitor.email == "test@test.com"
    assert retrieved_monitor.warning_days == 14


@pytest.mark.asyncio
async def test_refresh_certificate_monitor(mocker):
    # Mock the get_certificate_detail function
    mock_cert_detail = {
        "serialNumber": "1234567890",
        "notBefore": "May 30 00:00:00 2023 GMT",
        "notAfter": "May 30 23:59:59 2024 GMT",
    }
    mocker.patch(
        "certainty.monitor.get_certificate_detail", return_value=mock_cert_detail
    )

    monitor = await create_certificate_monitor("refresh.com", "refresh@test.com", 30)
    refreshed_monitor = await refresh_certificate_monitor(monitor.uuid)

    assert refreshed_monitor.serial == "1234567890"
    assert refreshed_monitor.not_before == datetime(2023, 5, 30, 0, 0, 0)
    assert refreshed_monitor.not_after == datetime(2024, 5, 30, 23, 59, 59)
    assert refreshed_monitor.state == MonitorState.OK


def test_create_monitor_api(client):
    response = client.post(
        "/api/monitors",
        json={
            "domain": "api.example.com",
            "email": "api@example.com",
            "warning_days": 10,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["domain"] == "api.example.com"
    assert data["email"] == "api@example.com"
    assert data["warning_days"] == 10


def test_get_monitor_api(client):
    # First, create a monitor
    create_response = client.post(
        "/api/monitors",
        json={
            "domain": "get.example.com",
            "email": "get@example.com",
            "warning_days": 15,
        },
    )
    created_monitor = create_response.json()

    # Now, get the monitor
    get_response = client.get(f"/api/monitors/{created_monitor['uuid']}")
    assert get_response.status_code == 200
    retrieved_monitor = get_response.json()
    assert retrieved_monitor["domain"] == "get.example.com"
    assert retrieved_monitor["email"] == "get@example.com"
    assert retrieved_monitor["warning_days"] == 15
