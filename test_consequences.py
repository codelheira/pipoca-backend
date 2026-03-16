import httpx
import asyncio

async def test():
    client = httpx.AsyncClient()
    params = {
        'api_key': 'fb7bb23f03b6994dafc674c074d01761', 
        'query': 'Consequências', 
        'language': 'pt-BR'
    }
    res = await client.get('https://api.themoviedb.org/3/search/multi', params=params)
    data = res.json()
    print(f"Status: {res.status_code}")
    results = data.get('results', [])
    print(f"Found {len(results)} results")
    for r in results:
        title = r.get('title') or r.get('name')
        poster = r.get('poster_path')
        print(f"- {title} | Poster: {poster}")
    await client.aclose()

if __name__ == "__main__":
    asyncio.run(test())
