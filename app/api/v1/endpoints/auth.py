from fastapi import APIRouter, HTTPException, Request, Depends
import time
import json
import os
from ....core.security import verify_google_token, create_access_token, get_current_user
from ....models.user import GoogleAuthRequest, AuthResponse, UserBase
import logging

router = APIRouter()
logger = logging.getLogger("pipoca-api")

from ....core.supabase import supabase
from ....models.user import GoogleAuthRequest, AuthResponse, UserBase
import logging
from datetime import datetime

router = APIRouter()
logger = logging.getLogger("pipoca-api")

@router.post("/google", response_model=AuthResponse)
async def google_auth(auth_req: GoogleAuthRequest):
    """Autenticação via Google SDK vinculada ao Supabase."""
    user_info = verify_google_token(auth_req.token)
    if not user_info:
        raise HTTPException(status_code=401, detail="Token do Google inválido")
    
    google_id = user_info["sub"]
    
    try:
        # Busca usuário no Supabase
        res = supabase.table("users").select("*").eq("id", google_id).execute()
        
        user_data = None
        if not res.data:
            # Novo usuário
            new_user = {
                "id": google_id,
                "email": user_info["email"],
                "name": user_info["name"],
                "picture": user_info["picture"],
                "created_at": time.time(), # Usando timestamp float compatível com o modelo
                "favorites": [],
                "history": []
            }
            try:
                ins_res = supabase.table("users").insert(new_user).execute()
                user_data = ins_res.data[0]
                logger.info(f"New user registered: {user_info['email']}")
            except Exception as e:
                logger.error(f"Erro ao inserir novo usuário no Supabase: {e}")
                raise
        else:
            # Login: atualiza informações básicas
            update_data = {
                "name": user_info["name"],
                "picture": user_info["picture"]
            }
            try:
                up_res = supabase.table("users").update(update_data).eq("id", google_id).execute()
                user_data = up_res.data[0]
                logger.info(f"User login: {user_info['email']}")
            except Exception as e:
                logger.error(f"Erro ao atualizar usuário no Supabase: {e}")
                raise
            
        access_token = create_access_token(data={"sub": google_id, "email": user_info["email"]})
        
        return AuthResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserBase(**user_data)
        )
        
    except Exception as e:
        logger.error(f"Supabase Auth Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro no banco de dados: {str(e)}")

@router.get("/me", response_model=UserBase)
async def get_me(current_user: dict = Depends(get_current_user)):
    """Busca o perfil do usuário logado no Supabase."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Não autenticado")
    
    google_id = current_user.get("sub")
    try:
        res = supabase.table("users").select("*").eq("id", google_id).execute()
        if res.data:
            return UserBase(**res.data[0])
    except Exception as e:
        logger.error(f"Supabase GET Error: {e}")
        
    raise HTTPException(status_code=404, detail="Usuário não encontrado")
