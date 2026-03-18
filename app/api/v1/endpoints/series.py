from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from bs4 import BeautifulSoup
import re
from ....services.scraping import get_item_html, extract_players, extract_recommendations
from ....services.tmdb import search_tmdb, get_tmdb_details, enrich_item_list
from ....services.cache import cache
from ....models.series import SeriesDetail, Season, Episode
from ....core.http_client import SafeAsyncClient
from ....core.config import settings
import logging

router = APIRouter()
logger = logging.getLogger("pipoca-api")

@router.get("/{slug}", response_model=SeriesDetail)
async def get_serie_details(slug: str):
    """
    Busca detalhes de uma série incluindo lista de temporadas.
    """
    cache_key = f"serie_{slug}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    url = f"{settings.PROVIDERS['ASSISTIR']}/iframe/{slug}"
    async with SafeAsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(url, timeout=30.0)
            if response.status_code != 200:
                raise HTTPException(status_code=404, detail="Série não encontrada")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Título
            h1 = soup.find('h1')
            title = h1.get_text().strip() if h1 else slug.replace('-', ' ').title()
            name_only = re.sub(r'\(\d{4}\)', '', title).strip()
            
            # Ano
            year_match = re.search(r'\((\d{4})\)', title)
            year = year_match.group(1) if year_match else ""
            
            # Sinopse
            synopsis = ""
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc:
                synopsis = meta_desc.get('content', '').strip()
            
            # Nota
            rating = ""
            rate_tag = soup.find('span', class_='card__rate')
            if rate_tag:
                rating = rate_tag.get_text().strip()
            
            # Temporadas
            temporadas = []
            temporada_cards = soup.find_all('div', id=re.compile(r'^temporada-\d+$'))
            
            for card in temporada_cards:
                temp_id = card.get('id', '')
                temp_num = int(temp_id.replace('temporada-', ''))
                
                temp_title_tag = card.find('h3', class_='card__title')
                temp_title = temp_title_tag.get_text().strip() if temp_title_tag else f"Temporada {temp_num}"
                
                temp_poster = ""
                img = card.find('img')
                if img:
                    temp_poster = img.get('data-src') or img.get('src') or ""
                    if temp_poster.startswith('//'):
                        temp_poster = 'https:' + temp_poster
                
                play_link = card.find('a', class_='card__play')
                temp_link = play_link.get('href', '') if play_link else f"/serie/{slug}/temporada-{temp_num}"
                
                temporadas.append(Season(
                    numero=temp_num,
                    titulo=temp_title,
                    poster=temp_poster,
                    link=temp_link
                ))
            
            temporadas.sort(key=lambda x: x.numero)
            
            # TMDB Enrichment
            tmdb_data = {}
            results = await search_tmdb(name_only, "tv", year)
            if results:
                tmdb_data = await get_tmdb_details(results[0]["id"], "tv")
            
            result = SeriesDetail(
                title=title,
                name=name_only,
                slug=slug,
                synopsis=tmdb_data.get("overview") or synopsis,
                year=year or (tmdb_data.get("first_air_date", "")[:4] if tmdb_data else ""),
                rating=float(rating) if rating else tmdb_data.get("vote_average", 0.0),
                poster=f"https://image.tmdb.org/t/p/w500{tmdb_data['poster_path']}" if tmdb_data.get("poster_path") else "",
                backdrop=f"https://image.tmdb.org/t/p/original{tmdb_data['backdrop_path']}" if tmdb_data.get("backdrop_path") else "",
                genres=[g["name"] for g in tmdb_data.get("genres", [])] if tmdb_data.get("genres") else [],
                temporadas=temporadas,
                total_temporadas=len(temporadas),
                id_tmdb=tmdb_data.get("id"),
                status=tmdb_data.get("status", ""),
                trailer=next((f"https://www.youtube.com/embed/{v['key']}" for v in tmdb_data.get("videos", {}).get("results", []) if v.get("site") == "YouTube" and v.get("type") == "Trailer"), None),
                cast=[{"id": p.get("id"), "name": p.get("name"), "character": p.get("character"), "photo": f"https://image.tmdb.org/t/p/w200{p.get('profile_path')}" if p.get('profile_path') else None} for p in tmdb_data.get("credits", {}).get("cast", [])[:12]]
            )

            cache.set(cache_key, result)
            return result
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting series details: {e}")
            raise HTTPException(status_code=500, detail=str(e))

@router.get("/{slug}/temporada/{num}", response_model=Season)
async def get_serie_temporada(slug: str, num: int):
    """Busca episódios de uma temporada específica."""
    cache_key = f"serie_{slug}_temp_{num}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    url = f"{settings.PROVIDERS['ASSISTIR']}/serie/{slug}/temporada-{num}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    async with SafeAsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            if response.status_code != 200:
                raise HTTPException(status_code=404, detail="Temporada não encontrada")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            episodios = []
            accordion = soup.find('div', class_='accordion')
            if accordion:
                table = accordion.find('table', class_='accordion__list')
                if table:
                    tbody = table.find('tbody')
                    if tbody:
                        for row in tbody.find_all('tr'):
                            onclick = row.get('onclick', '')
                            match = re.search(r"reloadVideoSerie\((\d+),\s*'([^']+)'\)", onclick)
                            if match:
                                ep_num = int(match.group(1))
                                ep_hash = match.group(2)
                                ths = row.find_all('th')
                                ep_title = ths[-1].get_text().strip() if ths else f"Episódio {ep_num}"
                                episodios.append(Episode(numero=ep_num, titulo=ep_title, hash=ep_hash))
            
            episodios.sort(key=lambda x: x.numero)
            
            # Pega poster para o Season object
            poster_div = soup.find('div', class_='card__cover')
            poster = ""
            if poster_div:
                img = poster_div.find('img')
                if img:
                    poster = img.get('data-src') or img.get('src') or ""
                    if poster.startswith('//'): poster = 'https:' + poster

            result = Season(
                numero=num,
                titulo=f"Temporada {num}",
                poster=poster,
                link=f"/serie/{slug}/temporada-{num}",
                episodios=episodios
            )
            cache.set(cache_key, result)
            return result
        except:
            raise HTTPException(status_code=500, detail="Erro ao buscar episódios da temporada")

@router.get("/{slug}/temporada/{num}/episodio/{ep}", response_model=Episode)
async def get_serie_episodio(slug: str, num: int, ep: int):
    """Busca o player de um episódio específico."""
    temp_data = await get_serie_temporada(slug, num)
    
    target_ep = next((e for e in temp_data.episodios if e.numero == ep), None)
    if not target_ep:
        raise HTTPException(status_code=404, detail="Episódio não encontrado")
    
    iframe_url = f"{settings.PROVIDERS['ASSISTIR']}/iframe/{target_ep.hash}/{ep}"
    target_ep.player_url = iframe_url
    
    return target_ep
