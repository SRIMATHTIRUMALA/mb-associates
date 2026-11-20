import re
from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator, model_validator

# Valid choices
ContactMethodType = Literal["phone", "whatsapp", "email"]
RequestType = Literal["general", "site_visit"]
EnquiryStatus = Literal["New", "Contacted", "In Progress", "Closed"]

class EnquiryCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=120, description="Full customer name as per electricity bill")
    contact_method: ContactMethodType = Field(default="phone", description="Preferred contact method")
    contact_detail: str = Field(..., min_length=5, max_length=120, description="10-digit mobile number or email address")
    pin_code: str = Field(..., description="6-digit Indian Postal PIN Code")
    property_type: str = Field(..., min_length=2, max_length=100, description="Residential Villa, Housing Society, Commercial, Industrial, etc.")
    request_type: RequestType = Field(default="general", description="general enquiry or site_visit request")
    assistance: List[str] = Field(default_factory=list, description="Array of requested assistance scopes")
    roof_area: Optional[str] = Field(default=None, max_length=100, description="Estimated roof area")
    monthly_bill: Optional[float] = Field(default=None, ge=0, description="Average monthly electricity bill in INR")
    notes: Optional[str] = Field(default=None, max_length=2000, description="Rooftop constraints, instructions or remarks")
    consent: bool = Field(..., description="Consent to be contacted regarding solar requirements")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        clean = v.strip()
        if len(clean) < 2:
            raise ValueError("Full Name must be at least 2 characters long.")
        if re.search(r"[<>{}[\]\\]", clean):
            raise ValueError("Name contains invalid characters.")
        return clean

    @field_validator("pin_code")
    @classmethod
    def validate_pin_code(cls, v: str) -> str:
        clean = re.sub(r"\D", "", v)
        if not re.match(r"^[1-9][0-9]{5}$", clean):
            raise ValueError("PIN Code must be a valid 6-digit Indian postal code (e.g. 500001).")
        return clean

    @field_validator("consent")
    @classmethod
    def validate_consent(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("You must consent to being contacted to submit an enquiry.")
        return v

    @field_validator("assistance")
    @classmethod
    def validate_assistance(cls, v: List[str]) -> List[str]:
        cleaned = [item.strip() for item in v if item and item.strip()]
        if not cleaned:
            # Default to general consultation if none selected
            cleaned = ["Solar Feasibility Assessment"]
        return cleaned

    @model_validator(mode="after")
    def validate_contact_detail_format(self) -> "EnquiryCreate":
        raw = self.contact_detail.strip()
        method = self.contact_method

        if method == "email":
            # Simple standard email validation
            email_pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
            if not re.match(email_pattern, raw):
                raise ValueError("A valid email address is required when preferred contact method is Email.")
            self.contact_detail = raw.lower()
        else:
            # Phone or WhatsApp: extract digits
            digits = re.sub(r"\D", "", raw)
            # Handle +91 or leading 0
            if digits.startswith("91") and len(digits) == 12:
                digits = digits[2:]
            elif digits.startswith("0") and len(digits) == 11:
                digits = digits[1:]
            
            if len(digits) != 10 or not digits[0] in "6789":
                raise ValueError(
                    f"A valid 10-digit Indian mobile number starting with 6, 7, 8, or 9 is required for {method.capitalize()}."
                )
            self.contact_detail = digits
        
        return self

class EnquiryResponse(BaseModel):
    reference: str
    status: EnquiryStatus
    created_at: datetime
    message: str = "Assistance request registered successfully."
    is_duplicate: bool = False

class StatusUpdate(BaseModel):
    status: EnquiryStatus

class StaffNoteCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000, description="Internal staff note content")

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Note content cannot be empty.")
        return clean

class StaffNoteResponse(BaseModel):
    id: str
    enquiry_id: str
    staff_id: Optional[str] = None
    staff_name: Optional[str] = None
    content: str
    created_at: datetime

class EnquiryDetail(BaseModel):
    id: str
    reference: str
    name: str
    contact_method: str
    contact_detail: str
    pin_code: str
    property_type: str
    request_type: str
    assistance: List[str]
    roof_area: Optional[str] = None
    monthly_bill: Optional[float] = None
    notes: Optional[str] = None
    consent: bool
    status: EnquiryStatus
    created_at: datetime
    updated_at: datetime
    staff_notes: List[StaffNoteResponse] = []

class StaffMember(BaseModel):
    id: str
    auth_user_id: str
    email: str
    name: Optional[str] = None
    role: str = "coordinator"
    created_at: datetime

class StaffLoginRequest(BaseModel):
    email: str
    password: str
    csrf_token: Optional[str] = None
