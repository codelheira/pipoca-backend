from pydantic import BaseModel, EmailStr
from typing import List, Optional

class UserBase(BaseModel):
    id: str
    email: EmailStr
    name: str
    picture: Optional[str] = None
    created_at: float
    
    # Novos campos
    role: str = "user" # user, creator, moderator, admin
    is_vip: bool = False
    vip_until: float = 0 # Timestamp de expiração
    
    favorites: List[str] = []
    history: List[str] = []

class GoogleAuthRequest(BaseModel):
    token: str

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserBase
