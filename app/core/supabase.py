from typing import Optional
from supabase import create_client, Client
from .config import settings
import logging

logger = logging.getLogger(__name__)

def get_supabase() -> Optional[Client]:
    """Retorna uma instância do cliente Supabase ou None se não configurado."""
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        logger.warning("SUPABASE_URL ou SUPABASE_KEY não configurados! Auth não funcionará.")
        return None
    try:
        return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    except Exception as e:
        logger.error(f"Erro ao conectar no Supabase: {e}")
        return None

supabase = get_supabase()
