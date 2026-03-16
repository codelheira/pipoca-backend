import httpx
from bs4 import BeautifulSoup
import re

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"}

def test_assistir_biz_search():
    query = "matrix"
    url = f"https://www.assistir.biz/busca?q={query}"
    
    with httpx.Client(follow_redirects=True) as client:
        r = client.get(url, headers=headers)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            cards = soup.find_all('div', class_='card')
            print(f"Found {len(cards)} cards on assistir.biz for '{query}':")
            for i, card in enumerate(cards[:5]):
                title_tag = card.find('h3', class_='card__title')
                name = title_tag.get_text().strip() if title_tag else "N/A"
                
                cat_tag = card.find('span', class_='card__category')
                info_text = cat_tag.get_text().strip() if cat_tag else "N/A"
                
                year_match = re.search(r'(\d{4})', info_text)
                year = year_match.group(1) if year_match else "NOT FOUND"
                
                print(f"{i+1}. {name} | Info: {info_text} | Extracted Year: {year}")
        else:
            print(f"Error: {r.status_code}")

if __name__ == "__main__":
    test_assistir_biz_search()
