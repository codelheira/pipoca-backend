import httpx
import json

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
}

def inspect_tmdb_results(query):
    tmdb_key = 'fb7bb23f03b6994dafc674c074d01761'
    url = "https://api.themoviedb.org/3/search/multi"
    params = {
        "api_key": tmdb_key,
        "query": query,
        "language": "pt-BR",
        "include_adult": "false"
    }
    
    with httpx.Client() as client:
        r = client.get(url, params=params)
        if r.status_code == 200:
            results = r.json().get("results", [])
            print(f"TMDB Results for '{query}':")
            for i, res in enumerate(results[:10]):
                m_type = res.get("media_type")
                name = res.get("title") or res.get("name")
                date = res.get("release_date") or res.get("first_air_date") or "N/A"
                pop = res.get("popularity", 0)
                poster = res.get("poster_path")
                print(f"{i+1}. [{m_type}] {name} ({date}) | Pop: {pop} | Poster: {poster}")
        else:
            print(f"Error: {r.status_code}")

if __name__ == "__main__":
    inspect_tmdb_results("Matrix")
