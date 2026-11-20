import logging
from typing import List, Optional
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.schemas import (
    StaffMember,
    StatusUpdate,
    StaffNoteCreate,
    StaffNoteResponse,
    EnquiryDetail
)
from app.auth import (
    authenticate_with_supabase,
    create_staff_session_token,
    get_current_staff,
    generate_csrf_token,
    verify_csrf_token,
    rate_limiter
)
from app.db import get_db_connection

logger = logging.getLogger("mb_associates.staff")

# Setup templates directory
BACKEND_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BACKEND_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["Staff Operations"])

# =========================================================================
# STAFF HTML PAGES (Web Portal)
# =========================================================================

@router.get("/staff/login", response_class=HTMLResponse)
async def staff_login_page(request: Request):
    """Render the staff login page with CSRF token."""
    settings = get_settings()
    session_token = request.cookies.get(settings.cookie_name)
    if session_token:
        # Check if already logged in
        try:
            staff = await get_current_staff(request)
            if staff:
                return RedirectResponse(url="/staff/enquiries", status_code=status.HTTP_302_FOUND)
        except Exception:
            pass

    # Generate a fresh CSRF token
    csrf_token = generate_csrf_token("anon_login_session")
    return templates.TemplateResponse(
        request=request,
        name="staff_login.html",
        context={"csrf_token": csrf_token, "error": None}
    )

