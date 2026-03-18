import httpx
from bs4 import BeautifulSoup
import re
from typing import List, Dict, Any, Optional
from ..core.http_client import SafeAsyncClient
from ..core.config import settings
import logging

logger = logging.getLogger("pipoca-api")

async def search_provider(query: str) -> List[Dict[str, Any]]:
    """Busca no provedor de conteúdo assistir.app."""
    url = f"{settings.PROVIDERS['ASSISTIR']}/autosearch/{query}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": f"{settings.PROVIDERS['ASSISTIR']}/",
        "Origin": settings.PROVIDERS['ASSISTIR'],
        "x-requested-with": "XMLHttpRequest"
    }
    
    async with SafeAsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(url, headers=headers, timeout=10.0)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.error(f"Error searching provider: {e}")
            
    return []

async def get_item_html(tipo: str, slug: str) -> Optional[str]:
    """Busca o HTML bruto de um item no provedor."""
    # Mapeamento do tipo para o padrão do assistir.app
    tipo_norm = "filme" if any(k in tipo.lower() for k in ["filme", "movie"]) else "serie"
    url = f"{settings.PROVIDERS['ASSISTIR']}/{tipo_norm}/{slug}"
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    async with SafeAsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(url, headers=headers, timeout=20.0)
            if response.status_code == 200:
                return response.text
        except Exception as e:
            logger.error(f"Error getting item HTML: {e}")
            
    return None

def extract_players(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """Extrai iframes de players a partir do HTML."""
    players = []
    
    # Tenta encontrar a lista de players no HTML (layout atual do assistir.app)
    player_buttons = soup.find_all('button', id=re.compile(r'bt\d+'))
    
    for btn in player_buttons:
        label = btn.get_text().strip()
        target_id = btn.get('id', '').replace('bt', 'player-')
        target_div = soup.find('div', id=target_id)
        if target_div:
            iframe = target_div.find('iframe')
            if iframe and iframe.get('src'):
                src = iframe['src']
                if src.startswith('//'): src = f"https:{src}"
                players.append({"label": label, "url": src})

    # Fallback se não achou botões
    if not players:
        found_iframes = soup.find_all('iframe')
        for i, iframe in enumerate(found_iframes):
            src = iframe.get('src', '')
            if '/iframe/' in src or 'player' in src.lower():
                if src.startswith('//'): src = f"https:{src}"
                
                label = f"Player {i+1}"
                num_match = re.search(r'player[=\/](\d+)', src.lower())
                if num_match:
                    label = f"Player {num_match.group(1)}"

                players.append({"label": label, "url": src})

    # Ordenação preferencial (HLS primeiro)
    def player_sort_key(p):
        label = p['label'].lower()
        url = p['url'].lower()
        if 'hls' in url or 'hls' in label: return 0
        if 'player 1' in label: return 1
        if 'player 2' in label: return 2
        return 10

    players.sort(key=player_sort_key)
    return players

def extract_recommendations(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """Extrai itens da seção 'Talvez você goste!'."""
    recommendations = []
    try:
        rec_header = None
        for h2 in soup.find_all('h2', class_='section__title'):
            if "Talvez você goste" in h2.get_text():
                rec_header = h2
                break
        
        if rec_header:
            row = rec_header.find_parent('div', class_='row')
            if row:
                cards = row.find_all('div', class_='card')
                for card in cards:
                    try:
                        link_tag = card.find('a', class_='card__play') or card.find('a')
                        if not link_tag: continue
                        rec_path = link_tag['href']
                        
                        title_tag = card.find('h3', class_='card__title')
                        if title_tag:
                            rec_name = title_tag.get_text().strip()
                        else:
                            rec_name = link_tag.get_text().strip() or "Sem Título"
                        
                        cover_div = card.find('div', class_='card__cover')
                        rec_img = ""
                        if cover_div:
                            img_tag = cover_div.find('img')
                            if img_tag:
                                rec_img = img_tag.get('data-src') or img_tag.get('src') or ""
                            
                            if not rec_img or "data:" in rec_img:
                                source_tag = cover_div.find('source')
                                if source_tag:
                                    srcset = source_tag.get('srcset') or source_tag.get('data-srcset')
                                    if srcset:
                                        rec_img = srcset.split(',')[0].split(' ')[0]
                        
                        if rec_img and rec_img.startswith('//'): rec_img = "https:" + rec_img
                        
                        rec_slug = rec_path.split('/')[-1]
                        rec_tipo = "filme" if "/filme/" in rec_path else "serie"
                        
                        recommendations.append({
                            "name": rec_name,
                            "slug": rec_slug,
                            "tipo": rec_tipo,
                            "poster": rec_img
                        })
                    except: continue
    except Exception as e:
        logger.error(f"Error extracting recommendations: {e}")
    return recommendations
