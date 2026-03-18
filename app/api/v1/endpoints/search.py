from fastapi import APIRouter
from typing import List
from ....services.scraping import search_provider
from ....services.tmdb import enrich_item_list
from ....services.cache import cache
from ....models.movie import MovieBase
import logging

router = APIRouter()
logger = logging.getLogger("pipoca-api")

@router.get("/{query}", response_model=List[MovieBase])
async def search_media(query: str):
    """
    Endpoint de busca que integra Scraping, TMDB e Cache.
    """
    query_clean = query.lower().strip()
    
    if len(query_clean) < 3:
        return []

    # 1. Verifica o Cache
    cache_key = f"search_{query_clean}"
    cached_data = cache.get(cache_key)
    if cached_data:
        logger.info(f"Cache Hit for query: {query_clean}")
        return cached_data

    # 2. Busca no Provedor Original (Scraping)
    results = await search_provider(query_clean)
    if not results:
        return []

    # 3. Enriquecimento com TMDB (Metadados e Imagens de Alta Qualidade)
    enriched_results = await enrich_item_list(results[:10])
    
    # 4. Normalização para o modelo MovieBase
    output = []
    for item in enriched_results:
        output.append(MovieBase(
            name=item.get("nome", ""),
            slug=item.get("slug", ""),
            year=str(item.get("ano", "")),
            tipo=item.get("tipo", "filme"),
            capa=item.get("capa"),
            nota=item.get("nota"),
            tag=item.get("tag")
        ))

    # 5. Salva no Cache
    cache.set(cache_key, output)
    
    return output
