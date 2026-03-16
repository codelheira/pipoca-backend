# Pipoca Filmes API (Backend)

Backend em Python (FastAPI) para o projeto Pipoca Filmes.

## Como implantar no Render

1. Crie um novo **Web Service** no Render.
2. Conecte este repositório.
3. Configure os detalhes abaixo:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app`
4. Adicione as variáveis de ambiente necessárias (se houver).

## Estrutura
- `main.py`: Ponto de entrada da API.
- `auth.py`: Lógica de autenticação Google.
- `requirements.txt`: Dependências do Python.
