"""
routers/auth.py
User authentication endpoints.
"""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from core.config import get_settings, Settings
from core.security import create_jwt

router = APIRouter()

USER_DB = {
    "13525001": {"password": "mahasiswa1", "name": "Michael Abduh"},
    "13525002": {"password": "mahasiswa2", "name": "Danesh Zacky"},
    "13525003": {"password": "mahasiswa3", "name": "Naufal Salastra"},
}

class UserLoginRequest(BaseModel):
    nim:      str = Field(..., min_length=5)
    password: str = Field(..., min_length=4)

@router.post("/user-login", summary="User login → JWT")
async def user_login(
    req: UserLoginRequest,
    settings: Settings = Depends(get_settings),
) -> dict:
    user = USER_DB.get(req.nim)
    if not user or user["password"] != req.password:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            detail="NIM atau password salah.")
    token = create_jwt(
        sub="dashboard_user",
        extra={"nim": req.nim, "name": user["name"]},
        ttl_hours=8,
        settings=settings,
    )
    return {
        "access_token": token,
        "token_type":   "bearer",
        "nim":          req.nim,
        "name":         user["name"],
    }