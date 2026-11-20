import hashlib
import random
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status, Response
from app.schemas import EnquiryCreate, EnquiryResponse
from app.db import get_db_connection

logger = logging.getLogger("mb_associates.enquiries")

router = APIRouter(prefix="/api/enquiries", tags=["Enquiries"])

def compute_idempotency_hash(name: str, contact_detail: str, pin_code: str) -> str:
    """
    Generate SHA-256 hash from canonical customer identity fields.
    Same customer submitting identical request can be deduplicated.
    """
    canonical = f"{name.strip().lower()}|{contact_detail.strip().lower()}|{pin_code.strip()}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

def generate_reference_code() -> str:
    """Generate a clean, professional reference code like MBA-202611-58291."""
    now = datetime.now(timezone.utc)
    year_month = now.strftime("%Y%m")
    digits = random.randint(10000, 99999)
    return f"MBA-{year_month}-{digits}"

@router.post(
    "",
    response_model=EnquiryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new customer solar enquiry or site visit request"
)
async def create_enquiry(payload: EnquiryCreate, response: Response):
    """
    Submit a customer solar enquiry or site visit request.
    
    - Validates server-side name, contact format, 6-digit Indian PIN, property type, and consent.
    - Uses database-backed idempotency:
      - An identical retry returns the original reference (200 OK).
      - The same customer contact details with conflicting request parameters returns 409 Conflict.
    - Saves with status 'New' and auto-generated reference code.
    """
    idempotency_hash = compute_idempotency_hash(
        payload.name, payload.contact_detail, payload.pin_code
    )

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # 1. Check for existing enquiry by idempotency_hash
                await cur.execute(
                    """
                    SELECT id, reference, property_type, request_type, assistance, status, created_at
                    FROM enquiries
                    WHERE idempotency_hash = %s
                    LIMIT 1
                    """,
                    (idempotency_hash,)
                )
                existing = await cur.fetchone()

                if existing:
                    # Compare payload to determine if identical retry or conflicting request
                    existing_assistance = set(existing.get("assistance") or [])
                    new_assistance = set(payload.assistance)
                    
                    is_identical = (
                        existing["property_type"].strip().lower() == payload.property_type.strip().lower() and
                        existing["request_type"].strip().lower() == payload.request_type.strip().lower() and
                        existing_assistance == new_assistance
                    )

                    if is_identical:
                        # Return original reference with status 200 (idempotent duplicate)
                        logger.info(f"Idempotent retry for reference {existing['reference']}")
                        response.status_code = status.HTTP_200_OK
                        return EnquiryResponse(
                            reference=existing["reference"],
                            status=existing["status"],
                            created_at=existing["created_at"],
                            message="Your enquiry was already received and is registered under this reference.",
                            is_duplicate=True
                        )
                    else:
                        # Same key, different request details -> 409 Conflict
                        logger.warning(
                            f"Idempotency conflict for contact: {payload.contact_detail}. Existing ref: {existing['reference']}"
                        )
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=(
                                f"An enquiry with these contact details already exists with different request parameters. "
                                f"Your existing reference code is {existing['reference']}. Please contact our advisory desk."
                            )
                        )

                # 2. Generate a unique reference code
                reference = None
                for _ in range(5):
                    candidate_ref = generate_reference_code()
                    await cur.execute("SELECT 1 FROM enquiries WHERE reference = %s", (candidate_ref,))
                    if not await cur.fetchone():
                        reference = candidate_ref
                        break

                if not reference:
                    # Fallback with timestamp microsecond
                    now_ts = int(datetime.now(timezone.utc).timestamp() * 1000) % 1000000
                    reference = f"MBA-{datetime.now(timezone.utc).strftime('%Y%m')}-{now_ts:06d}"

                # 3. Insert new enquiry
                now = datetime.now(timezone.utc)
                await cur.execute(
                    """
                    INSERT INTO enquiries (
                        reference,
                        idempotency_hash,
                        name,
                        contact_method,
                        contact_detail,
                        pin_code,
                        property_type,
                        request_type,
                        assistance,
                        roof_area,
                        monthly_bill,
                        notes,
                        consent,
                        status,
                        created_at,
                        updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'New', %s, %s
                    )
                    RETURNING id, reference, status, created_at
                    """,
                    (
                        reference,
                        idempotency_hash,
                        payload.name,
                        payload.contact_method,
                        payload.contact_detail,
                        payload.pin_code,
                        payload.property_type,
                        payload.request_type,
                        payload.assistance,
                        payload.roof_area,
                        payload.monthly_bill,
                        payload.notes,
                        payload.consent,
                        now,
                        now
                    )
                )
                row = await cur.fetchone()
                await conn.commit()

                logger.info(f"Successfully registered new enquiry {row['reference']} for {payload.name}")

                return EnquiryResponse(
                    reference=row["reference"],
                    status=row["status"],
                    created_at=row["created_at"],
                    message="Assistance request registered successfully.",
                    is_duplicate=False
                )

    except HTTPException:
        raise
    except RuntimeError as r_err:
        logger.error(f"Database unavailable: {r_err}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The enquiry submission service is temporarily unavailable. Please retry shortly or contact support."
        )
    except Exception as exc:
        logger.error(f"Unexpected error saving enquiry: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while saving your enquiry. Please retry."
        )
