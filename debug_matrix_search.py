import httpx
import json

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://assistir.app/",
    "Origin": "https://assistir.app",
    "x-requested-with": "XMLHttpRequest"
}

def test_matrix_search():
    query = "matrix"
    url = f"https://assistir.app/autosearch/{query}"
    
    with httpx.Client(follow_redirects=True) as client:
        r = client.get(url, headers=headers)
        if r.status_code == 200:
            results = r.json()
            print(f"Results from assistir.app for '{query}':")
            for item in results[:5]:
                print(f"  - Nome: {item.get('nome')} | Ano: {item.get('ano')} | Slug: {item.get('slug')}")
                
                # Test TMDB search for this specific title/year
                tmdb_key = 'fb7bb23f03b6994dafc674c074d01761'
                title = item.get('nome')
                year = item.get('ano')
                
                tmdb_params = {
                    "api_key": tmdb_key,
                    "query": title,
                    "language": "pt-BR",
                    "include_adult": "false"
                }
                if year: tmdb_params["year"] = year
                
                tm_res = client.get("https://api.themoviedb.org/3/search/multi", params=tmdb_params)
                if tm_res.status_code == 200:
                    tm_json = tm_res.json()
                    tm_results = tm_json.get("results", [])
                    print(f"    TMDB found {len(tm_results)} results.")
                    if tm_results:
                        first = tm_results[0]
                        print(f"    First TMDB result: {first.get('title') or first.get('name')} ({first.get('release_date', '')[:4]}) - Poster: {first.get('poster_path')}")
        else:
            print(f"Error: {r.status_code}")

if __name__ == "__main__":
    test_matrix_search()
