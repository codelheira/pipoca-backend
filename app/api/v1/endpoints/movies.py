from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from bs4 import BeautifulSoup
import re
import asyncio
from ....services.scraping import get_item_html, extract_players, extract_recommendations, search_provider
from ....services.tmdb import search_tmdb, get_tmdb_details, extract_certification, enrich_item_list
from ....services.cache import cache
from ....models.movie import MovieDetail, MovieBase
from ....core.http_client import SafeAsyncClient, get_random_tmdb_key
from ....core.config import settings
import logging

router = APIRouter()
logger = logging.getLogger("pipoca-api")

@router.get("/info/{tipo}/{slug}", response_model=MovieDetail)
async def get_movie_info(tipo: str, slug: str):
    """
    Busca informações detalhadas de um filme ou série, com enriquecimento TMDB.
    """
    cache_key = f"info_{tipo}_{slug}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    html = await get_item_html(tipo, slug)
    if not html:
        raise HTTPException(status_code=404, detail="Item não encontrado no provedor.")

    soup = BeautifulSoup(html, 'html.parser')
    
    # Extração básica
    title_tag = soup.find('h1')
    title = title_tag.get_text().strip() if title_tag else ""
    name_only = re.sub(r'\(\d{4}\)', '', title).strip()
    
    # Detalhes técnicos e Ano
    info_list = soup.find('ul', class_='video-details')
    details = {}
    if info_list:
        for li in info_list.find_all('li'):
            text = li.get_text().strip()
            if ":" in text:
                k, v = text.split(":", 1)
                details[k.strip().lower()] = v.strip()

    year_match = re.search(r'(\d{4})', title)
    year = year_match.group(1) if year_match else details.get("ano", "")
    
    # TMDB Enrichment
    tmdb_data = {}
    search_results = await search_tmdb(name_only, "multi", year)
    
    if search_results:
        # Lógica de match (simplificada do original)
        best_match = search_results[0]
        for res in search_results:
            res_title = (res.get("title") or res.get("name") or "").lower()
            res_date = res.get("release_date") or res.get("first_air_date") or ""
            res_year = res_date.split("-")[0] if res_date else ""
            if res_title == name_only.lower() and res_year == year:
                best_match = res
                break
        
        # Busca detalhes completos
        media_type = best_match.get("media_type", "movie" if "filme" in tipo.lower() else "tv")
        tmdb_data = await get_tmdb_details(best_match["id"], media_type)
        tmdb_data["certification"] = extract_certification(tmdb_data, media_type)

    # Players e Recomendações
    players = extract_players(soup)
    recommendations = extract_recommendations(soup)
    
    # Enriquecimento de recomendações (paralelo)
    if recommendations:
        recommendations = await enrich_item_list(recommendations[:8])

    # Construção do objeto de resposta
    result = MovieDetail(
        title=title,
        name=name_only,
        synopsis=tmdb_data.get("overview", details.get("sinopse", "")),
        year=year or tmdb_data.get("release_date", "")[:4],
        tipo=tipo,
        slug=slug,
        poster=f"https://image.tmdb.org/t/p/w500{tmdb_data['poster_path']}" if tmdb_data.get("poster_path") else f"https://assistir.app/capas/{slug}.jpg",
        backdrop=f"https://image.tmdb.org/t/p/original{tmdb_data['backdrop_path']}" if tmdb_data.get("backdrop_path") else None,
        rating=round(tmdb_data.get("vote_average", 0.0), 1),
        genres=([g["name"] for g in tmdb_data.get("genres", [])] if "genres" in tmdb_data else details.get("gênero", "").split(",")),
        details=details,
        id_tmdb=tmdb_data.get("id"),
        recommendations=recommendations,
        players=players,
        trailer=next((f"https://www.youtube.com/embed/{v['key']}" for v in tmdb_data.get("videos", {}).get("results", []) if v.get("site") == "YouTube" and v.get("type") == "Trailer"), None),
        certification=tmdb_data.get("certification")
    )

    cache.set(cache_key, result)
    return result

@router.get("/all", response_model=dict)
async def get_all_movies(page: int = Query(1, ge=1)):
    """
    Lista todos os filmes com paginação e enriquecimento TMDB.
    """
    cache_key_full = "filmes_all_full_list"
    full_results = cache.get(cache_key_full)
    
    if not full_results:
        # Implementação do scraping multi-categoria (simplificada para o serviço)
        categorias = ["acao", "animacao", "aventura", "comedia", "crime", "drama", "terror", "ficcao-cientifica"]
        filmes_dict = {}
        
        async def fetch_cat(cat):
            url = f"{settings.PROVIDERS['ASSISTIR']}/categoria/{cat}"
            async with SafeAsyncClient() as client:
                try:
                    res = await client.get(url, timeout=20.0)
                    if res.status_code == 200:
                        soup = BeautifulSoup(res.text, 'html.parser')
                        for card in soup.find_all('div', class_='card'):
                            slug = card.get('id', '')
                            if not slug: continue
                            title_tag = card.find('h3', class_='card__title')
                            name = title_tag.get_text().strip() if title_tag else slug
                            filmes_dict[slug] = {"nome": name, "slug": slug, "tipo": "filme"}
                except: pass

        await asyncio.gather(*(fetch_cat(c) for c in categorias))
        full_results = list(filmes_dict.values())
        cache.set(cache_key_full, full_results, custom_expiration=3600) # 1h cache

    # Paginação
    per_page = 24
    start = (page - 1) * per_page
    end = start + per_page
    page_items = full_results[start:end]
    
    enriched_items = await enrich_item_list(page_items)
    
    return {
        "items": enriched_items,
        "page": page,
        "has_more": end < len(full_results),
        "total": len(full_results)
    }
