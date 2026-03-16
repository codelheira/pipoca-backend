import httpx
from bs4 import BeautifulSoup
import re
import json

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# Busca a página de uma temporada específica
url_temp = 'https://www.assistir.biz/serie/stranger-things/temporada-1'
print(f"=== BUSCANDO: {url_temp} ===\n")

r = httpx.get(url_temp, headers=headers, follow_redirects=True, timeout=30)
soup = BeautifulSoup(r.text, 'html.parser')
print(f"Status: {r.status_code}")
print(f"URL Final: {r.url}")

# Salva HTML para análise
with open('temp_temporada.html', 'w', encoding='utf-8') as f:
    f.write(r.text)
print("HTML salvo em temp_temporada.html")

# Procura cards (episódios)
cards = soup.find_all('div', class_='card')
print(f"\nTotal de div.card: {len(cards)}")

# Filtra apenas episódios (não temporadas)
episodios = []
for card in cards:
    card_id = card.get('id', '')
    link = card.find('a', class_='card__play') or card.find('a', href=True)
    if link:
        href = link.get('href', '')
        # Episódios têm formato /serie/slug/temporada-X/episodio-Y
        if 'episodio' in href:
            title = card.find('h3', class_='card__title')
            rate = card.find('span', class_='card__rate')
            category = card.find('span', class_='card__category')
            episodios.append({
                'id': card_id,
                'href': href,
                'titulo': title.get_text().strip() if title else 'N/A',
                'nota': rate.get_text().strip() if rate else 'N/A',
                'info': category.get_text().strip() if category else 'N/A'
            })

print(f"\nEpisódios encontrados: {len(episodios)}")
for ep in episodios:
    print(f"  - {ep['id']}: {ep['titulo']} | {ep['href']}")

# Se não encontrou episódios, vamos ver a estrutura
if not episodios:
    print("\n=== ANALISANDO ESTRUTURA ALTERNATIVA ===")
    # Procura por outras estruturas
    sections = soup.find_all('section')
    for s in sections:
        s_class = s.get('class', [])
        print(f"Section: {s_class}")
    
    # Mostra todos os links
    print("\n=== TODOS OS LINKS ===")
    all_links = soup.find_all('a', href=True)
    for link in all_links:
        href = link.get('href', '')
        if '/serie/' in href and href.count('/') >= 3:
            print(f"  {href}")
