from .endpoints import search, movies, series, auth, user_data

api_v1_router = APIRouter()

# Registro de sub-routers
api_v1_router.include_router(search.router, prefix="/search", tags=["Busca"])
api_v1_router.include_router(movies.router, prefix="/filmes", tags=["Filmes"])
api_v1_router.include_router(series.router, prefix="/series", tags=["Séries"])
api_v1_router.include_router(auth.router, prefix="/auth", tags=["Autenticação"])
api_v1_router.include_router(user_data.router, prefix="/user", tags=["Dados de Usuário"])
