from fastapi import APIRouter
from .endpoints import search, movies, series, auth, user_data, home, genres

api_v1_router = APIRouter()

# 1. Home e Categorias
api_v1_router.include_router(home.router, prefix="/home", tags=["Home"])
api_v1_router.include_router(genres.router, prefix="/categoria", tags=["Categorias"])

# 2. Busca (Suporta /search e /busca)
api_v1_router.include_router(search.router, prefix="/search", tags=["Busca"])
api_v1_router.include_router(search.router, prefix="/busca", tags=["Busca"])

# 3. Filmes (Suporta /info e /filmes/...)
api_v1_router.include_router(movies.router, tags=["Filmes"]) # For /info/{tipo}/{slug}
api_v1_router.include_router(movies.router, prefix="/filmes", tags=["Filmes"]) # For /filmes/all

# 4. Séries (Suporta /serie e /series/...)
api_v1_router.include_router(series.router, prefix="/serie", tags=["Séries"]) # For /serie/{slug}
api_v1_router.include_router(series.router, prefix="/series", tags=["Séries"]) # For /series/all

# 5. Autenticação e Usuário
api_v1_router.include_router(auth.router, prefix="/auth", tags=["Autenticação"])
api_v1_router.include_router(user_data.router, prefix="/user", tags=["Dados de Usuário"])
