import pytest
from unittest.mock import patch, MagicMock
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.main import app
from app.auth import create_staff_session_token, generate_csrf_token

client = TestClient(app)

class MockStaffCursor:
    def __init__(self, db_store):
        self.db_store = db_store
        self._last_result = None
        self._last_results = []

    async def execute(self, query, params=None):
        q = " ".join(query.split())
        params = params or ()

        # 1. Staff lookup
        if "FROM staff_members WHERE auth_user_id =" in q:
            auth_uid = params[0]
            staff = self.db_store.get("staff_by_auth", {}).get(auth_uid)
            self._last_result = staff
            return

        # 2. List enquiries
        if "FROM enquiries e" in q:
            all_enqs = list(self.db_store.get("enquiries", {}).values())
            # Basic filtering for test
            if "e.status =" in q:
                status_filter = params[0]
                all_enqs = [e for e in all_enqs if e["status"] == status_filter]
            if "ILIKE" in q:
                term = params[0].strip("%").lower()
                all_enqs = [e for e in all_enqs if term in e["reference"].lower() or term in e["name"].lower()]
            
            self._last_results = all_enqs
            return

        # 3. Single enquiry detail
        if "FROM enquiries WHERE id =" in q:
            enq_id = params[0]
            self._last_result = self.db_store.get("enquiries", {}).get(enq_id)
            return

        # 4. Fetch notes for enquiry
        if "FROM staff_notes sn" in q:
            enq_id = params[0]
            notes = self.db_store.get("notes_by_enq", {}).get(enq_id, [])
            self._last_results = notes
            return

        # 5. Update enquiry status
        if "UPDATE enquiries SET status =" in q:
            new_status = params[0]
            enq_id = params[2]
            enq = self.db_store.get("enquiries", {}).get(enq_id)
            if enq:
                enq["status"] = new_status
                enq["updated_at"] = datetime.now(timezone.utc)
                self._last_result = {"id": enq_id, "reference": enq["reference"], "status": new_status, "updated_at": enq["updated_at"]}
            else:
                self._last_result = None
            return

        # 6. Check enquiry exists before note
        if "SELECT id FROM enquiries WHERE id =" in q:
            enq_id = params[0]
            self._last_result = {"id": enq_id} if enq_id in self.db_store.get("enquiries", {}) else None
            return

        # 7. Insert staff note
        if "INSERT INTO staff_notes" in q:
            enq_id = params[0]
            staff_id = params[1]
            content = params[2]
            now = params[3]
            note_rec = {
                "id": "note-uuid-1",
                "enquiry_id": enq_id,
                "staff_id": staff_id,
                "staff_name": "Test Coordinator",
                "content": content,
                "created_at": now
            }
            self.db_store.setdefault("notes_by_enq", {}).setdefault(enq_id, []).append(note_rec)
            self._last_result = note_rec
            return

    async def fetchone(self):
        return self._last_result

    async def fetchall(self):
        return self._last_results

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

class MockStaffConnection:
    def __init__(self, db_store):
        self.db_store = db_store

    def cursor(self):
        return MockStaffCursor(self.db_store)

    async def commit(self):
        pass

@pytest.fixture
def mock_staff_db():
    auth_uid = "staff-auth-uuid-123"
    staff_member = {
        "id": "staff-member-uuid-1",
        "auth_user_id": auth_uid,
        "email": "coordinator@mbassociates.internal",
        "name": "Prashanth Rao",
        "role": "coordinator",
        "created_at": datetime.now(timezone.utc)
    }

    test_enquiry = {
        "id": "enq-uuid-101",
        "reference": "MBA-202611-10001",
        "name": "Narendra Modi",
        "contact_method": "phone",
        "contact_detail": "9811122233",
        "pin_code": "500034",
        "property_type": "Residential Villa",
        "request_type": "site_visit",
        "assistance": ["Solar Feasibility Assessment", "Subsidy Guidance"],
        "roof_area": "400 sq.ft",
        "monthly_bill": 5000.0,
        "notes": "Parapet shadow on north side",
        "consent": True,
        "status": "New",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "notes_count": 0
    }

    store = {
        "staff_by_auth": {auth_uid: staff_member},
        "enquiries": {"enq-uuid-101": test_enquiry},
        "notes_by_enq": {}
    }

    @asynccontextmanager
    async def _get_conn():
        yield MockStaffConnection(store)

    with patch("app.auth.get_db_connection", _get_conn), \
         patch("app.routers.staff.get_db_connection", _get_conn):
        yield {"store": store, "auth_uid": auth_uid}

