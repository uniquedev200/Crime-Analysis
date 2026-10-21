import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User
from backend.auth import (
    hash_password, verify_password, create_access_token,
    get_current_user_optional
)

router = APIRouter(prefix="/api/auth", tags=["Authentication & Access Control"])

class SignupRequest(BaseModel):
    officerName: str
    badgeNumber: str
    password: str
    department: Optional[str] = "CID Crime Branch"
    unit: Optional[str] = None
    role: Optional[str] = "investigator"
    clearanceLevel: Optional[str] = "Level 2: Investigator"

class LoginRequest(BaseModel):
    badgeNumber: str
    password: str

@router.post("/signup", summary="Official Officer Registration")
async def signup(req: SignupRequest, db: Session = Depends(get_db)):
    badge = req.badgeNumber.strip()
    existing = db.query(User).filter(User.badge_number == badge).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Officer ID {badge} is already registered."
        )

    # Determine clearance level if not passed
    clearance = req.clearanceLevel or "Level 2: Investigator"
    dept = req.department or req.unit or "CID Crime Branch"

    user = User(
        badge_number=badge,
        officer_name=req.officerName.strip(),
        password_hash=hash_password(req.password),
        department=dept,
        unit=req.unit or dept,
        role=req.role or "investigator",
        clearance_level=clearance,
        created_at=datetime.datetime.utcnow(),
        last_login=datetime.datetime.utcnow()
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": user.badge_number, "role": user.role})
    now_iso = datetime.datetime.utcnow().isoformat() + "Z"

    return {
        "success": True,
        "token": token,
        "session": {
            "badgeNumber": user.badge_number,
            "officerName": user.officer_name,
            "department": user.department,
            "clearanceLevel": user.clearance_level,
            "role": user.role,
            "signedInAt": now_iso
        }
    }

@router.post("/login", summary="Officer Authentication")
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    badge = req.badgeNumber.strip()
    user = db.query(User).filter(User.badge_number == badge).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Officer ID or security passcode."
        )

    user.last_login = datetime.datetime.utcnow()
    db.commit()

    token = create_access_token({"sub": user.badge_number, "role": user.role})
    now_iso = datetime.datetime.utcnow().isoformat() + "Z"

    return {
        "success": True,
        "token": token,
        "session": {
            "badgeNumber": user.badge_number,
            "officerName": user.officer_name,
            "department": user.department,
            "clearanceLevel": user.clearance_level,
            "role": user.role,
            "signedInAt": now_iso
        }
    }

@router.get("/me", summary="Current Officer Session")
async def get_me(user: Optional[User] = Depends(get_current_user_optional)):
    if not user:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "badgeNumber": user.badge_number,
        "officerName": user.officer_name,
        "department": user.department,
        "clearanceLevel": user.clearance_level,
        "role": user.role
    }
