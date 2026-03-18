from pydantic import BaseModel, EmailStr
from typing import List, Optional

class UserBase(BaseModel):
    id: str
    email: EmailStr
    name: str
    picture: Optional[str] = None
    created_at: float
    favorites: List[str] = []
    history: List[str] = []

class GoogleAuthRequest(BaseModel):
    token: str

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserBase
