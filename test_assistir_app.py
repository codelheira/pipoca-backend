import httpx
import json

def test_external_search():
    url = "https://assistir.app/autosearch/matrix"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    }
    r = httpx.get(url, headers=headers)
    if r.status_code == 200:
        print(f"Status: {r.status_code}")
        print("Response head (first 500 chars):")
        print(r.text[:500])
        try:
            data = r.json()
            if data:
                print("\nFirst item 'ano' field:")
                print(data[0].get('ano'))
        except:
            print("\nCould not parse JSON")
    else:
        print(f"Error: {r.status_code}")

if __name__ == "__main__":
    test_external_search()
