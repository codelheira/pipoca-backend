from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio
import logging
from .core.config import settings
from .core.dns_patch import apply_dns_patch
from .api.v1.api_router import api_v1_router
from .socket.events import register_socket_events

# Configuração de Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pipoca-api")

# Aplica o Patch de DNS
apply_dns_patch()

# Inicialização do FastAPI
app = FastAPI(title=settings.PROJECT_NAME)

# Middleware de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicialização do Socket.io
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*', logger=True, engineio_logger=True)

# Registra Eventos do Socket.io
register_socket_events(sio)

# ASGI App para montar o SIO no FastAPI
sio_app = socketio.ASGIApp(sio, app)

# Inclusão dos Routers
app.include_router(api_v1_router, prefix="/api/v1")

# Rota Raiz (Health Check)
@app.get("/")
async def root():
    return {
        "message": f"{settings.PROJECT_NAME} is running with new modular architecture!",
        "version": "1.0.0"
    }
