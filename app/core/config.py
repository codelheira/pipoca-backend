from pydantic_settings import BaseSettings
from typing import List, Optional
import os
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    PROJECT_NAME: str = "Pipoca Filmes API"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "chave_fallback_apenas_dev")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 1 semana
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: Optional[str] = os.getenv("GOOGLE_CLIENT_SECRET")
    
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    
    CORS_ORIGINS: List[str] = [
        "https://pipocafilmes.pages.dev",
        "http://localhost:5173",
        "http://localhost:3000",
        "*" # Mantemos o * caso você queira desativar credentials depois, mas por agora o FastAPI usará os acima.
    ]
    
    TMDB_KEYS: List[str] = [
        'fb7bb23f03b6994dafc674c074d01761', 'e55425032d3d0f371fc776f302e7c09b',
        '8301a21598f8b45668d5711a814f01f6', '8cf43ad9c085135b9479ad5cf6bbcbda',
        'da63548086e399ffc910fbc08526df05', '13e53ff644a8bd4ba37b3e1044ad24f3',
        '269890f657dddf4635473cf4cf456576', 'a2f888b27315e62e471b2d587048f32e',
        '8476a7ab80ad76f0936744df0430e67c', '5622cafbfe8f8cfe358a29c53e19bba0',
        'ae4bd1b6fce2a5648671bfc171d15ba4', '257654f35e3dff105574f97fb4b97035',
        '2f4038e83265214a0dcd6ec2eb3276f5', '9e43f45f94705cc8e1d5a0400d19a7b7',
        'af6887753365e14160254ac7f4345dd2', '06f10fc8741a672af455421c239a1ffc',
        '09ad8ace66eec34302943272db0e8d2c'
    ]
    
    GENRE_MAP: dict = {
        28: "Ação", 12: "Aventura", 16: "Animação", 35: "Comédia", 80: "Crime", 
        99: "Documentário", 18: "Drama", 10751: "Família", 14: "Fantasia", 
        36: "História", 27: "Terror", 10402: "Música", 9648: "Mistério", 
        10749: "Romance", 878: "Ficção", 10770: "Cinema TV", 
        53: "Suspense", 10752: "Guerra", 37: "Faroeste",
        10759: "Ação e Aventura", 10762: "Kids", 10763: "News", 
        10764: "Reality", 10765: "Sci-Fi & Fantasy", 10766: "Soap", 
        10767: "Talk", 10768: "War & Politics"
    }
    
    CACHE_EXPIRATION: int = 24 * 60 * 60  # 24 horas em segundos
    PROVIDERS: dict = {
        "ASSISTIR": "https://assistir.app"
    }

    class Config:
        case_sensitive = True

settings = Settings()
