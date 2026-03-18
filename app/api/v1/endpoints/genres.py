from fastapi import APIRouter, Query, HTTPException
from ....services.tmdb import enrich_item_list
from ....services.cache import cache
from ....core.http_client import SafeAsyncClient
from ....core.config import settings
from bs4 import BeautifulSoup
import logging

router = APIRouter()
logger = logging.getLogger("pipoca-api")

@router.get("/{categoria}")
async def get_categoria(categoria: str, page: int = Query(1, ge=1)):
    """Lista filmes/séries de uma categoria específica com enriquecimento TMDB."""
    cache_key = f"cat_{categoria}_{page}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    url = f"{settings.PROVIDERS['ASSISTIR']}/categoria/{categoria}"
    if page > 1:
        url += f"/{page}"
    
    items = []
    async with SafeAsyncClient() as client:
        try:
            res = await client.get(url, timeout=15.0)
            if res.status_code != 200:
                raise HTTPException(status_code=404, detail="Categoria não encontrada")
            
            soup = BeautifulSoup(res.text, 'html.parser')
            for card in soup.find_all('div', class_='card'):
                slug = card.get('id', '')
                if not slug: continue
                title_tag = card.find('h3', class_='card__title')
                name = title_tag.get_text().strip() if title_tag else slug
                # Decide tipo com base na categoria
                tipo = "serie" if "serie" in categoria or "series" in categoria else "filme"
                items.append({"nome": name, "slug": slug, "tipo": tipo})
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error scraping category {categoria}: {e}")
            return {"items": [], "page": page, "has_more": False}

    enriched_items = await enrich_item_list(items)
    
    result = {
        "items": enriched_items,
        "page": page,
        "has_more": len(items) >= 20, # Estimativa simples
        "categoria": categoria
    }
    
    cache.set(cache_key, result)
    return result
