import time
import logging
from typing import Optional, Dict, Tuple
from collections import defaultdict
import httpx
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import Request, HTTPException, status, Depends
from app.config import get_settings
from app.schemas import StaffMember
from app.db import get_db_connection

logger = logging.getLogger("mb_associates.auth")

# In-memory login attempt rate limiter (max 5 failed attempts per 5 minutes per IP/email)
class LoginRateLimiter:
    def __init__(self, max_attempts: int = 5, window_seconds: int = 300):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        # key -> list of timestamp floats
        self._attempts: Dict[str, list] = defaultdict(list)

    def is_rate_limited(self, key: str) -> bool:
        now = time.time()
        # Clean expired
        self._attempts[key] = [t for t in self._attempts[key] if now - t < self.window_seconds]
        return len(self._attempts[key]) >= self.max_attempts

    def record_failure(self, key: str) -> None:
        self._attempts[key].append(time.time())

    def reset(self, key: str) -> None:
        if key in self._attempts:
            del self._attempts[key]

rate_limiter = LoginRateLimiter()

def get_session_serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(settings.session_secret, salt="mb-staff-session")

def get_csrf_serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(settings.session_secret, salt="mb-csrf-token")

def create_staff_session_token(data: dict) -> str:
    """Create a signed, time-stamped session token."""
    serializer = get_session_serializer()
    return serializer.dumps(data)

def decode_staff_session_token(token: str) -> Optional[dict]:
    """Decode and verify a signed staff session token."""
    settings = get_settings()
    serializer = get_session_serializer()
    try:
        data = serializer.loads(token, max_age=settings.session_max_age_seconds)
        return data
    except (BadSignature, SignatureExpired):
        return None

def generate_csrf_token(session_id: str) -> str:
    """Generate CSRF token bound to a session."""
    serializer = get_csrf_serializer()
    return serializer.dumps({"sid": session_id, "t": time.time()})

def verify_csrf_token(csrf_token: str, session_id: str) -> bool:
    """Verify CSRF token matches the session and is fresh (within 24 hours)."""
    serializer = get_csrf_serializer()
    try:
        data = serializer.loads(csrf_token, max_age=86400)
        return data.get("sid") == session_id
    except (BadSignature, SignatureExpired, Exception):
        return False

async def authenticate_with_supabase(email: str, password: str) -> Tuple[Optional[dict], Optional[str]]:
    """
    Authenticate staff user with Supabase GoTrue Auth API.
    Returns (user_dict, error_message).
    """
    settings = get_settings()
    if not settings.supabase_url or "example.supabase.co" in settings.supabase_url:
        # Development / Local mock fallback when Supabase credentials are not yet configured
        logger.warning("Supabase URL not configured in backend/.env.")
        return None, "Supabase connection not configured. Please set SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY."

    auth_endpoint = f"{settings.supabase_url.rstrip('/')}/auth/v1/token?grant_type=password"
    headers = {
        "apikey": settings.supabase_publishable_key,
        "Content-Type": "application/json"
    }
    payload = {
        "email": email.strip().lower(),
        "password": password
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(auth_endpoint, json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                return data, None
            else:
                err_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                msg = err_data.get("error_description") or err_data.get("msg") or "Invalid credentials"
                return None, msg
    except Exception as exc:
        logger.error(f"Error calling Supabase Auth: {exc}")
        return None, f"Authentication service error: {str(exc)}"

async def get_current_staff(request: Request) -> StaffMember:
    """
    FastAPI dependency to verify staff authentication.
    Checks cookie or Authorization header.
    Validates staff membership against staff_members table.
    """
    settings = get_settings()
    session_token = request.cookies.get(settings.cookie_name)

    # Allow Authorization: Bearer <token> for testing/API clients
    if not session_token and "Authorization" in request.headers:
        auth_header = request.headers["Authorization"]
        if auth_header.startswith("Bearer "):
            session_token = auth_header[7:].strip()

    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in to the staff portal."
        )

    session_data = decode_staff_session_token(session_token)
    if not session_data or "auth_user_id" not in session_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or is invalid. Please sign in again."
        )

    auth_user_id = session_data["auth_user_id"]

    # Verify user exists in staff_members table
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT id, auth_user_id, email, name, role, created_at FROM staff_members WHERE auth_user_id = %s",
                    (auth_user_id,)
                )
                row = await cur.fetchone()
                if not row:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access denied. Your account is not authorized as an MB Associates staff member."
                    )
                return StaffMember(
                    id=str(row["id"]),
                    auth_user_id=str(row["auth_user_id"]),
                    email=row["email"],
                    name=row["name"],
                    role=row["role"] or "coordinator",
                    created_at=row["created_at"]
                )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Database error verifying staff member: {exc}")
        # In test mode or when DB is mock, if session has staff info, allow test mock
        if settings.environment == "test" and session_data.get("is_test"):
            return StaffMember(
                id=session_data.get("id", "test-staff-id"),
                auth_user_id=session_data["auth_user_id"],
                email=session_data.get("email", "staff@mbassociates.internal"),
                name=session_data.get("name", "Test Coordinator"),
                role="coordinator",
                created_at=time.time()
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal database error verifying staff authorization."
        )
