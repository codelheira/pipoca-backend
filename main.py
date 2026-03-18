import sys
import os

# Adiciona o diretório atual ao PATH para garantir que o pacote 'app' seja encontrado
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from app.main import sio_app
except Exception as e:
    print(f"CRITICAL ERROR LOADING APP: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Expõe para o Gunicorn
app = sio_app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), reload=True)
