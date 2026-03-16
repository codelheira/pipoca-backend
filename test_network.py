import httpx
import asyncio

async def test():
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get("https://www.google.com", timeout=10.0)
            print(f"Google status: {resp.status_code}")
            
            resp2 = await client.get("https://assistir.biz/inicio", timeout=10.0)
            print(f"Assistir.biz (no-www) status: {resp2.status_code}")
            
            resp3 = await client.get("https://assistir.app/", timeout=10.0)
            print(f"Assistir.app status: {resp3.status_code}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test())
