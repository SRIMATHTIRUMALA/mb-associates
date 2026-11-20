import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.main import app
from app.routers.enquiries import compute_idempotency_hash

client = TestClient(app)

# In-memory mock database store for testing enquiries
class MockCursor:
    def __init__(self, db_store):
        self.db_store = db_store
        self._last_result = None
        self._last_results = []

    async def execute(self, query, params=None):
        q = " ".join(query.split())
        params = params or ()

        if "SELECT id, reference, property_type, request_type, assistance, status, created_at FROM enquiries WHERE idempotency_hash =" in q:
            hash_val = params[0]
            existing = self.db_store.get("by_hash", {}).get(hash_val)
            self._last_result = existing
            return

        if "SELECT 1 FROM enquiries WHERE reference =" in q:
            ref_val = params[0]
            existing = self.db_store.get("by_ref", {}).get(ref_val)
            self._last_result = {"exists": 1} if existing else None
            return

        if "INSERT INTO enquiries" in q:
            ref = params[0]
            hash_val = params[1]
            record = {
                "id": "11111111-2222-3333-4444-555555555555",
                "reference": ref,
                "idempotency_hash": hash_val,
                "name": params[2],
                "contact_method": params[3],
                "contact_detail": params[4],
                "pin_code": params[5],
                "property_type": params[6],
                "request_type": params[7],
                "assistance": params[8],
                "roof_area": params[9],
                "monthly_bill": params[10],
                "notes": params[11],
                "consent": params[12],
                "status": "New",
                "created_at": params[13],
                "updated_at": params[14]
            }
            self.db_store.setdefault("by_hash", {})[hash_val] = record
            self.db_store.setdefault("by_ref", {})[ref] = record
            self._last_result = {"id": record["id"], "reference": ref, "status": "New", "created_at": record["created_at"]}
            return

    async def fetchone(self):
        return self._last_result

    async def fetchall(self):
        return self._last_results

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

class MockConnection:
    def __init__(self, db_store):
        self.db_store = db_store

    def cursor(self):
        return MockCursor(self.db_store)

    async def commit(self):
        pass

@pytest.fixture
def mock_db():
    store = {"by_hash": {}, "by_ref": {}}

    @asynccontextmanager
    async def _get_conn():
        yield MockConnection(store)

    with patch("app.routers.enquiries.get_db_connection", _get_conn):
        yield store

# =========================================================================
# TEST CASES: Customer Enquiry Submission & Validation
# =========================================================================

def test_valid_enquiry_submission(mock_db):
    """Test valid enquiry with 10-digit mobile number and 6-digit PIN."""
    payload = {
        "name": "Rajesh Kumar",
        "contact_method": "phone",
        "contact_detail": "9876543210",
        "pin_code": "500001",
        "property_type": "Residential Villa",
        "request_type": "general",
        "assistance": ["Solar Feasibility Assessment", "Subsidy Guidance"],
        "monthly_bill": 4500.0,
        "consent": True
    }
    response = client.post("/api/enquiries", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "reference" in data
    assert data["reference"].startswith("MBA-")
    assert data["status"] == "New"
    assert data["is_duplicate"] is False

def test_valid_enquiry_with_email(mock_db):
    """Test valid enquiry when preferred contact is email."""
    payload = {
        "name": "Suresh Patel",
        "contact_method": "email",
        "contact_detail": "suresh.patel@example.com",
        "pin_code": "380001",
        "property_type": "Commercial",
        "request_type": "site_visit",
        "assistance": ["Full Project Coordination"],
        "consent": True
    }
    response = client.post("/api/enquiries", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["reference"].startswith("MBA-")

def test_idempotent_duplicate_submission(mock_db):
    """Test identical retry returns the original reference (idempotency)."""
    payload = {
        "name": "Ananya Sharma",
        "contact_method": "whatsapp",
        "contact_detail": "9123456780",
        "pin_code": "560001",
        "property_type": "Housing Society",
        "request_type": "general",
        "assistance": ["PM Surya Ghar Subsidy Guidance"],
        "consent": True
    }
    # First submission
    resp1 = client.post("/api/enquiries", json=payload)
    assert resp1.status_code == 201
    ref1 = resp1.json()["reference"]

    # Identical retry
    resp2 = client.post("/api/enquiries", json=payload)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["reference"] == ref1
    assert data2["is_duplicate"] is True

def test_conflicting_idempotency_key(mock_db):
    """Test same customer contact details with different parameters returns 409 Conflict."""
    payload1 = {
        "name": "Vikram Verma",
        "contact_method": "phone",
        "contact_detail": "9988776655",
        "pin_code": "110001",
        "property_type": "Residential Villa",
        "request_type": "general",
        "assistance": ["Solar Feasibility Assessment"],
        "consent": True
    }
    resp1 = client.post("/api/enquiries", json=payload1)
    assert resp1.status_code == 201

    # Same name + contact + PIN, but different property type
    payload2 = dict(payload1)
    payload2["property_type"] = "Industrial"
    payload2["request_type"] = "site_visit"

    resp2 = client.post("/api/enquiries", json=payload2)
    assert resp2.status_code == 409
    assert "already exists with different request parameters" in resp2.json()["detail"]

def test_missing_required_fields():
    """Test validation fails when required fields are missing."""
    # Missing consent
    resp = client.post("/api/enquiries", json={
        "name": "Test User",
        "contact_method": "phone",
        "contact_detail": "9876543210",
        "pin_code": "500001",
        "property_type": "Residential Villa"
    })
    assert resp.status_code == 422

def test_invalid_pin_code():
    """Test invalid 5-digit or non-numeric PIN codes fail validation."""
    resp1 = client.post("/api/enquiries", json={
        "name": "Test User",
        "contact_method": "phone",
        "contact_detail": "9876543210",
        "pin_code": "12345",  # Only 5 digits
        "property_type": "Residential Villa",
        "consent": True
    })
    assert resp1.status_code == 422

    resp2 = client.post("/api/enquiries", json={
        "name": "Test User",
        "contact_method": "phone",
        "contact_detail": "9876543210",
        "pin_code": "ABC123",  # Non-digit
        "property_type": "Residential Villa",
        "consent": True
    })
    assert resp2.status_code == 422

def test_contact_method_mismatch():
    """Test validation fails if method is email but phone provided or vice versa."""
    # Email method with phone number
    resp1 = client.post("/api/enquiries", json={
        "name": "Test User",
        "contact_method": "email",
        "contact_detail": "9876543210",  # Not an email
        "pin_code": "500001",
        "property_type": "Residential Villa",
        "consent": True
    })
    assert resp1.status_code == 422

    # Phone method with invalid short number
    resp2 = client.post("/api/enquiries", json={
        "name": "Test User",
        "contact_method": "phone",
        "contact_detail": "12345",  # Invalid phone
        "pin_code": "500001",
        "property_type": "Residential Villa",
        "consent": True
    })
    assert resp2.status_code == 422

def test_consent_mandatory():
    """Test consent=False is rejected."""
    resp = client.post("/api/enquiries", json={
        "name": "Test User",
        "contact_method": "phone",
        "contact_detail": "9876543210",
        "pin_code": "500001",
        "property_type": "Residential Villa",
        "consent": False
    })
    assert resp.status_code == 422
