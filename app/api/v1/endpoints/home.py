from fastapi import APIRouter
from ....services.tmdb import enrich_item_list
from ....services.cache import cache
from ....core.http_client import SafeAsyncClient
from ....core.config import settings
from bs4 import BeautifulSoup
import asyncio
import logging

router = APIRouter()
logger = logging.getLogger("pipoca-api")

async def scrape_featured_from_home():
    """Scrapes the most relevant items from some categories to simulate a home feed."""
    categories = ["acao", "animacao", "scifi", "drama"]
    pool = {}
    
    async def fetch_cat(cat):
        url = f"{settings.PROVIDERS['ASSISTIR']}/categoria/{cat}"
        async with SafeAsyncClient() as client:
            try:
                res = await client.get(url, timeout=10.0)
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, 'html.parser')
                    for card in soup.find_all('div', class_='card')[:6]:
                        slug = card.get('id', '')
                        if not slug: continue
                        title_tag = card.find('h3', class_='card__title')
                        name = title_tag.get_text().strip() if title_tag else slug
                        pool[slug] = {"nome": name, "slug": slug, "tipo": "filme"}
            except: pass

    await asyncio.gather(*(fetch_cat(c) for c in categories))
    return list(pool.values())

async def scrape_series_for_home():
    categories = ["series-legendadas", "series-dubladas"]
    pool = {}
    
    async def fetch_cat(cat):
        url = f"{settings.PROVIDERS['ASSISTIR']}/categoria/{cat}"
        async with SafeAsyncClient() as client:
            try:
                res = await client.get(url, timeout=10.0)
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, 'html.parser')
                    for card in soup.find_all('div', class_='card')[:6]:
                        slug = card.get('id', '')
                        if not slug: continue
                        title_tag = card.find('h3', class_='card__title')
                        name = title_tag.get_text().strip() if title_tag else slug
                        pool[slug] = {"nome": name, "slug": slug, "tipo": "serie"}
            except: pass

    await asyncio.gather(*(fetch_cat(c) for c in categories))
    return list(pool.values())

@router.get("")
async def get_home():
    """Retorna o conteúdo da Home Page com Destaques, Mais Assistidos e Lançamentos."""
    cached = cache.get("home_v1")
    if cached:
        return cached

    # Getting pools
    movies_pool = await scrape_featured_from_home()
    series_pool = await scrape_series_for_home()
    
    # Enrich pools
    enriched_movies = await enrich_item_list(movies_pool)
    enriched_series = await enrich_item_list(series_pool)
    
    # Construct sections
    data = {
        "featured": enriched_movies[:5],  # Top 5 as slides
        "most_watched": enriched_movies[5:15],
        "recently_added": enriched_movies[15:25],
        "releases_2026": enriched_movies[:10], # Latest releases
        "series": enriched_series[:10]
    }
    
    cache.set("home_v1", data, custom_expiration=3600) # 1h cache
    return data