def get_auth_cookies(auth_uid):
    token = create_staff_session_token({"auth_user_id": auth_uid})
    return {"mb_staff_session": token}

# =========================================================================
# TEST CASES: Staff Authentication & Private Operations Queue
# =========================================================================

def test_staff_login_page_renders():
    """Test staff login page is accessible and contains CSRF token."""
    resp = client.get("/staff/login")
    assert resp.status_code == 200
    assert "Staff Operations Sign In" in resp.text
    assert "csrf_token" in resp.text

def test_unauthenticated_api_access_blocked():
    """Test staff API blocks unauthenticated requests with 401."""
    resp = client.get("/api/staff/enquiries")
    assert resp.status_code == 401
    assert "Authentication required" in resp.json()["detail"]

def test_unauthorized_user_access_forbidden(mock_staff_db):
    """Test an authenticated user NOT in staff_members is rejected with 403."""
    unauthorized_uid = "unauthorized-user-uuid-999"
    cookies = get_auth_cookies(unauthorized_uid)
    resp = client.get("/api/staff/enquiries", cookies=cookies)
    assert resp.status_code == 403
    assert "not authorized as an MB Associates staff member" in resp.json()["detail"]

def test_staff_list_enquiries(mock_staff_db):
    """Test authorized staff can view customer enquiries queue."""
    cookies = get_auth_cookies(mock_staff_db["auth_uid"])
    resp = client.get("/api/staff/enquiries", cookies=cookies)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["reference"] == "MBA-202611-10001"
    assert data[0]["status"] == "New"

def test_staff_get_enquiry_detail(mock_staff_db):
    """Test staff can view full enquiry details including notes."""
    cookies = get_auth_cookies(mock_staff_db["auth_uid"])
    resp = client.get("/api/staff/enquiries/enq-uuid-101", cookies=cookies)
    assert resp.status_code == 200
    data = resp.json()
    assert data["reference"] == "MBA-202611-10001"
    assert data["name"] == "Narendra Modi"
    assert data["roof_area"] == "400 sq.ft"

def test_staff_update_status(mock_staff_db):
    """Test staff can transition status between New, Contacted, In Progress, Closed."""
    cookies = get_auth_cookies(mock_staff_db["auth_uid"])
    resp = client.patch(
        "/api/staff/enquiries/enq-uuid-101/status",
        json={"status": "Contacted"},
        cookies=cookies
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "Contacted"

    # Transition to In Progress
    resp2 = client.patch(
        "/api/staff/enquiries/enq-uuid-101/status",
        json={"status": "In Progress"},
        cookies=cookies
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "In Progress"

def test_staff_add_internal_note(mock_staff_db):
    """Test staff can record internal notes on an enquiry."""
    cookies = get_auth_cookies(mock_staff_db["auth_uid"])
    note_payload = {
        "content": "Spoke with client. Confirmed 3.5 kWp feasibility. Offline vendor dispatched for terrace audit."
    }
    resp = client.post(
        "/api/staff/enquiries/enq-uuid-101/notes",
        json=note_payload,
        cookies=cookies
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "Spoke with client" in data["content"]
    assert data["staff_name"] == "Prashanth Rao"

def test_staff_logout():
    """Test logout removes session cookie and redirects to login."""
    resp = client.get("/staff/logout", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/staff/login"
