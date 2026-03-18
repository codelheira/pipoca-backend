from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class Episode(BaseModel):
    numero: int
    titulo: str
    hash: Optional[str] = None
    player_url: Optional[str] = None

class Season(BaseModel):
    numero: int
    titulo: str
    poster: str
    link: str
    episodios: Optional[List[Episode]] = None

class SeriesBase(BaseModel):
    nome: str
    slug: str
    ano: str
    tipo: str = "serie"
    capa: Optional[str] = None
    nota: Optional[str] = None
    tag: Optional[str] = None

class SeriesDetail(BaseModel):
    title: str
    name: str
    slug: str
    synopsis: str
    year: str
    rating: float
    poster: str
    backdrop: Optional[str] = None
    genres: List[str]
    temporadas: List[Season]
    total_temporadas: int
    id_tmdb: Optional[int] = None
    status: Optional[str] = None
    trailer: Optional[str] = None
    cast: Optional[List[Dict[str, Any]]] = None