@router.post("/staff/login")
async def staff_login_post(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: Optional[str] = Form(None)
):
    """Handle staff login via Supabase Auth with rate limiting and CSRF protection."""
    settings = get_settings()
    client_ip = request.client.host if request.client else "unknown"
    rate_limit_key = f"{client_ip}:{email.strip().lower()}"

    # 1. Check rate limit
    if rate_limiter.is_rate_limited(rate_limit_key):
        return templates.TemplateResponse(
            request=request,
            name="staff_login.html",
            context={
                "csrf_token": generate_csrf_token("anon_login_session"),
                "error": "Too many failed login attempts. Please wait 5 minutes before trying again."
            },
            status_code=status.HTTP_429_TOO_MANY_REQUESTS
        )

    # 2. Verify CSRF token
    if not csrf_token or not verify_csrf_token(csrf_token, "anon_login_session"):
        return templates.TemplateResponse(
            request=request,
            name="staff_login.html",
            context={
                "csrf_token": generate_csrf_token("anon_login_session"),
                "error": "Session security verification failed. Please refresh and try again."
            },
            status_code=status.HTTP_400_BAD_REQUEST
        )

    # 3. Authenticate against Supabase GoTrue Auth
    auth_data, err_msg = await authenticate_with_supabase(email, password)
    if err_msg or not auth_data or "user" not in auth_data:
        rate_limiter.record_failure(rate_limit_key)
        return templates.TemplateResponse(
            request=request,
            name="staff_login.html",
            context={
                "csrf_token": generate_csrf_token("anon_login_session"),
                "error": err_msg or "Invalid email or password."
            },
            status_code=status.HTTP_401_UNAUTHORIZED
        )

    user = auth_data["user"]
    auth_user_id = str(user["id"])

    # 4. Verify user exists in staff_members table
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT id, auth_user_id, email, name, role FROM staff_members WHERE auth_user_id = %s",
                    (auth_user_id,)
                )
                staff_row = await cur.fetchone()
                if not staff_row:
                    rate_limiter.record_failure(rate_limit_key)
                    return templates.TemplateResponse(
                        request=request,
                        name="staff_login.html",
                        context={
                            "csrf_token": generate_csrf_token("anon_login_session"),
                            "error": "Authentication successful, but you are not registered as an authorized staff member."
                        },
                        status_code=status.HTTP_403_FORBIDDEN
                    )

        # Successful staff login -> reset rate limiter
        rate_limiter.reset(rate_limit_key)

        # Create session cookie
        session_payload = {
            "auth_user_id": auth_user_id,
            "email": staff_row["email"],
            "name": staff_row["name"],
            "role": staff_row["role"]
        }
        token = create_staff_session_token(session_payload)

        redirect = RedirectResponse(url="/staff/enquiries", status_code=status.HTTP_303_SEE_OTHER)
        redirect.set_cookie(
            key=settings.cookie_name,
            value=token,
            max_age=settings.session_max_age_seconds,
            httponly=True,
            samesite="lax",
            secure=(settings.environment == "production")
        )
        return redirect

    except Exception as exc:
        logger.error(f"Error checking staff membership: {exc}")
        return templates.TemplateResponse(
            request=request,
            name="staff_login.html",
            context={
                "csrf_token": generate_csrf_token("anon_login_session"),
                "error": "Database error checking staff privileges. Please contact administrator."
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@router.get("/staff/logout")
@router.post("/staff/logout")
async def staff_logout():
    """Clear staff session cookie and redirect to login."""
    settings = get_settings()
    redirect = RedirectResponse(url="/staff/login", status_code=status.HTTP_303_SEE_OTHER)
    redirect.delete_cookie(key=settings.cookie_name)
    return redirect

@router.get("/staff/enquiries", response_class=HTMLResponse)
async def staff_enquiries_page(
    request: Request,
    current_staff: StaffMember = Depends(get_current_staff)
):
    """Render the private staff operations queue interface."""
    # Generate CSRF token bound to this staff member's auth id
    csrf_token = generate_csrf_token(current_staff.auth_user_id)
    return templates.TemplateResponse(
        request=request,
        name="staff_enquiries.html",
        context={
            "staff": current_staff,
            "csrf_token": csrf_token
        }
    )

# =========================================================================
# STAFF REST API (Protected endpoints for table & actions)
# =========================================================================

@router.get("/api/staff/enquiries", response_model=List[dict])
async def list_enquiries(
    search: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    current_staff: StaffMember = Depends(get_current_staff)
):
    """
    Search and filter customer enquiries in the staff queue.
    - search: matches reference, name, contact_detail, pin_code
    - status: filters by 'New', 'Contacted', 'In Progress', 'Closed'
    """
    query = """
        SELECT 
            e.id, 
            e.reference, 
            e.name, 
            e.contact_method, 
            e.contact_detail, 
            e.pin_code, 
            e.property_type, 
            e.request_type, 
            e.status, 
            e.created_at,
            (SELECT COUNT(*) FROM staff_notes sn WHERE sn.enquiry_id = e.id) AS notes_count
        FROM enquiries e
        WHERE 1=1
    """
    params = []

    if status and status.strip() and status != "All":
        query += " AND e.status = %s"
        params.append(status.strip())

    if search and search.strip():
        term = f"%{search.strip()}%"
        query += " AND (e.reference ILIKE %s OR e.name ILIKE %s OR e.contact_detail ILIKE %s OR e.pin_code ILIKE %s)"
        params.extend([term, term, term, term])

    query += " ORDER BY e.created_at DESC LIMIT %s OFFSET %s"
    params.extend([min(limit, 200), max(offset, 0)])

    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, tuple(params))
            rows = await cur.fetchall()
            return [
                {
                    "id": str(r["id"]),
                    "reference": r["reference"],
                    "name": r["name"],
                    "contact_method": r["contact_method"],
                    "contact_detail": r["contact_detail"],
                    "pin_code": r["pin_code"],
                    "property_type": r["property_type"],
                    "request_type": r["request_type"],
                    "status": r["status"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                    "notes_count": r["notes_count"]
                }
                for r in rows
            ]

@router.get("/api/staff/enquiries/{enquiry_id}", response_model=EnquiryDetail)
async def get_enquiry_detail(
    enquiry_id: str,
    current_staff: StaffMember = Depends(get_current_staff)
):
    """Retrieve full details of an enquiry including all internal staff notes."""
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, reference, name, contact_method, contact_detail, pin_code,
                       property_type, request_type, assistance, roof_area, monthly_bill,
                       notes, consent, status, created_at, updated_at
                FROM enquiries
                WHERE id = %s
                """,
                (enquiry_id,)
            )
            enq = await cur.fetchone()
            if not enq:
                raise HTTPException(status_code=404, detail="Enquiry not found.")

            # Fetch staff notes with author name
            await cur.execute(
                """
                SELECT sn.id, sn.enquiry_id, sn.staff_id, sm.name AS staff_name, sn.content, sn.created_at
                FROM staff_notes sn
                LEFT JOIN staff_members sm ON sn.staff_id = sm.id
                WHERE sn.enquiry_id = %s
                ORDER BY sn.created_at ASC
                """,
                (enquiry_id,)
            )
            notes_rows = await cur.fetchall()

            staff_notes = [
                StaffNoteResponse(
                    id=str(n["id"]),
                    enquiry_id=str(n["enquiry_id"]),
                    staff_id=str(n["staff_id"]) if n["staff_id"] else None,
                    staff_name=n["staff_name"] or "Staff Coordinator",
                    content=n["content"],
                    created_at=n["created_at"]
                )
                for n in notes_rows
            ]

            return EnquiryDetail(
                id=str(enq["id"]),
                reference=enq["reference"],
                name=enq["name"],
                contact_method=enq["contact_method"],
                contact_detail=enq["contact_detail"],
                pin_code=enq["pin_code"],
                property_type=enq["property_type"],
                request_type=enq["request_type"],
                assistance=enq["assistance"] or [],
                roof_area=enq["roof_area"],
                monthly_bill=float(enq["monthly_bill"]) if enq["monthly_bill"] is not None else None,
                notes=enq["notes"],
                consent=enq["consent"],
                status=enq["status"],
                created_at=enq["created_at"],
                updated_at=enq["updated_at"],
                staff_notes=staff_notes
            )

@router.patch("/api/staff/enquiries/{enquiry_id}/status")
async def update_enquiry_status(
    enquiry_id: str,
    payload: StatusUpdate,
    current_staff: StaffMember = Depends(get_current_staff)
):
    """Update enquiry status (New, Contacted, In Progress, Closed)."""
    now = datetime.now(timezone.utc)
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE enquiries
                SET status = %s, updated_at = %s
                WHERE id = %s
                RETURNING id, reference, status, updated_at
                """,
                (payload.status, now, enquiry_id)
            )
            updated = await cur.fetchone()
            if not updated:
                raise HTTPException(status_code=404, detail="Enquiry not found.")
            await conn.commit()

            logger.info(
                f"Staff {current_staff.email} updated enquiry {updated['reference']} to {payload.status}"
            )
            return {
                "id": str(updated["id"]),
                "reference": updated["reference"],
                "status": updated["status"],
                "updated_at": updated["updated_at"].isoformat()
            }

@router.post("/api/staff/enquiries/{enquiry_id}/notes", response_model=StaffNoteResponse)
async def add_staff_note(
    enquiry_id: str,
    payload: StaffNoteCreate,
    current_staff: StaffMember = Depends(get_current_staff)
):
    """Add an internal note to a customer enquiry."""
    now = datetime.now(timezone.utc)
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            # Check enquiry exists
            await cur.execute("SELECT id FROM enquiries WHERE id = %s", (enquiry_id,))
            if not await cur.fetchone():
                raise HTTPException(status_code=404, detail="Enquiry not found.")

            await cur.execute(
                """
                INSERT INTO staff_notes (enquiry_id, staff_id, content, created_at)
                VALUES (%s, %s, %s, %s)
                RETURNING id, enquiry_id, staff_id, content, created_at
                """,
                (enquiry_id, current_staff.id, payload.content, now)
            )
            note = await cur.fetchone()
            await conn.commit()

            logger.info(f"Staff {current_staff.email} added internal note to enquiry {enquiry_id}")

            return StaffNoteResponse(
                id=str(note["id"]),
                enquiry_id=str(note["enquiry_id"]),
                staff_id=str(note["staff_id"]),
                staff_name=current_staff.name or "Staff Coordinator",
                content=note["content"],
                created_at=note["created_at"]
            )
