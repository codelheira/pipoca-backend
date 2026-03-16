import httpx

def test_specific_search():
    tmdb_key = 'fb7bb23f03b6994dafc674c074d01761'
    url = "https://api.themoviedb.org/3/search/movie"
    params = {
        "api_key": tmdb_key,
        "query": "Matrix",
        "language": "pt-BR"
    }
    
    with httpx.Client() as client:
        r = client.get(url, params=params)
        if r.status_code == 200:
            results = r.json().get("results", [])
            if results:
                first = results[0]
                print(f"Keys in a 'search/movie' result: {list(first.keys())}")
                print(f"media_type present? {'media_type' in first}")
        else:
            print(f"Error: {r.status_code}")

if __name__ == "__main__":
    test_specific_search()
