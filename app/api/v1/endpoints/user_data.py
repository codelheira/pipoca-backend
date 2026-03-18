from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
from ....core.security import get_current_user
from ....core.supabase import supabase
from ....models.user import UserBase
import logging

router = APIRouter()
logger = logging.getLogger("pipoca-api")

@router.post("/favorites/{media_id}")
async def add_favorite(media_id: str, current_user: dict = Depends(get_current_user)):
    """Adiciona um item aos favoritos no Supabase."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Não autenticado")
    
    user_id = current_user.get("sub")
    try:
        # Busca favoritos atuais
        res = supabase.table("users").select("favorites").eq("id", user_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")
        
        favorites = res.data[0].get("favorites", [])
        if media_id not in favorites:
            favorites.append(media_id)
            supabase.table("users").update({"favorites": favorites}).eq("id", user_id).execute()
            
        return {"status": "success", "favorites": favorites}
    except Exception as e:
        logger.error(f"Error adding favorite: {e}")
        raise HTTPException(status_code=500, detail="Erro ao salvar favorito")

@router.delete("/favorites/{media_id}")
async def remove_favorite(media_id: str, current_user: dict = Depends(get_current_user)):
    """Remove um item dos favoritos no Supabase."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Não autenticado")
    
    user_id = current_user.get("sub")
    try:
        res = supabase.table("users").select("favorites").eq("id", user_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")
        
        favorites = res.data[0].get("favorites", [])
        if media_id in favorites:
            favorites.remove(media_id)
            supabase.table("users").update({"favorites": favorites}).eq("id", user_id).execute()
            
        return {"status": "success", "favorites": favorites}
    except Exception as e:
        logger.error(f"Error removing favorite: {e}")
        raise HTTPException(status_code=500, detail="Erro ao remover favorito")

@router.post("/history")
async def add_to_history(history_item: Dict[str, Any], current_user: dict = Depends(get_current_user)):
    """
    Adiciona um item ao histórico de visualização (ex: {slug, title, type, last_time}).
    Mantém apenas os últimos 50 itens.
    """
    if not current_user:
        return {"status": "skipped"} # Silencioso se não logado
    
    user_id = current_user.get("sub")
    try:
        res = supabase.table("users").select("history").eq("id", user_id).execute()
        if not res.data: return {"status": "user_not_found"}
        
        history = res.data[0].get("history", [])
        
        # Remove se já existir para desempilhar e colocar no topo (mais recente)
        history = [item for item in history if item.get("slug") != history_item.get("slug")]
        history.insert(0, history_item)
        
        # Limita a 50 itens
        history = history[:50]
        
        supabase.table("users").update({"history": history}).eq("id", user_id).execute()
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error updating history: {e}")
        return {"status": "error", "message": str(e)}
