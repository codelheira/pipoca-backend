import asyncio
import re
from typing import List, Dict, Any, Optional
from ..core.http_client import SafeAsyncClient, get_random_tmdb_key
from ..core.config import settings
import logging

logger = logging.getLogger("pipoca-api")

async def search_tmdb(query: str, media_type: str = "multi", year: str = None) -> List[Dict[str, Any]]:
    """Busca genérica no TMDB."""
    async with SafeAsyncClient() as client:
        params = {
            "api_key": get_random_tmdb_key(),
            "query": query,
            "language": "pt-BR",
            "include_adult": "false"
        }
        
        if year and year.isdigit():
            if media_type == "movie":
                params["year"] = year
            elif media_type == "tv":
                params["first_air_date_year"] = year

        endpoint = f"search/{media_type}"
        url = f"https://api.themoviedb.org/3/{endpoint}"
        
        try:
            res = await client.get(url, params=params, timeout=5.0)
            if res.status_code == 200:
                return res.json().get("results", [])
        except Exception as e:
            logger.error(f"Error searching TMDB: {e}")
        
    return []

async def get_tmdb_details(tmdb_id: int, media_type: str = "movie") -> Dict[str, Any]:
    """Busca detalhes completos de um item no TMDB."""
    async with SafeAsyncClient() as client:
        url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}"
        params = {
            "api_key": get_random_tmdb_key(),
            "language": "pt-BR",
            "append_to_response": "videos,release_dates,content_ratings,credits"
        }
        
        try:
            res = await client.get(url, params=params, timeout=5.0)
            if res.status_code == 200:
                return res.json()
        except Exception as e:
            logger.error(f"Error getting TMDB details: {e}")
            
    return {}

def extract_certification(details: Dict[str, Any], media_type: str) -> str:
    """Extrai a classificação indicativa brasileira."""
    certification = ""
    try:
        if media_type == "movie":
            releases = details.get("release_dates", {}).get("results", [])
            for rel in releases:
                if rel.get("iso_3166_1") == "BR":
                    for date in rel.get("release_dates", []):
                        if date.get("certification"):
                            certification = date.get("certification")
                            break
                    if certification: break
        else: # tv
            ratings = details.get("content_ratings", {}).get("results", [])
            for rate in ratings:
                if rate.get("iso_3166_1") == "BR":
                    certification = rate.get("rating")
                    break
    except Exception as e:
        logger.error(f"Error extracting certification: {e}")
    return certification

async def enrich_item_list(items: List[Dict[str, Any]], media_type: str = "multi") -> List[Dict[str, Any]]:
    """Enriquece uma lista de itens (geralmente resultados de scraping) com dados TMDB em paralelo."""
    async def _enrich(item):
        name = item.get("nome") or item.get("name")
        year = item.get("ano")
        
        # Tenta buscar no TMDB
        results = await search_tmdb(name, media_type, year)
        
        if not results and year: # Tenta sem o ano se não achar nada
            results = await search_tmdb(name, media_type)
            
        if results:
            best_match = results[0] # Simplificação: pega o primeiro ou implementa lógica de match
            
            if best_match.get("poster_path"):
                item["capa"] = f"https://image.tmdb.org/t/p/w500{best_match['poster_path']}"
            
            if best_match.get("vote_average"):
                item["nota"] = str(round(best_match["vote_average"], 1))
                
            # Adiciona gêneros se disponíveis
            if best_match.get("genre_ids"):
                genres = [settings.GENRE_MAP.get(gid) for gid in best_match["genre_ids"] if settings.GENRE_MAP.get(gid)]
                item["generos"] = genres

        if "capa" not in item:
            item["capa"] = item.get("capa_original", f"https://assistir.app/capas/{item.get('slug')}.jpg")
            
        return item

    tasks = [_enrich(item) for item in items]
    return await asyncio.gather(*tasks)
