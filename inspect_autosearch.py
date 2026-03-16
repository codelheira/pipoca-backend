import httpx
import json

def inspect_restuls():
    url = "https://assistir.app/autosearch/matrix"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    }
    r = httpx.get(url, headers=headers)
    if r.status_code == 200:
        data = r.json()
        if data:
            print("Keys in autosearch item:")
            print(list(data[0].keys()))
            print("\nExample item:")
            print(json.dumps(data[0], indent=2))
    else:
        print(f"Error: {r.status_code}")

if __name__ == "__main__":
    inspect_restuls()
