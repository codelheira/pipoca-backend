import httpx
import json

def test_api():
    url = "http://localhost:8000/api/search/matrix"
    try:
        r = httpx.get(url, timeout=10.0)
        if r.status_code == 200:
            results = r.json()
            if results:
                print("Raw item from /api/search:")
                print(json.dumps(results[0], indent=2))
        else:
            print(f"API Error: {r.status_code}")
    except Exception as e:
        print(f"Connection Error: {e}")

if __name__ == "__main__":
    test_api()
