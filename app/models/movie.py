from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class MovieBase(BaseModel):
    name: str
    slug: str
    year: str
    tipo: str = "filme"
    capa: Optional[str] = None
    nota: Optional[str] = None
    tag: Optional[str] = None

class MovieDetail(BaseModel):
    title: str
    name: str
    synopsis: str
    year: str
    tipo: str
    slug: str
    poster: str
    backdrop: Optional[str] = None
    rating: float
    genres: List[str]
    details: Dict[str, str]
    id_tmdb: Optional[int] = None
    recommendations: List[Dict[str, Any]]
    players: List[Dict[str, str]]
    trailer: Optional[str] = None
    certification: Optional[str] = None

class SearchResult(BaseModel):
    items: List[MovieBase]
