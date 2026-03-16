import httpx

def test_endpoint(name, url):
    print(f"\n--- Testing {name} ({url}) ---")
    try:
        r = httpx.get(url, timeout=10.0)
        if r.status_code == 200:
            results = r.json()
            print(f"Total results: {len(results)}")
            for item in results[:3]:
                nome = item.get('nome') or item.get('title') or 'N/A'
                capa = item.get('capa') or 'N/A'
                ano = item.get('ano') or 'N/A'
                genero = item.get('genero') or 'N/A'
                print(f"Item: {nome} ({ano}) [{genero}] | Capa: {capa}")
        else:
            print(f"API Error: {r.status_code}")
    except Exception as e:
        print(f"Connection Error: {e}")

if __name__ == "__main__":
    test_endpoint("Autosearch", "http://localhost:8000/api/search/matrix")
    test_endpoint("Full Search", "http://localhost:8000/api/busca/matrix")
