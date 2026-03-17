import asyncio
import websockets
import json

async def test_ws():
    # Usando o token da sala que sabemos que existe no debug
    token = "81cbe68c-d9b8-48b7-a7b4-b96ffcfae8ea"
    user_id = "test_bot_external"
    url = f"wss://pipoca-backend-jazs.onrender.com/api/transmission/ws/{token}/{user_id}"
    
    print(f"Tentando conectar em {url}...")
    try:
        async with websockets.connect(url) as websocket:
            print("Conectado!")
            await websocket.send(json.dumps({"type": "ping"}))
            print("Mensagem enviada.")
            response = await websocket.recv()
            print(f"Resposta: {response}")
    except Exception as e:
        print(f"Erro na conexão: {e}")

if __name__ == "__main__":
    asyncio.run(test_ws())
