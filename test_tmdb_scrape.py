import httpx
from bs4 import BeautifulSoup
import re

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
}

def test_tmdb_scrape(tmdb_id, type="movie"):
    url = f"https://www.themoviedb.org/{type}/{tmdb_id}/discuss/category/5047951f760ee3318900009a"
    print(f"Testing URL: {url}")
    
    with httpx.Client(follow_redirects=True, headers=headers) as client:
        r = client.get(url)
        print(f"Status: {r.status_code}")
        soup = BeautifulSoup(r.text, 'html.parser')
        
        threads = []
        # Procura por links de discussão. Podem ser /movie/ID/discuss/THREAD_ID ou /movie/ID-SLUG/discuss/THREAD_ID
        pattern = re.compile(r'/discuss/[0-9a-f]{24}')
        
        # Mostra todos os links que batem no regex
        for a in soup.find_all('a', href=True):
            href = a['href']
            if pattern.search(href):
                title = a.get_text(strip=True)
                print(f"Found candidate: {title} | {href}")

if __name__ == "__main__":
    test_tmdb_scrape(664413) # 365 Days
