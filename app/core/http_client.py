import httpx
import random
from .config import settings

class SafeAsyncClient(httpx.AsyncClient):
    """Client que usa configurações otimizadas para evitar erros de SSL e DNS"""
    def __init__(self, *args, **kwargs):
        # Usamos verificador de SSL padrão, mas com tolerância a versões de TLS
        if "verify" not in kwargs:
            kwargs["verify"] = False # Mantido False para o assistir.app que pode ter certs variados em proxies
        
        # Headers padrão para parecer um navegador real e evitar bloqueios de handshake
        if "headers" not in kwargs:
            kwargs["headers"] = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            }
        
        # Aumentamos o limite de conexões e timeout
        if "timeout" not in kwargs:
            kwargs["timeout"] = httpx.Timeout(20.0, connect=10.0)
            
        super().__init__(*args, **kwargs)

def get_random_tmdb_key():
    """Retorna uma chave aleatória da lista do TMDB configurada em settings."""
    return random.choice(settings.TMDB_KEYS)
