import httpx
import json

def test_home():
    url = "http://localhost:8000/api/home"
    try:
        r = httpx.get(url, timeout=15.0)
        if r.status_code == 200:
            data = r.json()
            sections = ["featured", "most_watched", "recently_added", "releases_2026", "series"]
            for section in sections:
                items = data.get(section, [])
                print(f"\nSection: {section} ({len(items)} items)")
                for item in items[:2]:
                    print(f"  - {item.get('nome')} | Capa: {item.get('capa')}")
        else:
            print(f"API Error: {r.status_code}")
    except Exception as e:
        print(f"Connection Error: {e}")

if __name__ == "__main__":
    test_home()
