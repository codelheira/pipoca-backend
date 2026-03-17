from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
import socketio

from fastapi.middleware.cors import CORSMiddleware
import httpx
import time
import random
import socket
import asyncio
import re
from nanodlna import devices, dlna
import logging
import json
import os
import uuid
from auth import verify_google_token, create_access_token, get_current_user, GOOGLE_CLIENT_ID
from fastapi import Depends
import logging

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pipoca-api")

# Helper para resolver DNS se o sistema falhar (problema comum em alguns provedores)
_dns_cache = {}
_original_getaddrinfo = socket.getaddrinfo

def resolve_host_safely(host):
    now = time.time()
    if host in _dns_cache:
        ts, ip = _dns_cache[host]
        if now - ts < 600: # 10 min cache
            return ip
            
    try:
        ip = socket.gethostbyname(host)
        _dns_cache[host] = (now, ip)
        return ip
    except:
        try:
            import subprocess
            cmd = f'powershell "Resolve-DnsName {host} -Server 8.8.8.8 -Type A | Select-Object -ExpandProperty IPAddress"'
            res = subprocess.check_output(cmd, shell=True).decode().strip().split('\n')[0].strip()
            if res and re.match(r"^\d{1,3}(\.\d{1,3}){3}$", res):
                 print(f"DNS Fallback: {host} -> {res}")
                 _dns_cache[host] = (now, res)
                 return res
        except:
            pass
    return host

def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    h = host.decode() if isinstance(host, bytes) else host
    if h in ["assistir.app", "www.assistir.app"]:
        resolved_ip = resolve_host_safely(h)
        if resolved_ip != h:
            return _original_getaddrinfo(resolved_ip, port, family, type, proto, flags)
    return _original_getaddrinfo(host, port, family, type, proto, flags)

# Aplica patch global no socket para contornar bloqueios de DNS do provedor
socket.getaddrinfo = patched_getaddrinfo

class SafeAsyncClient(httpx.AsyncClient):
    """Client que usa configurações otimizadas para evitar erros de SSL e DNS"""
    def __init__(self, *args, **kwargs):
        # Usamos verificador de SSL padrão, mas com tolerância a versões de TLS
        if "verify" not in kwargs:
            kwargs["verify"] = False # Mantemos False para o assistir.app que pode ter certs váriaveis em proxies
        
        # Headers padrão para parecer um navegador real e evitar bloqueios de handshake
        if "headers" not in kwargs:
            kwargs["headers"] = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            }
        
        # Aumentamos o limite de conexões e timeout
        if "timeout" not in kwargs:
            kwargs["timeout"] = httpx.Timeout(20.0, connect=10.0)
            
        super().__init__(*args, **kwargs)

    async def request(self, method, url, **kwargs):
        # Agora o DNS é resolvido pelo patch global do socket.
        # Mantemos o hostname na URL para que o SNI (SSL) funcione corretamente.
        return await super().request(method, url, **kwargs)

app = FastAPI(title="Pipoca Filmes API")

# Setup Socket.io
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')



# Cache simples em memória: { "query": (timestamp, data) }
search_cache = {}
CACHE_EXPIRATION = 24 * 60 * 60  # 24 horas em segundos

# Lista de chaves TMDB para rodízio
# Mapeamento de Gêneros TMDB (PT-BR)
GENRE_MAP = {
    28: "Ação", 12: "Aventura", 16: "Animação", 35: "Comédia", 80: "Crime", 
    99: "Documentário", 18: "Drama", 10751: "Família", 14: "Fantasia", 
    36: "História", 27: "Terror", 10402: "Música", 9648: "Mistério", 
    10749: "Romance", 878: "Ficção", 10770: "Cinema TV", 
    53: "Suspense", 10752: "Guerra", 37: "Faroeste",
    10759: "Ação e Aventura", 10762: "Kids", 10763: "News", 
    10764: "Reality", 10765: "Sci-Fi & Fantasy", 10766: "Soap", 
    10767: "Talk", 10768: "War & Politics"
}

TMDB_KEYS = [
    'fb7bb23f03b6994dafc674c074d01761', 'e55425032d3d0f371fc776f302e7c09b',
    '8301a21598f8b45668d5711a814f01f6', '8cf43ad9c085135b9479ad5cf6bbcbda',
    'da63548086e399ffc910fbc08526df05', '13e53ff644a8bd4ba37b3e1044ad24f3',
    '269890f657dddf4635473cf4cf456576', 'a2f888b27315e62e471b2d587048f32e',
    '8476a7ab80ad76f0936744df0430e67c', '5622cafbfe8f8cfe358a29c53e19bba0',
    'ae4bd1b6fce2a5648671bfc171d15ba4', '257654f35e3dff105574f97fb4b97035',
    '2f4038e83265214a0dcd6ec2eb3276f5', '9e43f45f94705cc8e1d5a0400d19a7b7',
    'af6887753365e14160254ac7f4345dd2', '06f10fc8741a672af455421c239a1ffc',
    '09ad8ace66eec34302943272db0e8d2c'
]

def get_random_tmdb_key():
    """Retorna uma chave aleatória da lista TMDB."""
    return random.choice(TMDB_KEYS)

# Configuração de local IP para DLNA
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

LOCAL_IP = get_local_ip()

# Configuração de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Debug middleware para ver o que chega no servidor (inclusive WebSockets)
@app.middleware("http")
async def log_http(request: Request, call_next):
    logger.info(f"HTTP REQ: {request.method} {request.url.path}")
    return await call_next(request)

@app.websocket("/ws")
async def test_websocket(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_text("WS Alive")
    await websocket.close()

@app.get("/api/search/{query}")
async def search_proxy(query: str):
    """
    Proxy para a API de busca do assistir.app com Cache de 24h e Rodízio de chaves TMDB.
    Suporta multidioma (PT-BR) nativamente via TMDB.
    """
    query_clean = query.lower().strip()
    
    # 0. Verifica o Cache
    current_time = time.time()
    if query_clean in search_cache:
        timestamp, cached_data = search_cache[query_clean]
        if current_time - timestamp < CACHE_EXPIRATION:
            print(f"Cache Hit: {query_clean}")
            return cached_data
    
    if len(query_clean) < 3:
        return []
    
    # URL da API externa assistir.app
    url = f"https://assistir.app/autosearch/{query_clean}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://assistir.app/",
        "Origin": "https://assistir.app",
        "x-requested-with": "XMLHttpRequest"
    }
    
    async with SafeAsyncClient(follow_redirects=True) as client:
        try:
            # 1. Busca no assistir.app
            try:
                response = await client.get(url, headers=headers, timeout=10.0)
                if response.status_code != 200:
                    return []
                results = response.json()
            except Exception as e:
                print(f"Erro ao consultar assistir.app: {e}")
                return []

            print(f"Busca (Cache Miss): {query_clean} -> {len(results)} itens found.")
            
            enriched_results = []
            
            # 2. Enriquecimento com Posters usando Rodízio de Chaves TMDB
            for item in results[:10]:
                title = item.get("nome", "")
                slug = item.get("slug", "")
                year = item.get("ano", "")
                item["ano"] = "" # Força usar apenas dados do TMDB se encontrado
                
                # Fallback inicial usando a capa do próprio assistir.app
                image_url = f"https://assistir.app/capas/{slug}.jpg"
                
                try:
                    current_key = get_random_tmdb_key()
                    
                    # Usa o endpoint específico se soubermos o tipo
                    endpoint = "movie" if item.get("tipo") == "filme" else "tv"
                    tmdb_url = f"https://api.themoviedb.org/3/search/{endpoint}"
                    
                    tmdb_params = {
                        "api_key": current_key,
                        "query": title,
                        "language": "pt-BR"
                    }
                    
                    # Tenta com o ano se disponível, mas se não encontrar nada, tentaremos sem
                    if year and year.isdigit():
                        if endpoint == "movie":
                            tmdb_params["year"] = year
                        else:
                            tmdb_params["first_air_date_year"] = year

                    tmdb_res = await client.get(tmdb_url, params=tmdb_params, timeout=2.0)
                    
                    # Se não encontrou nada com o filtro de ano, tenta sem o filtro (caso o ano do scraper esteja errado)
                    if tmdb_res.status_code != 200 or not tmdb_res.json().get("results"):
                        if "year" in tmdb_params: del tmdb_params["year"]
                        if "first_air_date_year" in tmdb_params: del tmdb_params["first_air_date_year"]
                        tmdb_res = await client.get(tmdb_url, params=tmdb_params, timeout=2.0)
                    
                    if tmdb_res.status_code == 200:
                        tmdb_json = tmdb_res.json()
                        tmdb_results = tmdb_json.get("results", [])
                        
                        if tmdb_results:
                            best_match = None
                            title_matches = []
                            
                            # Limpa o título buscado de anos (ex: Matrix (1999) -> Matrix)
                            clean_search_title = re.sub(r'\(\d{4}\)', '', title).strip().lower()
                            
                            for res in tmdb_results:
                                # Extração de dados
                                res_title = (res.get("title") or res.get("name") or "").lower()
                                res_orig_title = (res.get("original_title") or res.get("original_name") or "").lower()
                                res_date = res.get("release_date") or res.get("first_air_date") or ""
                                res_year = res_date.split("-")[0] if res_date else ""
                                
                                # Verificações mais flexíveis
                                # Match se o título for idêntico OU se um contiver o outro (ajuda no caso de "The Matrix" vs "Matrix")
                                is_title_match = (res_title == clean_search_title) or (res_orig_title == clean_search_title) or \
                                               (clean_search_title in res_title) or (res_title in clean_search_title)
                                
                                is_year_match = (year and str(year) == res_year)
                                
                                # 1. Match Perfeito (Título + Ano)
                                if is_title_match and is_year_match:
                                    best_match = res
                                    break
                                
                                # 2. Lista de candidatos por título
                                if is_title_match:
                                    title_matches.append(res)
                            
                            # Seleção do Melhor Candidato
                            target_data = best_match
                            if not target_data and title_matches:
                                # Desempate por popularidade
                                title_matches.sort(key=lambda x: x.get("popularity", 0), reverse=True)
                                target_data = title_matches[0]
                            
                            # Fallback: Primeiro resultado se nada der certo (geralmente o mais relevante da busca multi)
                            if not target_data:
                                target_data = tmdb_results[0]
                            
                            # Atribui a imagem e o ano se encontrou
                            if target_data:
                                if target_data.get("poster_path"):
                                    image_url = f"https://image.tmdb.org/t/p/w300{target_data['poster_path']}"
                                
                                # Atualiza o ano com o do TMDB (geralmente mais preciso)
                                res_date = target_data.get("release_date") or target_data.get("first_air_date") or ""
                                if res_date:
                                    item["ano"] = res_date.split("-")[0]
                                if target_data.get("genre_ids"):
                                    item["genero"] = ", ".join([GENRE_MAP.get(gid, "") for gid in target_data["genre_ids"] if GENRE_MAP.get(gid)])
                    else:
                        print(f"Aviso TMDB ({tmdb_res.status_code}) para {title}")
                        
                except Exception as net_err:
                    print(f"Erro na conexão TMDB: {net_err}")
                
                item["capa"] = image_url
                enriched_results.append(item)
            
            # 3. Salva no Cache
            search_cache[query_clean] = (current_time, enriched_results)
            return enriched_results
            
        except Exception as e:
            print(f"ERRO CRÍTICO: {str(e)}")
            return []

@app.get("/api/network-ip")
async def get_network_ip():
    return {"ip": LOCAL_IP}

@app.get("/")
async def root():
    return {
        "message": "Pipoca Filmes API running with TMDB Rotation!",
        "google_client_id": GOOGLE_CLIENT_ID
    }

# --- AUTH SYSTEM ---
USERS_FILE = "users.json"

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=4, ensure_ascii=False)

@app.post("/api/auth/google")
async def google_auth(request: Request):
    try:
        data = await request.json()
        token = data.get("token")
        if not token:
            raise HTTPException(status_code=400, detail="Token missing")
        
        user_info = verify_google_token(token)
        if not user_info:
            raise HTTPException(status_code=401, detail="Invalid Google token")
        
        users = load_users()
        google_id = user_info["sub"]
        
        if google_id not in users:
            users[google_id] = {
                "id": google_id,
                "email": user_info["email"],
                "name": user_info["name"],
                "picture": user_info["picture"],
                "created_at": time.time(),
                "favorites": [],
                "history": []
            }
            save_users(users)
        else:
            # Atualiza info se mudou
            users[google_id]["name"] = user_info["name"]
            users[google_id]["picture"] = user_info["picture"]
            save_users(users)
        
        access_token = create_access_token(data={"sub": google_id, "email": user_info["email"]})
        return {
            "access_token": access_token, 
            "token_type": "bearer", 
            "user": users[google_id]
        }
    except Exception as e:
        print(f"Erro no google_auth: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    users = load_users()
    google_id = current_user.get("sub")
    if google_id in users:
        return users[google_id]
    raise HTTPException(status_code=404, detail="User not found")
# -------------------

@app.get("/api/info/{tipo}/{slug}")
async def get_info(tipo: str, slug: str):
    """
    Busca informações detalhadas de um filme ou série.
    """
    from bs4 import BeautifulSoup
    import re
    
    print(f"Request Info: tipo={tipo}, slug={slug}")
    
    # Mapeamento do tipo para o padrão do assistir.app
    tipo_lower = tipo.lower()
    if any(keyword in tipo_lower for keyword in ["filme", "movie"]):
        path_tipo = "filme"
    else:
        path_tipo = "serie"
        
    url = f"https://assistir.app/{path_tipo}/{slug}"
    
    print(f"Fetching Provider URL: {url}")
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"}
    
    async with SafeAsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(url, headers=headers, timeout=10.0)
            if response.status_code != 200:
                print(f"Provider returned {response.status_code} for {url}")
                raise HTTPException(status_code=404, detail=f"Item não encontrado no provedor: {url} (Status: {response.status_code})")
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extração básica
            title_tag = soup.find('h1')
            title = title_tag.get_text().strip() if title_tag else ""
            
            # Limpa o ano do título se houver (ex: "Deadpool (2024)")
            name_only = re.sub(r'\(\d{4}\)', '', title).strip()
            
            # Sinopse (geralmente em uma div com classe específica ou após algum cabeçalho)
            # No assistir.app a sinopse costuma estar em uma div 'video-synopsis' ou similar
            synopsis_div = soup.find('div', class_='video-synopsis') or soup.find('div', class_='description')
            synopsis = synopsis_div.get_text().strip() if synopsis_div else ""
            
            # Detalhes técnicos
            info_list = soup.find('ul', class_='video-details')
            details = {}
            if info_list:
                for li in info_list.find_all('li'):
                    text = li.get_text().strip()
                    if ":" in text:
                        k, v = text.split(":", 1)
                        details[k.strip().lower()] = v.strip()

            # Ano
            year_match = re.search(r'(\d{4})', title)
            year = year_match.group(1) if year_match else details.get("ano", "")
            
            # TMDB Enrichment
            current_key = get_random_tmdb_key()
            tmdb_params = {
                "api_key": current_key,
                "query": name_only,
                "language": "pt-BR"
            }
            if year: tmdb_params["year"] = year
            
            print(f"DEBUG: Buscando TMDB -> Query: '{name_only}' | Ano: '{year}'")

            tmdb_data = {}
            try:
                tmdb_res = await client.get("https://api.themoviedb.org/3/search/multi", params=tmdb_params, timeout=3.0)
                if tmdb_res.status_code == 200:
                    results = tmdb_res.json().get("results", [])
                    print(f"DEBUG: TMDB retornou {len(results)} resultados.")
                    
                    if results:
                        # Candidatos que deram match de título
                        title_matches = []
                        
                        for i, res in enumerate(results):
                            # Extrai dados do resultado
                            res_title = res.get("title") or res.get("name") or ""
                            res_orig_title = res.get("original_title") or res.get("original_name") or ""
                            res_date = res.get("release_date") or res.get("first_air_date") or ""
                            res_year = res_date.split("-")[0] if res_date else ""
                            res_pop = res.get("popularity", 0)
                            
                            print(f"DEBUG: Candidato {i+1}: '{res_title}' ({res_year}) Pop: {res_pop}")

                            # Verifica Título (Case Insensitive)
                            is_title_match = (res_title.lower() == name_only.lower()) or (res_orig_title.lower() == name_only.lower())
                            is_year_match = (year and res_year == year)
                            
                            if is_title_match:
                                if is_year_match:
                                    # Match Perfeito (Título + Ano) -> Prioridade Máxima
                                    tmdb_data = res
                                    print("DEBUG: MATCH PERFEITO (Ano + Título)!")
                                    break
                                title_matches.append(res)
                        
                        # Se não achou match perfeito, mas tem matches de título
                        if not tmdb_data and title_matches:
                            # Ordena por popularidade (descendente) para pegar o mais famoso (ex: Matrix 1999 vs 1993)
                            title_matches.sort(key=lambda x: x.get("popularity", 0), reverse=True)
                            tmdb_data = title_matches[0]
                            print(f"DEBUG: Usando match de título mais popular: {tmdb_data.get('title')}")
                        
                        if not tmdb_data:
                             print("DEBUG: Nenhum match de título. Usando o primeiro da lista.")
                             tmdb_data = results[0]
                        
                        # Atualiza o ano com o do TMDB se encontramos um match confiável
                        if tmdb_data:
                            res_date = tmdb_data.get("release_date") or tmdb_data.get("first_air_date") or ""
                            if res_date:
                                year = res_date.split("-")[0]
            except: pass

            # 2.5 BUSCA DETALHES COMPLETOS SE TIVERMOS UM ID (Para pegar Gêneros, etc)
            if tmdb_data and tmdb_data.get("id"):
                try:
                    media_type = tmdb_data.get("media_type")
                    if not media_type:
                        media_type = "movie" if "filme" in tipo.lower() else "tv"
                    
                    print(f"DEBUG: Buscando detalhes completos TMDB para {media_type}/{tmdb_data['id']}...")
                    details_url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_data['id']}"
                    details_params = {
                        "api_key": current_key, 
                        "language": "pt-BR",
                        "append_to_response": "videos,release_dates,content_ratings,credits"
                    }
                    
                    details_res = await client.get(details_url, params=details_params, timeout=3.0)
                    if details_res.status_code == 200:
                        full_data = details_res.json()
                        tmdb_data.update(full_data)
                        
                        # Extrai Classificação Indicativa (BR)
                        certification = ""
                        try:
                            # Para Filmes
                            if media_type == "movie":
                                releases = full_data.get("release_dates", {}).get("results", [])
                                for rel in releases:
                                    if rel.get("iso_3166_1") == "BR":
                                        # Pega a primeira certificação não vazia
                                        for date in rel.get("release_dates", []):
                                            if date.get("certification"):
                                                certification = date.get("certification")
                                                break
                                        if certification: break
                            # Para Séries
                            else:
                                ratings = full_data.get("content_ratings", {}).get("results", [])
                                for rate in ratings:
                                    if rate.get("iso_3166_1") == "BR":
                                        certification = rate.get("rating")
                                        break
                            
                            if certification:
                                tmdb_data["certification"] = certification
                                print(f"DEBUG: Classificação encontrada: {certification}")
                        except Exception as e:
                            print(f"Erro ao extrair certificação: {e}")
                            
                        print("DEBUG: Detalhes completos carregados com sucesso!")
                except Exception as e:
                    print(f"Erro no enrich full details: {e}")
            
            # Extração dos players (iframes) com busca de labels reais
            players = []
            
            # Tenta encontrar a lista de players no HTML para pegar os nomes reais
            # No assistir.app, os players costumam estar em botões com IDs bt1, bt2... que mostram iframes player-1, player-2...
            player_buttons = soup.find_all('button', id=re.compile(r'bt\d+'))
            
            for btn in player_buttons:
                label = btn.get_text().strip()
                # O ID do botão bt1 costuma abrir o div player-1
                target_id = btn.get('id', '').replace('bt', 'player-')
                target_div = soup.find('div', id=target_id)
                if target_div:
                    iframe = target_div.find('iframe')
                    if iframe and iframe.get('src'):
                        src = iframe['src']
                        if src.startswith('//'): src = f"https:{src}"
                        players.append({"label": label, "url": src})

            # Fallback: Se não achou jogadores pelos botões (ex: Layout antigo ou diferente)
            if not players:
                found_iframes = soup.find_all('iframe')
                for i, iframe in enumerate(found_iframes):
                    src = iframe.get('src', '')
                    if '/iframe/' in src or 'player' in src.lower():
                        if src.startswith('//'): src = f"https:{src}"
                        
                        label = f"Player {i+1}"
                        # Se o src contiver um número (ex: player=2), usamos ele como label principal
                        num_match = re.search(r'player[=\/](\d+)', src.lower())
                        if num_match:
                            label = f"Player {num_match.group(1)}"

                        players.append({"label": label, "url": src})

            # Se ainda assim não achou nada, mas tem iframes com /iframe/, usa a busca original como fallback
            if not players:
                for iframe in found_iframes:
                    src = iframe.get('src', '')
                    if '/iframe/' in src:
                        if src.startswith('//'): src = f"https:{src}"
                        players.append({"label": f"Player {len(players)+1}", "url": src})

            # Ordena os players para colocar HLS em primeiro (geralmente mais estável)
            def player_sort_key(p):
                label = p['label'].lower()
                url = p['url'].lower()
                if 'hls' in url or 'hls' in label:
                    return 0
                if 'player 1' in label:
                    return 1
                if 'player 2' in label:
                    return 2
                return 10

            players.sort(key=player_sort_key)


            # Tenta pegar a sinopse também de meta tags se falhar no div
            if not synopsis:
                meta_desc = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', attrs={'property': 'og:description'})
                if meta_desc: synopsis = meta_desc.get('content', '').strip()

            # Prioriza a sinopse do TMDB pois geralmente é mais limpa.
            # Se não tiver no TMDB, usa a do site (fallback).
            final_synopsis = tmdb_data.get("overview")
            if not final_synopsis:
                final_synopsis = synopsis

            # Formatação da Duração (TMDB)
            runtime = tmdb_data.get("runtime") or (tmdb_data.get("episode_run_time", [0])[0] if tmdb_data.get("episode_run_time") else 0)
            
            if runtime:
                try:
                    runtime = int(runtime)
                    hours = runtime // 60
                    minutes = runtime % 60
                    if hours > 0:
                        details["duração"] = f"{hours}h {minutes}m"
                    else:
                        details["duração"] = f"{minutes}m"
                except: pass

            # Recomendações (Talvez você goste!)
            recommendations = []
            try:
                # Encontra a seção "Talvez você goste!"
                rec_header = None
                for h2 in soup.find_all('h2', class_='section__title'):
                    if "Talvez você goste" in h2.get_text():
                        rec_header = h2
                        break
                
                if rec_header:
                    # O header está em uma col dentro de uma row. 
                    # Os cards estão nas colunas irmãs dentro dessa mesma row.
                    # h2 -> div(col) -> div(row)
                    row = rec_header.find_parent('div', class_='row')
                    if row:
                        cards = row.find_all('div', class_='card')
                        for card in cards:
                            try:
                                # Link (geralmente na capa ou botão play)
                                link_tag = card.find('a', class_='card__play') or card.find('a')
                                if not link_tag: continue
                                rec_path = link_tag['href']
                                
                                # Título (pode estar direto no h3 ou dentro de um a)
                                title_tag = card.find('h3', class_='card__title')
                                if title_tag:
                                    rec_name = title_tag.get_text().strip()
                                else:
                                    # Tenta pegar do link se não achar h3
                                    rec_name = link_tag.get_text().strip() or "Sem Título"
                                
                                # Poster
                                cover_div = card.find('div', class_='card__cover')
                                rec_img = ""
                                if cover_div:
                                    img_tag = cover_div.find('img')
                                    if img_tag:
                                        rec_img = img_tag.get('src') or img_tag.get('data-src') or ""
                                    
                                    # Fallback para picture/source se img falhar ou for placeholder
                                    if not rec_img or "data:" in rec_img:
                                        source_tag = cover_div.find('source')
                                        if source_tag:
                                            scrset = source_tag.get('srcset') or source_tag.get('data-srcset')
                                            if scrset:
                                                rec_img = scrset.split(',')[0].split(' ')[0] # Pega a primeira URL
                                
                                # Ajusta URL da imagem
                                if rec_img and rec_img.startswith('//'): rec_img = "https:" + rec_img
                                
                                # Slug e Tipo
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
                print(f"Erro ao extrair recomendações: {e}")
            
            # Enriquecimento das Recomendações com TMDB (Paralelo)
            # Substitui as imagens raspadas por imagens de alta qualidade do TMDB
            if recommendations:
                async def enrich_rec(rec):
                    try:
                        rec_key = get_random_tmdb_key()
                        rec_params = {
                            "api_key": rec_key,
                            "query": rec["name"],
                            "language": "pt-BR",
                            "include_adult": "false"
                        }
                        
                        # Tenta buscar no TMDB
                        tmdb_rec_res = await client.get("https://api.themoviedb.org/3/search/multi", params=rec_params, timeout=2.0)
                        
                        best_rec = None
                        if tmdb_rec_res.status_code == 200:
                            rec_results = tmdb_rec_res.json().get("results", [])
                            if rec_results:
                                # 1. Match Perfeito de Título (Ordenado por Popularidade)
                                title_matches = [r for r in rec_results if (r.get("title") or r.get("name") or "").lower() == rec["name"].lower()]
                                if title_matches:
                                    # Prioriza os que tem poster_path e melhor popularidade
                                    title_matches.sort(key=lambda x: (x.get("poster_path") is not None, x.get("popularity", 0)), reverse=True)
                                    best_rec = title_matches[0]
                                
                                # 2. Match Parcial
                                if not best_rec:
                                    for r in rec_results:
                                        r_title = (r.get("title") or r.get("name") or "").lower()
                                        if rec["name"].lower() in r_title or r_title in rec["name"].lower():
                                            best_rec = r
                                            break

                                # 3. Fallback: Pega o primeiro resultado
                                if not best_rec:
                                    best_rec = rec_results[0]

                                if best_rec:
                                    if best_rec.get("poster_path"):
                                        rec["poster"] = f"https://image.tmdb.org/t/p/w300{best_rec['poster_path']}"
                                    
                                    # Adiciona Ano e Nota se não tiver
                                    date_str = best_rec.get("release_date") or best_rec.get("first_air_date") or ""
                                    if not rec.get("ano"):
                                        rec["ano"] = date_str.split("-")[0] if date_str else ""
                                    rec["nota"] = round(best_rec.get("vote_average", 0), 1)

                        # Fallback de Imagem: Se não conseguimos poster do TMDB ou o poster atual é suspeito/vazio
                        curr_poster = rec.get("poster", "")
                        if not curr_poster or "placeholder" in curr_poster.lower() or "data:" in curr_poster:
                             rec["poster"] = f"https://assistir.app/capas/{rec['slug']}.jpg"
                             
                    except Exception as e:
                        print(f"Erro no enrich_rec: {e}")
                    return rec

                # Processa apenas as primeiras 8 para não sobrecarregar
                tasks = [enrich_rec(rec) for rec in recommendations[:8]]
                recommendations = await asyncio.gather(*tasks)

            print(f"DEBUG: Returning info for {title} with id_tmdb: {tmdb_data.get('id')}")
            return {
                "title": title,
                "name": name_only,
                "synopsis": final_synopsis or "",
                "year": year or tmdb_data.get("release_date", "")[:4],
                "tipo": tipo,
                "slug": slug,
                "poster": f"https://image.tmdb.org/t/p/w500{tmdb_data['poster_path']}" if tmdb_data.get("poster_path") else f"https://assistir.app/capas/{slug}.jpg",
                "backdrop": f"https://image.tmdb.org/t/p/original{tmdb_data['backdrop_path']}" if tmdb_data.get("backdrop_path") else None,
                "rating": round(tmdb_data.get("vote_average", (float(details.get("nota", 0)) if details.get("nota") else 0)), 1),
                "genres": [g["name"] for g in tmdb_data.get("genres", [])] if "genres" in tmdb_data else details.get("gênero", "").split(","),
                "details": details,
                "id_tmdb": tmdb_data.get("id"),
                "recommendations": recommendations,
                "players": players,
                "trailer": next((f"https://www.youtube.com/embed/{v['key']}" for v in tmdb_data.get("videos", {}).get("results", []) if v.get("site") == "YouTube" and v.get("type") == "Trailer"), None),
                "certification": tmdb_data.get("certification", "L"),
                "cast": [{
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "character": p.get("character"),
                    "photo": f"https://image.tmdb.org/t/p/w200{p.get('profile_path')}" if p.get("profile_path") else None
                } for p in tmdb_data.get("credits", {}).get("cast", [])[:12]]
            }
            
        except Exception as e:
            print(f"Erro ao buscar info: {e}")
            raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/busca/{query}")
async def full_search_proxy(query: str):
    """
    Realiza uma busca completa fazendo scraping do assistir.app e enriquecendo com TMDB.
    """
    from bs4 import BeautifulSoup
    query_clean = query.lower().strip()
    
    # 0. Verifica o Cache (usando um prefixo para diferenciar da busca de sugestões)
    cache_key = f"full_{query_clean}"
    current_time = time.time()
    if cache_key in search_cache:
        timestamp, cached_data = search_cache[cache_key]
        if current_time - timestamp < CACHE_EXPIRATION:
            return cached_data
            
    # URL de busca no assistir.app
    url = f"https://assistir.app/busca?q={query_clean}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"}
    
    async with SafeAsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(url, headers=headers, timeout=15.0)
            if response.status_code != 200:
                return []
                
            soup = BeautifulSoup(response.text, 'html.parser')
            cards = soup.find_all('div', class_='card')
            
            results = []
            for card in cards:
                try:
                    title_tag = card.find('h3', class_='card__title')
                    if not title_tag: continue
                    
                    link_tag = title_tag.find('a')
                    name = link_tag.get_text().strip()
                    path = link_tag['href']
                    
                    # Extrai ano e categoria
                    cat_tag = card.find('span', class_='card__category')
                    info_text = cat_tag.get_text().strip() if cat_tag else ""
                    
                    # Tenta extrair o ano (geralmente os últimos 4 dígitos)
                    import re
                    year_match = re.search(r'(\d{4})', info_text)
                    year = year_match.group(1) if year_match else ""
                    
                    # Slug e Tipo
                    slug = path.split('/')[-1]
                    tipo = "filme" if "/filme/" in path else "serie"
                    
                    # Extrai a nota
                    rate_tag = card.find('span', class_='card__rate')
                    rate = rate_tag.get_text().strip() if rate_tag else ""
                    
                    results.append({
                        "nome": name,
                        "slug": slug,
                        "ano": year,
                        "tipo": tipo,
                        "info": info_text,
                        "nota": rate
                    })
                except Exception as e:
                    print(f"Erro ao processar card: {e}")
                    continue
            
            # Enriquecimento com TMDB (limitado aos 20 primeiros para performance)
            enriched_results = []
            for item in results[:20]:
                name = item["nome"]
                year = item["ano"]
                item["ano"] = "" # Força usar apenas dados do TMDB se encontrado
                slug = item["slug"]
                
                # Fallback
                image_url = f"https://assistir.app/capas/{slug}.jpg"
                
                try:
                    current_key = get_random_tmdb_key()
                    # Usa o endpoint específico se soubermos o tipo, melhora muito a precisão do 'year'
                    endpoint = "movie" if item["tipo"] == "filme" else "tv"
                    tmdb_url = f"https://api.themoviedb.org/3/search/{endpoint}"
                    
                    tmdb_params = {
                        "api_key": current_key,
                        "query": name,
                        "language": "pt-BR"
                    }
                    if year:
                        if endpoint == "movie":
                            tmdb_params["year"] = year
                        else:
                            tmdb_params["first_air_date_year"] = year
                        
                    tmdb_res = await client.get(tmdb_url, params=tmdb_params, timeout=2.0)
                    if tmdb_res.status_code == 200:
                        tmdb_json = tmdb_res.json()
                        tmdb_results = tmdb_json.get("results", [])
                        
                        if tmdb_results:
                            best_match = None
                            title_matches = []
                            
                            # Limpa o título buscado de anos (ex: Matrix (1999) -> Matrix)
                            clean_search_title = re.sub(r'\(\d{4}\)', '', name).strip().lower()
                            
                            for res in tmdb_results:
                                # Extração de dados
                                res_title = (res.get("title") or res.get("name") or "").lower()
                                res_orig_title = (res.get("original_title") or res.get("original_name") or "").lower()
                                res_date = res.get("release_date") or res.get("first_air_date") or ""
                                res_year = res_date.split("-")[0] if res_date else ""
                                
                                # Verificações mais flexíveis
                                is_title_match = (res_title == clean_search_title) or (res_orig_title == clean_search_title) or \
                                               (clean_search_title in res_title) or (res_title in clean_search_title)
                                
                                is_year_match = (year and str(year) == res_year)
                                
                                # 1. Match Perfeito (Título + Ano)
                                if is_title_match and is_year_match:
                                    best_match = res
                                    break
                                
                                # 2. Lista de candidatos por título
                                if is_title_match:
                                    title_matches.append(res)
                            
                            # Seleção do Melhor Candidato
                            target_data = best_match
                            if not target_data and title_matches:
                                # Desempate por popularidade
                                title_matches.sort(key=lambda x: x.get("popularity", 0), reverse=True)
                                target_data = title_matches[0]
                            
                            # Fallback: Primeiro resultado se nada der certo
                            if not target_data:
                                target_data = tmdb_results[0]
                            
                            if target_data:
                                if target_data.get("poster_path"):
                                    image_url = f"https://image.tmdb.org/t/p/w300{target_data['poster_path']}"
                                
                                # Atualiza o ano com o do TMDB (geralmente mais preciso)
                                res_date = target_data.get("release_date") or target_data.get("first_air_date") or ""
                                if res_date:
                                    item["ano"] = res_date.split("-")[0]
                                if target_data.get("genre_ids"):
                                    item["genero"] = ", ".join([GENRE_MAP.get(gid, "") for gid in target_data["genre_ids"] if GENRE_MAP.get(gid)])
                except Exception:
                    pass
                
                item["capa"] = image_url
                enriched_results.append(item)
                
            # Salva no Cache
            search_cache[cache_key] = (current_time, enriched_results)
            return enriched_results
            
        except Exception as e:
            print(f"Erro na busca completa: {e}")
            return []

# Mapeamento de categorias (nome amigável -> slug do assistir.app)
CATEGORIA_SLUGS = {
    "acao": "acao",
    "animacao": "animacao",
    "aventura": "aventura",
    "comedia": "comedia",
    "crime": "crime",
    "documentario": "documentario",
    "drama": "drama",
    "familia": "familia",
    "fantasia": "fantasia",
    "faroeste": "faroeste",
    "ficcao-cientifica": "ficcao-cientifica",
    "ficção científica": "ficcao-cientifica",
    "guerra": "guerra",
    "historia": "historia",
    "misterio": "misterio",
    "romance": "romance",
    "terror": "terror",
    "thriller": "thriller",
}

@app.get("/api/categoria/{categoria}")
async def get_categoria(categoria: str, page: int = 1):
    """
    Lista filmes e séries de uma categoria específica.
    Faz scraping do assistir.app e enriquece com posters do TMDB.
    """
    from bs4 import BeautifulSoup
    import re
    
    # Normaliza o slug da categoria
    categoria_clean = categoria.lower().strip()
    categoria_slug = CATEGORIA_SLUGS.get(categoria_clean, categoria_clean)
    
    # Cache key inclui a página
    cache_key = f"cat_{categoria_slug}_p{page}"
    current_time = time.time()
    if cache_key in search_cache:
        timestamp, cached_data = search_cache[cache_key]
        if current_time - timestamp < CACHE_EXPIRATION:
            print(f"Cache Hit: {cache_key}")
            return cached_data
    
    # URL da categoria no assistir.app
    url = f"https://assistir.app/categoria/{categoria_slug}?page={page}"
    
    print(f"Fetching categoria: {url}")
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"}
    
    async with SafeAsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(url, headers=headers, timeout=15.0)
            if response.status_code != 200:
                print(f"Categoria {categoria_slug} retornou status {response.status_code}")
                return {"items": [], "categoria": categoria_slug, "page": page, "has_more": False}
                
            soup = BeautifulSoup(response.text, 'html.parser')
            cards = soup.find_all('div', class_='card')
            
            results = []
            for card in cards:
                try:
                    # Título - pode estar direto no h3 ou dentro de um link
                    title_tag = card.find('h3', class_='card__title')
                    if not title_tag: 
                        continue
                    
                    # Nome do título
                    link_tag = title_tag.find('a') or card.find('a', class_='card__play')
                    if link_tag:
                        name = title_tag.get_text().strip()
                        path = link_tag.get('href', '')
                    else:
                        name = title_tag.get_text().strip()
                        # Tenta pegar o link de outro lugar
                        any_link = card.find('a', href=True)
                        path = any_link['href'] if any_link else ''
                    
                    if not name or not path:
                        continue
                    
                    # Extrai ano e categoria do card__category
                    cat_tag = card.find('span', class_='card__category')
                    info_text = cat_tag.get_text().strip() if cat_tag else ""
                    
                    year_match = re.search(r'(\d{4})', info_text)
                    year = year_match.group(1) if year_match else ""
                    
                    # Slug e Tipo
                    slug = path.split('/')[-1]
                    tipo = "filme" if "/filme/" in path else "serie"
                    
                    # Nota
                    rate_tag = card.find('span', class_='card__rate')
                    rate = rate_tag.get_text().strip() if rate_tag else ""
                    
                    results.append({
                        "nome": name,
                        "slug": slug,
                        "ano": year,
                        "tipo": tipo,
                        "info": info_text,
                        "nota": rate
                    })
                except Exception as e:
                    print(f"Erro ao processar card de categoria: {e}")
                    continue
            
            print(f"Categoria {categoria_slug}: {len(results)} itens encontrados")
            
            # Enriquecimento com TMDB (paralelo para performance)
            async def enrich_item(item):
                try:
                    current_key = get_random_tmdb_key()
                    tmdb_params = {
                        "api_key": current_key,
                        "query": item["nome"],
                        "language": "pt-BR",
                        "include_adult": "false"
                    }
                    if item["ano"]:
                        tmdb_params["year"] = item["ano"]
                        
                    tmdb_res = await client.get("https://api.themoviedb.org/3/search/multi", params=tmdb_params, timeout=2.0)
                    if tmdb_res.status_code == 200:
                        tmdb_data = tmdb_res.json()
                        if tmdb_data.get("results"):
                            for match in tmdb_data["results"]:
                                if match.get("poster_path"):
                                    item["capa"] = f"https://image.tmdb.org/t/p/w300{match['poster_path']}"
                                    # Também pega a nota do TMDB se disponível
                                    if match.get("vote_average"):
                                        item["nota"] = str(round(match["vote_average"], 1))
                                    
                                    # Pega os gêneros
                                    if match.get("genre_ids"):
                                        item["genero"] = ", ".join([GENRE_MAP.get(gid, "") for gid in match["genre_ids"] if GENRE_MAP.get(gid)])
                                    else:
                                        item["genero"] = ""
                                        
                                    break
                except Exception:
                    pass
                
                # Fallback se não encontrou poster
                if "capa" not in item:
                    item["capa"] = f"https://assistir.app/capas/{item['slug']}.jpg"
                
                return item
            
            # Processa em paralelo (limitado a 24 itens)
            tasks = [enrich_item(item) for item in results[:24]]
            enriched_results = await asyncio.gather(*tasks)
            
            # Verifica se há mais páginas
            has_more = len(results) >= 20  # Se tem 20+ resultados, provavelmente há mais páginas
            
            # Monta resposta
            response_data = {
                "items": enriched_results,
                "categoria": categoria_slug,
                "page": page,
                "has_more": has_more
            }
            
            # Salva no Cache
            search_cache[cache_key] = (current_time, response_data)
            return response_data
            
        except Exception as e:
            print(f"Erro ao buscar categoria: {e}")
            return {"items": [], "categoria": categoria_slug, "page": page, "has_more": False, "error": str(e)}

@app.get("/api/player-proxy")
async def player_proxy(url: str):
    """
    Proxy que baixa o player original, remove anti-dev-tools e troca a logo.
    """
    import re
    if not url.startswith("http"):
        url = f"https:{url}" if url.startswith("//") else f"https://www.assistir.app{url}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Referer": "https://www.assistir.app/",
        "Origin": "https://www.assistir.app"
    }

    async with SafeAsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(url, headers=headers, timeout=10.0)
            if response.status_code != 200:
                return response.text
            
            html = response.text
            
            # 1. Troca de Logo (tentativa por regex e substituição de strings comuns)
            # Vamos injetar um script que faz isso no DOM e também trocar no HTML se acharmos
            custom_logo = "/logo.png"
            
            # 2. Injeção de CSS e JS Customizado
            injection = f"""
            <style>
                /* Oculta logos flutuantes conhecidas ou marcas d'água */
                .logo, .watermark, [class*="logo"], [id*="logo"] {{
                    display: none !important;
                }}
                /* Ajusta o player se necessário */
                .plyr--video {{
                    height: 100vh !important;
                }}
            </style>
            <script>
                // Tenta neutralizar detecção de console que usa eval/Function
                try {{
                    const originalConstructor = Function.prototype.constructor;
                    Function.prototype.constructor = function(str) {{
                        if (str && str.includes('debugger')) return function() {{}};
                        return originalConstructor.apply(this, arguments);
                    }};
                }} catch(e) {{}}

                // Tenta forçar a nossa logo em qualquer lugar que pareça uma logo
                window.addEventListener('DOMContentLoaded', function() {{
                    const images = document.getElementsByTagName('img');
                    for(let img of images) {{
                        if(img.src.includes('logo') || img.src.includes('favicon')) {{
                            img.src = '{custom_logo}';
                        }}
                    }}
                    // Oculta players que não carregam ou avisos
                    const debugDivs = document.querySelectorAll('div');
                    for(let div of debugDivs) {{
                        if(div.textContent.includes('developer tools')) {{
                            div.style.display = 'none';
                        }}
                    }}
                }});
            </script>
            """
            
            # Insere antes do fechamento do head ou no início do body
            if "</head>" in html:
                html = html.replace("</head>", f"{injection}</head>")
            else:
                html = f"{injection}{html}"
                
            # Corrige caminhos relativos para caminhos absolutos do provedor
            # Mantemos os originais mas garantimos que as requisições de mídia funcionem
            html = html.replace('src="//', 'src="https://')
            html = html.replace('href="//', 'href="https://')
            html = html.replace('src="/assets', 'src="https://www.assistir.app/assets')
            html = html.replace('href="/assets', 'href="https://www.assistir.app/assets')
            html = html.replace('src="/js', 'src="https://www.assistir.app/js')
            html = html.replace('src="/css', 'src="https://www.assistir.app/css')

            from fastapi.responses import HTMLResponse
            return HTMLResponse(content=html, headers={
                "Access-Control-Allow-Origin": "*",
                "X-Frame-Options": "ALLOW-FROM *"
            }, status_code=200)

        except Exception as e:
            from fastapi.responses import HTMLResponse
            return HTMLResponse(content=f"Erro no proxy: {str(e)}", status_code=500)

@app.get("/api/stream")
async def get_stream(url: str, request: Request):
    """
    Tenta extrair a URL direta do vídeo de um iframe.
    """
    if not url.startswith("http"):
        url = f"https:{url}" if url.startswith("//") else f"https://www.assistir.app{url}"

    base_url = str(request.base_url).rstrip('/')
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Referer": "https://www.assistir.app/",
    }

    async with SafeAsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(url, headers=headers, timeout=10.0)
            if response.status_code != 200:
                return {"error": "Falha ao acessar o player"}
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Procura tag <source>
            source_tag = soup.find('source')
            if source_tag and source_tag.get('src'):
                src = source_tag['src']
                if src.startswith('//'): src = f"https:{src}"
                
                # Aplica o Proxy se necessário
                from urllib.parse import quote
                # 1. Se for m3u8, NÃO PROXY
                if ".m3u8" in src:
                     return {"url": src, "type": "application/x-mpegURL", "original_url": src}
                
                # 2. Se for MP4 do assistir.app, resolvemos o redirect
                if ".mp4" in src or "assistir.app" in src:
                    try:
                        if "assistir.app" in src:
                            # Segue o redirect no backend para pegar a URL final (CDN)
                            r = await client.head(src, headers=headers, follow_redirects=True, timeout=8.0)
                            final_url = str(r.url)
                            print(f"Redirect resolvido: {src} -> {final_url}")
                            
                            # Retornamos o link direto resolvido (CDN)
                            return {"url": final_url, "type": "video/mp4", "direct": True}
                    except Exception as e:
                        print(f"Erro ao resolver redirect: {e}")
                    
                    return {"url": src, "type": "video/mp4", "direct": True}
                    
                return {"url": src, "type": source_tag.get('type', 'video/mp4')}
            
            # Procura script que define o player ou source
            import re
            from urllib.parse import quote
            patterns = [
                r'file:\s*["\']([^"\']+)["\']',
                r'source:\s*["\']([^"\']+)["\']',
                r'src:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'src:\s*["\']([^"\']+\.mp4[^"\']*)["\']'
            ]
            for pattern in patterns:
                m = re.search(pattern, response.text)
                if m:
                    stream_url = m.group(1)
                    if stream_url.startswith('//'): stream_url = f"https:{stream_url}"
                    
                    # Logica de Proxy
                    # 1. Se for m3u8, NÃO usamos o video-proxy simples (quebra HLS)
                    if ".m3u8" in stream_url:
                         return {"url": stream_url, "type": "application/x-mpegURL"}
                         
                    # 2. Se for MP4 do assistir.app, resolvemos o redirect
                    if ".mp4" in stream_url or "assistir.app" in stream_url:
                        try:
                            if "assistir.app" in stream_url:
                                r = await client.head(stream_url, headers=headers, follow_redirects=True, timeout=8.0)
                                final_url = str(r.url)
                                print(f"Redirect resolvido: {stream_url} -> {final_url}")
                                # Retornamos o link direto resolvido
                                return {"url": final_url, "type": "video/mp4", "direct": True}
                        except Exception as e:
                            print(f"Erro ao resolver redirect: {e}")

                        return {"url": stream_url, "type": "video/mp4", "direct": True}
                    
                    # Default fallback
                    mime_type = "video/mp4"
                    return {"url": stream_url, "type": mime_type, "direct": True}
                
            return {"error": "Fonte não encontrada"}
        except Exception as e:
            return {"error": str(e)}

@app.get("/api/dlna/devices")
async def get_dlna_devices():
    """
    Escaneia a rede local em busca de dispositivos DLNA (Smart TVs).
    """
    try:
        # nanodlna discovery é síncrono, então rodamos em thread
        found_devices = await asyncio.to_thread(devices.get_devices, 5)
        
        result = []
        for d in found_devices:
            result.append({
                "name": d.friendly_name,
                "location": d.location,
                "ip": d.hostname
            })
        return result
    except Exception as e:
        print(f"Erro no DLNA Discovery: {e}")
        return []

@app.get("/api/dlna/cast")
async def dlna_cast(device_ip: str, video_url: str):
    """
    Envia o comando de reprodução para o dispositivo DLNA.
    """
    try:
        # Se a URL for localhost, troca pelo IP local para a TV conseguir acessar
        if "localhost" in video_url:
            video_url = video_url.replace("localhost", LOCAL_IP)
        elif "127.0.0.1" in video_url:
            video_url = video_url.replace("127.0.0.1", LOCAL_IP)
            
        print(f"Casting to {device_ip}: {video_url}")
        
        # Procura o dispositivo pelo IP
        found_devices = await asyncio.to_thread(devices.get_devices, 3)
        target = None
        for d in found_devices:
            if d.hostname == device_ip:
                target = d
                break
        
        if not target:
            return {"error": "Dispositivo não encontrado"}
        
        # Envia o comando de play
        # dlna.play(video_url, target) é síncrono
        await asyncio.to_thread(dlna.play, video_url, target)
        
        return {"success": True, "message": f"Reproduzindo em {target.friendly_name}"}
    except Exception as e:
        print(f"Erro ao transmitir DLNA: {e}")
@app.api_route("/api/video-proxy", methods=["GET", "HEAD"])
async def video_proxy(url: str, request: Request):
    """
    Proxy de Streaming de Vídeo com suporte a Range Requests (Crucial para Smart TVs/DLNA).
    """
    from fastapi.responses import StreamingResponse
    
    if not url.startswith("http"):
        raise HTTPException(status_code=400, detail="URL Inválida")
        
    async with SafeAsyncClient(follow_redirects=True) as client:
        # Pega o tamanho total primeiro (HEAD)
        try:
             head_resp = await client.head(url, headers={
                 "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                 "Referer": "https://www.assistir.app/"
             })
             total_size = int(head_resp.headers.get("Content-Length", 0))
        except:
             total_size = 0

        # Processa o header Range do cliente (TV/Browser)
        range_header = request.headers.get("range")
        start = 0
        end = total_size - 1 if total_size > 0 else None
        
        if range_header:
            try:
                # Ex: bytes=0-
                scope = range_header.split("=")[1]
                parts = scope.split("-")
                start = int(parts[0]) if parts[0] else 0
                if len(parts) > 1 and parts[1]:
                    end = int(parts[1])
            except:
                pass
        
        # Se não tivermos tamanho total, assumimos um chunk grande ou stream contínuo
        chunk_size = 1024 * 1024 # 1MB chunks
        if end is not None:
             content_length = end - start + 1
        else:
             content_length = int(head_resp.headers.get("Content-Length", 0)) - start
             if content_length < 0: content_length = None
             
        # Headers para o request ao servidor original
        upstream_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://assistir.app/",
            "Range": f"bytes={start}-{end if end else ''}"
        }

        print(f"Proxying: {url} | Range: {range_header} | Start: {start} End: {end}")

        async def iterfile():
            async with httpx.AsyncClient(follow_redirects=True) as dl_client:
                 try:
                     # User-Agent móvel às vezes ajuda a contornar bloqueios
                     m_headers = upstream_headers.copy()
                     m_headers["User-Agent"] = "Mozilla/5.0 (Linux; Android 10; SM-A205U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.5993.71 Mobile Safari/537.36"
                     
                     async with dl_client.stream("GET", url, headers=m_headers, timeout=30.0) as r:
                         if r.status_code not in [200, 206]:
                             print(f"Upstream returned status {r.status_code} for {url}")
                             # Se falhar, tenta stream sem range
                             # return
                         
                         async for chunk in r.aiter_bytes():
                             yield chunk
                 except Exception as e:
                     print(f"Stream error: {e}")

        # Headers de resposta para a TV
        content_type = head_resp.headers.get("Content-Type", "video/mp4")
        response_headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Expose-Headers": "Content-Range, Content-Length, Accept-Ranges",
            "Accept-Ranges": "bytes",
            "Content-Type": content_type
        }
        
        if total_size > 0:
             if range_header:
                 response_headers["Content-Range"] = f"bytes {start}-{end}/{total_size}"
                 response_headers["Content-Length"] = str(content_length)
             else:
                 response_headers["Content-Length"] = str(total_size)

        return StreamingResponse(
            iterfile(), 
            status_code=206 if range_header and total_size > 0 else 200, 
            media_type="video/mp4", 
            headers=response_headers
        )


@app.get("/api/discussions/{tipo}/{tmdb_id}")
async def get_discussions(tipo: str, tmdb_id: str):
    """
    Busca discussões (tópicos do fórum) do TMDB fazendo scraping do site.
    """
    media_type = "movie" if "filme" in tipo.lower() else "tv"
    # Adicionamos o ID da categoria 'General' (5047951f760ee3318900009a) para ignorar 'Content Issues'
    url = f"https://www.themoviedb.org/{media_type}/{tmdb_id}/discuss/category/5047951f760ee3318900009a"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    
    import logging
    logger = logging.getLogger(__name__)
    
    async with httpx.AsyncClient(follow_redirects=True, headers=headers) as client:
        try:
            # URL Forçada para Categoria General - TMDB ID: 5047951f760ee3318900009a
            url = f"https://www.themoviedb.org/{media_type}/{tmdb_id}/discuss/category/5047951f760ee3318900009a"
            logger.info(f"SCRAPER: Iniciando busca em {url}")
            
            response = await client.get(url, timeout=12.0)
            if response.status_code != 200:
                logger.error(f"SCRAPER ERROR: Status {response.status_code} para {url}")
                return []
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            threads = []
            # Regex específica para IDs de 24 caracteres hexadecimais no final do link
            pattern = re.compile(r'/discuss/([0-9a-f]{24})$')
            
            for a in soup.find_all('a', href=True):
                full_href = a['href']
                # Limpa querystring e fragmentos
                href_clean = full_href.split('?')[0].split('#')[0]
                
                match = pattern.search(href_clean)
                if match:
                    title = a.get_text(strip=True)
                    # Filtra explicitamente threads que não queremos (Content Issues auto-gen)
                    is_banished = "Reported Problem" in title or "Content Issue" in title
                    
                    if title and not is_banished and title != "Show More":
                        thread_id = match.group(1)
                        if thread_id not in [t['id'] for t in threads]:
                            threads.append({
                                "title": title,
                                "url": "https://www.themoviedb.org" + href_clean,
                                "id": thread_id
                            })
            
            logger.info(f"SCRAPER: Encontradas {len(threads)} threads válidas após filtros.")
            # Pega as 4 discussões mais recentes
            selected_threads = threads[:4]
            
            async def fetch_thread_detail(thread):
                try:
                    res = await client.get(thread['url'], timeout=6.0)
                    if res.status_code == 200:
                        inner_soup = BeautifulSoup(res.text, 'html.parser')
                        
                        # Cada post está em um div.carton
                        cartons = inner_soup.find_all('div', class_='carton')
                        if not cartons:
                             return None
                             
                        thread_posts = []
                        for carton in cartons:
                            # Autor - procura por links para perfil de usuário
                            author = "Usuário TMDB"
                            # Coleta todos os links de usuário e pega o com texto mais longo
                            user_links = []
                            all_links = carton.find_all('a', href=True)
                            for link in all_links:
                                href = link.get('href', '')
                                text = link.get_text(strip=True)
                                if '/u/' in href:
                                    if text and len(text) > 1:
                                        user_links.append(text)
                                    else:
                                        # Extrai o nome do href (ex: /u/DaMan -> DaMan)
                                        username = href.split('/u/')[-1].split('/')[0].split('?')[0]
                                        if username:
                                            user_links.append(username)
                            
                            # Pega o nome de usuário mais longo (geralmente o correto)
                            if user_links:
                                author = max(user_links, key=len)
                            else:
                                # Fallback: tenta extrair do h3 "posted by X on..."
                                h3_tags = carton.find_all('h3')
                                for h3 in h3_tags:
                                    h3_text = h3.get_text(strip=True)
                                    if 'posted by' in h3_text.lower():
                                        match = re.search(r'posted by\s+([\w\d_-]+)', h3_text, re.IGNORECASE)
                                        if match:
                                            author = match.group(1)
                                            break
                            
                            # Data
                            date_str = "Recente"
                            h3_tags = carton.find_all('h3')
                            for h3 in h3_tags:
                                if 'on' in h3.get_text().lower():
                                    date_str = h3.get_text(separator=' ', strip=True).split('on')[-1].strip()
                                    break
                            
                            # Conteúdo - com limpeza avançada
                            content_div = carton.find('div', class_='content') or carton.find('div', class_='content_wrapper')
                            content = ""
                            quote = ""  # Para armazenar citações separadas
                            
                            if content_div:
                                # Remove elementos de navegação e headers
                                for junk in content_div.find_all(['h2', 'h3', 'nav', 'script', 'style']):
                                    junk.decompose()
                                
                                # Extrai citações (blockquote) separadamente
                                blockquotes = content_div.find_all('blockquote')
                                if blockquotes:
                                    quote_parts = []
                                    for bq in blockquotes:
                                        quote_text = bq.get_text(strip=True)
                                        if quote_text:
                                            quote_parts.append(quote_text)
                                        bq.decompose()  # Remove do conteúdo principal
                                    quote = ' | '.join(quote_parts)
                                
                                # Pega o texto restante (sem as citações)
                                raw_content = content_div.get_text(separator=' ', strip=True)
                                
                                # Limpa padrões de "@user said:" que aparecem no início
                                cleaned = re.sub(r'^@\w+\s*said:\s*', '', raw_content, flags=re.IGNORECASE)
                                # Limpa "said:" solto
                                cleaned = re.sub(r'^said:\s*', '', cleaned, flags=re.IGNORECASE)
                                # Remove espaços múltiplos
                                cleaned = re.sub(r'\s+', ' ', cleaned).strip()
                                
                                content = cleaned
                            
                            if content:
                                thread_posts.append({
                                    "author": author,
                                    "content": content,
                                    "quote": quote if quote else None,
                                    "date": date_str
                                })
                        
                        if not thread_posts:
                            return None
                            
                        main_post = thread_posts[0]
                        return {
                            "id": thread['id'],
                            "author": main_post['author'],
                            "title": thread['title'],
                            "content": main_post['content'],
                            "created_at": main_post['date'],
                            "url": thread['url'],
                            "replies": thread_posts[1:] # Lista de respostas
                        }
                except Exception as e:
                    print(f"Erro no detalhe da thread: {e}")
                return None

            tasks = [fetch_thread_detail(t) for t in selected_threads]
            results = await asyncio.gather(*tasks)
            
            return [r for r in results if r]
            
        except Exception as e:
            print(f"Erro ao buscar discussões: {e}")
            return []


# --- W2G TRANSMISSION SYSTEM ---
from pydantic import BaseModel

class CreateTransmissionRequest(BaseModel):
    title: str
    user_id: str = None
    user_name: str = None
    
class JoinTransmissionRequest(BaseModel):
    token: str
    user_id: str = None
    user_name: str = None

@app.post("/api/transmission/create")
async def create_transmission(req: CreateTransmissionRequest, current_user: dict = Depends(get_current_user)):
    users = load_users()
    
    if current_user:
        google_id = current_user.get("sub")
        user_info = users.get(google_id)
        if not user_info:
            user_info = {
                "name": current_user.get("name", "Usuário"),
                "picture": current_user.get("picture", "")
            }
    else:
        # Usuário Anônimo ou ID vindo do frontend
        google_id = req.user_id or f"anon_{uuid.uuid4().hex[:8]}"
        user_info = {
            "name": req.user_name or "Pipoca Anônimo",
            "picture": f"https://api.dicebear.com/7.x/avataaars/svg?seed={google_id}"
        }
        
    token = manager.create(google_id, user_info, req.title)
    return {"token": token, "url": f"/player?transmission={token}"}

@app.post("/api/transmission/join")
async def join_transmission(req: JoinTransmissionRequest, current_user: dict = Depends(get_current_user)):
    users = load_users()
    
    if current_user:
        google_id = current_user.get("sub")
        user_info = users.get(google_id)
        if not user_info:
            user_info = {
                "name": current_user.get("name", "Usuário"),
                "picture": current_user.get("picture", "")
            }
    else:
        # Usuário Anônimo ou ID vindo do frontend
        google_id = req.user_id or f"anon_{uuid.uuid4().hex[:8]}"
        user_info = {
            "name": req.user_name or "Pipoca Anônimo",
            "picture": f"https://api.dicebear.com/7.x/avataaars/svg?seed={google_id}"
        }
        
    success = manager.join(req.token, google_id, user_info)
    if not success:
        raise HTTPException(status_code=400, detail="Sala cheia ou inválida")
        
    room_info = manager.active_transmissions.get(req.token)
    role = "host" if room_info.get("host_id") == google_id else "guest"
        
    logger.info(f"Join Success: {google_id} na sala {req.token} como {role}")
    return {"token": req.token, "role": role}

@app.get("/api/transmission/debug")
async def debug_transmission():
    """Endpoint para debugar o estado das salas em produção"""
    return {
        "active_rooms": list(manager.active_transmissions.keys()),
        "room_count": len(manager.active_transmissions),
        "details": {k: {"host": v["host_id"], "parts": list(v["participants"].keys())} for k, v in manager.active_transmissions.items()}
    }

# WebSockets removed in favor of Socket.io
# -----------------------------------
@app.get("/api/home")
async def home_page():
    """
    Retorna o conteúdo da página inicial do assistir.app:
    - Destaques (Carousel)
    - Mais Assistidos
    - Últimos Adicionados
    - Lançamentos 2026
    - Séries
    """
    from bs4 import BeautifulSoup
    import re
    
    # Cache key global para a home
    cache_key = "home_page_content_v3_sorted"
    current_time = time.time()
    
    # 15 minutos de cache para a home
    if cache_key in search_cache:
        timestamp, cached_data = search_cache[cache_key]
        if current_time - timestamp < 900: # 15 min
            print("Home Cache Hit")
            return cached_data
            
    url = "https://assistir.app/inicio"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"}
    
    print(f"Fetching home: {url}")
    
    async with SafeAsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(url, headers=headers, timeout=15.0)
            if response.status_code != 200:
                return {"error": "Falha ao carregar home"}
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            result_data = {
                "featured": [],
                "most_watched": [],
                "recently_added": [],
                "releases_2026": [],
                "series": []
            }
            
            # Função auxiliar para extrair dados de um container de cards
            def extract_cards(container):
                items = []
                if not container: return items
                
                cards = container.find_all('div', class_='card')
                for card in cards:
                    try:
                        title_tag = card.find('h3', class_='card__title')
                        if not title_tag: continue
                        
                        link_tag = title_tag.find('a') or card.find('a', class_='card__play')
                        if not link_tag:
                            any_link = card.find('a', href=True)
                            if any_link: link_tag = any_link
                            else: continue
                            
                        name = title_tag.get_text().strip()
                        path = link_tag['href']
                        
                        cat_tag = card.find('span', class_='card__category')
                        info_text = cat_tag.get_text().strip() if cat_tag else ""
                        
                        year_match = re.search(r'(\d{4})', info_text)
                        year = year_match.group(1) if year_match else ""
                        
                        slug = path.split('/')[-1]
                        tipo = "filme" if "/filme/" in path else "serie"
                        
                        rate_tag = card.find('span', class_='card__rate')
                        rate = rate_tag.get_text().strip() if rate_tag else ""
                        
                        # Tenta pegar imagem background se existir (comum em carrossel)
                        bg_img = ""
                        # Verifica style="background-image: url(...)"
                        style = card.get('style', '')
                        if 'background-image' in style:
                             bg_match = re.search(r'url\([\'"]?([^\'"\)]+)[\'"]?\)', style)
                             if bg_match: bg_img = bg_match.group(1)

                        # Extrai Tag
                        tag_text = ""
                        tag_elem = card.find('div', class_='tags-top') or card.find('span', class_='tag-hd') or card.find('span', class_='card__new')
                        if tag_elem:
                            tag_text = tag_elem.get_text().strip()

                        items.append({
                            "nome": name,
                            "slug": slug,
                            "ano": year,
                            "tipo": tipo,
                            "info": info_text,
                            "nota": rate,
                            "tag": tag_text,
                            "capa_original": bg_img
                        })
                    except: pass
                return items

            # 1. Destaques (Carousel)
            sections = soup.find_all('section')
            
            for section in sections:
                title_el = section.find('h2', class_='section__title')
                title_text = title_el.get_text().strip().upper() if title_el else ""
                
                # Identifica a seção pelo título
                section_key = ""
                if "ASSISTIDOS" in title_text:
                    section_key = "most_watched"
                elif "ADICIONADOS" in title_text:
                    section_key = "recently_added"
                elif "2026" in title_text: 
                    section_key = "releases_2026"
                elif "SÉRIES" in title_text or "SERIES" in title_text:
                    section_key = "series"
                elif "DESTAQUES" in title_text:
                    section_key = "featured"
                
                if section_key:
                    items = extract_cards(section)
                    if items:
                         # Prioriza itens com TAG (Novos Episódios, etc)
                         if section_key in ["series", "recently_added"]:
                             items.sort(key=lambda x: "NOVOS EPS" not in x.get("tag", "").upper())
                         result_data[section_key] = items

            # Se featured estiver vazio, tenta carrossel principal
            if not result_data["featured"]:
                 home_carousel = soup.find('div', class_='home__carousel') or soup.find('section', class_='home')
                 if home_carousel:
                      result_data["featured"] = extract_cards(home_carousel)

            # Enriquecimento com TMDB (paralelo)
            async def enrich_list(items_list):
                if not items_list: return []
                
                async def enrich_item(item):
                    try:
                        current_key = get_random_tmdb_key()
                        tmdb_params = {
                            "api_key": current_key,
                            "query": item["nome"],
                            "language": "pt-BR",
                            "include_adult": "false"
                        }
                        if item["ano"]:
                            tmdb_params["year"] = item["ano"]
                            
                        tmdb_res = await client.get("https://api.themoviedb.org/3/search/multi", params=tmdb_params, timeout=2.0)
                        if tmdb_res.status_code == 200:
                            tmdb_data = tmdb_res.json()
                            if tmdb_data.get("results"):
                                for match in tmdb_data["results"]:
                                    if match.get("poster_path"):
                                        item["capa"] = f"https://image.tmdb.org/t/p/w300{match['poster_path']}"
                                        if match.get("backdrop_path"):
                                            item["backdrop"] = f"https://image.tmdb.org/t/p/original{match['backdrop_path']}"
                                        if match.get("vote_average"):
                                            item["nota"] = str(round(match["vote_average"], 1))
                                        item["sinopse"] = match.get("overview", "")
                                        break
                    except: pass
                    
                    if "capa" not in item:
                        item["capa"] = f"https://assistir.app/capas/{item['slug']}.jpg"
                    return item

                tasks = [enrich_item(item) for item in items_list[:12]] # Limita a 12 itens por seção para não estourar
                return await asyncio.gather(*tasks)

            # Enriquece todas as listas
            result_data["featured"] = await enrich_list(result_data["featured"])
            result_data["most_watched"] = await enrich_list(result_data["most_watched"])
            result_data["recently_added"] = await enrich_list(result_data["recently_added"])
            result_data["releases_2026"] = await enrich_list(result_data["releases_2026"])
            result_data["series"] = await enrich_list(result_data["series"])
            
            search_cache[cache_key] = (current_time, result_data)
            return result_data
            
        except Exception as e:
            print(f"Erro na home: {e}")
            return {"error": str(e)}
@app.get("/api/series/all")
async def get_series_all(page: int = 1):
    """
    Lista todas as séries do assistir.app via in-memory pagination.
    A página /series-todas retorna ~230 itens de uma vez.
    """
    from bs4 import BeautifulSoup
    import re
    import logging
    
    logger.info(f"Start get_series_all page={page}")
    logging.info(f"Start get_series_all page={page}")
    
    # Cache key para a lista COMPLETA
    cache_key_full = "series_all_full_list_v8_sorted"
    current_time = time.time()
    
    full_results = []
    
    # 1. Tenta recuperar lista completa do cache
    if cache_key_full in search_cache:
        timestamp, cached_data = search_cache[cache_key_full]
        if current_time - timestamp < 3600:
            logging.info("Cache hit for full list (v8)")
            full_results = cached_data
            
    # 2. Se não estiver em cache, faz scraping
    if not full_results:
        logging.info("Fetching FULL series list form URL (v8)...")
        url = "https://assistir.app/series-todas"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"}
        
        async with SafeAsyncClient(follow_redirects=True) as client:
            try:
                logging.info(f"Requesting {url}")
                response = await client.get(url, headers=headers, timeout=30.0)
                
                if response.status_code != 200:
                    logging.error(f"Status error: {response.status_code}")
                    return {"items": [], "page": page, "has_more": False, "error": f"Status {response.status_code}"}
                
                soup = BeautifulSoup(response.text, 'html.parser')
                cards = soup.find_all('div', class_='card')
                
                logging.info(f"Items found in full list: {len(cards)}")
                
                for card in cards:
                    try:
                        title_tag = card.find('h3', class_='card__title')
                        if not title_tag: continue
                        
                        link_tag = title_tag.find('a') or card.find('a', class_='card__play')
                        if not link_tag:
                             link_tag = card.find('a', href=True)
                        
                        if not link_tag: continue
                            
                        name = title_tag.get_text().strip()
                        path = link_tag['href']
                        
                        cat_tag = card.find('span', class_='card__category')
                        info_text = cat_tag.get_text().strip() if cat_tag else ""
                        
                        year = ""
                        if info_text:
                            m = re.search(r'(\d{4})', info_text)
                            if m: year = m.group(1)
                        
                        slug = path.split('/')[-1]
                        
                        rate_tag = card.find('span', class_='card__rate')
                        rate = rate_tag.get_text().strip() if rate_tag else ""
                        
                        # Extrai Tag de Novos Episodios ou Qualidade
                        tag_text = ""
                        tag_elem = card.find('div', class_='tags-top') or card.find('span', class_='tag-hd') or card.find('span', class_='card__new')
                        if tag_elem:
                            tag_text = tag_elem.get_text().strip()
                        
                        full_results.append({
                            "nome": name,
                            "slug": slug,
                            "ano": year,
                            "tipo": "serie", 
                            "info": info_text,
                            "nota": rate,
                            "tag": tag_text,
                            "capa_original": f"https://assistir.app/capas/{slug}.jpg"
                        })
                    except: continue
                
                if full_results:
                    # Ordena: NOVOS EPS primeiro, depois outras tags, depois sem tag
                    def get_sort_priority(item):
                        t = item.get("tag", "").upper()
                        if "NOVOS EPS" in t: return 0
                        if t: return 1
                        return 2
                    
                    full_results.sort(key=get_sort_priority)
                    
                    search_cache[cache_key_full] = (current_time, full_results)
                    logging.info(f"Cached {len(full_results)} series in memory (sorted by tag).")
                    
            except Exception as e:
                logging.error(f"Erro scraping full series: {e}")
                return {"items": [], "page": page, "has_more": False, "error": str(e)}


    # 3. Paginação em Memória
    total_items = len(full_results)
    per_page = 24
    start = (page - 1) * per_page
    end = start + per_page
    
    page_items = full_results[start:end]
    has_more = end < total_items
    
    logging.info(f"Serving page {page}: items {start} to {end} (total {total_items})")

    # 4. Enriquecimento apenas dos itens da página
    async with SafeAsyncClient(follow_redirects=True) as client:
        async def enrich_item(item):
            new_item = item.copy()
            try:
                current_key = get_random_tmdb_key()
                tmdb_params = {
                    "api_key": current_key,
                    "query": new_item["nome"],
                    "language": "pt-BR",
                    "include_adult": "false"
                }
                if new_item["ano"]: tmdb_params["first_air_date_year"] = new_item["ano"]
                
                res = await client.get("https://api.themoviedb.org/3/search/tv", params=tmdb_params, timeout=2.0)
                if res.status_code == 200:
                    data = res.json()
                    if data.get("results"):
                        for r in data["results"]:
                            if r.get("poster_path"):
                                new_item["capa"] = f"https://image.tmdb.org/t/p/w500{r['poster_path']}"
                                if r.get("vote_average"):
                                    new_item["nota"] = str(round(r["vote_average"], 1))
                                break
            except: pass
            
            if "capa" not in new_item:
                new_item["capa"] = new_item.get("capa_original", "")
            return new_item

        tasks = [enrich_item(item) for item in page_items]
        enriched_page_items = await asyncio.gather(*tasks)

    return {
        "items": enriched_page_items,
        "page": page,
        "has_more": has_more,
        "total": total_items
    }


@app.get("/api/serie/{slug}")
async def get_serie_details(slug: str):
    """
    Busca detalhes de uma série incluindo lista de temporadas.
    """
    from bs4 import BeautifulSoup
    import re
    
    url = f"https://assistir.app/iframe/{slug}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    async with SafeAsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
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
            
            # Backdrop
            backdrop = ""
            backdrop_div = soup.find('div', class_='backdrop--bg')
            if backdrop_div:
                backdrop = backdrop_div.get('data-bg', '')
                if backdrop.startswith('//'):
                    backdrop = 'https:' + backdrop
            
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
                
                temporadas.append({
                    "numero": temp_num,
                    "titulo": temp_title,
                    "poster": temp_poster,
                    "link": temp_link
                })
            
            temporadas.sort(key=lambda x: x["numero"])
            
            # TMDB Enrichment
            current_key = get_random_tmdb_key()
            tmdb_data = {}
            try:
                tmdb_params = {"api_key": current_key, "query": name_only, "language": "pt-BR"}
                if year:
                    tmdb_params["first_air_date_year"] = year
                
                tmdb_res = await client.get("https://api.themoviedb.org/3/search/tv", params=tmdb_params, timeout=3.0)
                if tmdb_res.status_code == 200:
                    results = tmdb_res.json().get("results", [])
                    if results:
                        tmdb_data = results[0]
                        if tmdb_data.get("id"):
                            details_url = f"https://api.themoviedb.org/3/tv/{tmdb_data['id']}"
                            details_params = {"api_key": current_key, "language": "pt-BR", "append_to_response": "videos,credits"}
                            details_res = await client.get(details_url, params=details_params, timeout=3.0)
                            if details_res.status_code == 200:
                                tmdb_data.update(details_res.json())
            except:
                pass
            
            return {
                "title": title,
                "name": name_only,
                "slug": slug,
                "synopsis": tmdb_data.get("overview") or synopsis,
                "year": year or (tmdb_data.get("first_air_date", "")[:4] if tmdb_data else ""),
                "rating": float(rating) if rating else tmdb_data.get("vote_average", 0),
                "poster": f"https://image.tmdb.org/t/p/w500{tmdb_data['poster_path']}" if tmdb_data.get("poster_path") else "",
                "backdrop": f"https://image.tmdb.org/t/p/original{tmdb_data['backdrop_path']}" if tmdb_data.get("backdrop_path") else backdrop,
                "genres": [g["name"] for g in tmdb_data.get("genres", [])] if tmdb_data.get("genres") else [],
                "temporadas": temporadas,
                "total_temporadas": len(temporadas),
                "id_tmdb": tmdb_data.get("id"),
                "status": tmdb_data.get("status", ""),
                "trailer": next((f"https://www.youtube.com/embed/{v['key']}" for v in tmdb_data.get("videos", {}).get("results", []) if v.get("site") == "YouTube" and v.get("type") == "Trailer"), None),
                "cast": [{"id": p.get("id"), "name": p.get("name"), "character": p.get("character"), "photo": f"https://image.tmdb.org/t/p/w200{p.get('profile_path')}" if p.get("profile_path") else None} for p in tmdb_data.get("credits", {}).get("cast", [])[:12]]
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/serie/{slug}/temporada/{num}")
async def get_serie_temporada(slug: str, num: int):
    """Busca episódios de uma temporada específica."""
    from bs4 import BeautifulSoup
    import re
    
    url = f"https://assistir.app/serie/{slug}/temporada-{num}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    async with SafeAsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            if response.status_code != 200:
                raise HTTPException(status_code=404, detail="Temporada não encontrada")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            h1 = soup.find('h1', class_='section__title')
            title = h1.get_text().strip() if h1 else f"{slug.replace('-', ' ').title()} - Temporada {num}"
            
            synopsis = ""
            desc_div = soup.find('div', class_='card__description')
            if desc_div:
                synopsis = desc_div.get_text().strip()
            
            poster = ""
            poster_div = soup.find('div', class_='card__cover')
            if poster_div:
                img = poster_div.find('img')
                if img:
                    poster = img.get('data-src') or img.get('src') or ""
                    if poster.startswith('//'):
                        poster = 'https:' + poster
            
            rating = ""
            rate_tag = soup.find('span', class_='card__rate')
            if rate_tag:
                rating = rate_tag.get_text().strip()
            
            episodios = []
            accordion = soup.find('div', class_='accordion')
            if accordion:
                table = accordion.find('table', class_='accordion__list')
                if table:
                    tbody = table.find('tbody')
                    if tbody:
                        rows = tbody.find_all('tr')
                        for row in rows:
                            try:
                                onclick = row.get('onclick', '')
                                match = re.search(r"reloadVideoSerie\((\d+),\s*'([^']+)'\)", onclick)
                                if match:
                                    ep_num = int(match.group(1))
                                    ep_hash = match.group(2)
                                    ths = row.find_all('th')
                                    ep_title = ths[-1].get_text().strip() if ths else f"Episódio {ep_num}"
                                    episodios.append({"numero": ep_num, "titulo": ep_title, "hash": ep_hash})
                            except:
                                continue
            
            episodios.sort(key=lambda x: x["numero"])
            
            backdrop = ""
            backdrop_div = soup.find('div', class_='backdrop--bg')
            if backdrop_div:
                backdrop = backdrop_div.get('data-bg', '')
                if backdrop.startswith('//'):
                    backdrop = 'https:' + backdrop
            
            return {
                "title": title, "slug": slug, "temporada": num, "synopsis": synopsis,
                "poster": poster, "rating": float(rating) if rating else 0,
                "backdrop": backdrop, "episodios": episodios, "total_episodios": len(episodios)
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/serie/{slug}/temporada/{num}/episodio/{ep}")
async def get_serie_episodio(slug: str, num: int, ep: int):
    """Busca o player de um episódio específico."""
    from bs4 import BeautifulSoup
    import re
    
    url = f"https://assistir.app/serie/{slug}/temporada-{num}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    async with SafeAsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            if response.status_code != 200:
                raise HTTPException(status_code=404, detail="Temporada não encontrada")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            ep_hash = None
            ep_title = f"Episódio {ep}"
            accordion = soup.find('div', class_='accordion')
            if accordion:
                table = accordion.find('table', class_='accordion__list')
                if table:
                    tbody = table.find('tbody')
                    if tbody:
                        rows = tbody.find_all('tr')
                        for row in rows:
                            onclick = row.get('onclick', '')
                            match = re.search(r"reloadVideoSerie\((\d+),\s*'([^']+)'\)", onclick)
                            if match and int(match.group(1)) == ep:
                                ep_hash = match.group(2)
                                ths = row.find_all('th')
                                if ths:
                                    ep_title = ths[-1].get_text().strip()
                                break
            
            if not ep_hash:
                raise HTTPException(status_code=404, detail="Episódio não encontrado")
            
            iframe_url = f"https://assistir.app/iframe/{ep_hash}/{ep}"
            
            return {
                "slug": slug, "temporada": num, "episodio": ep, "titulo": ep_title,
                "hash": ep_hash, "player_url": iframe_url,
                "players": [{"label": "Player 1", "url": iframe_url}]
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/filmes/all")
async def get_filmes_all(page: int = 1):
    """
    Lista todos os filmes do assistir.app via in-memory pagination.
    Busca de TODAS as categorias e combina os resultados (sem duplicatas).
    """
    from bs4 import BeautifulSoup
    import re
    import logging
    
    logging.basicConfig(filename='backend_debug.log', level=logging.INFO, format='%(asctime)s - %(message)s')
    logging.info(f"Start get_filmes_all page={page}")
    
    # Cache key para a lista COMPLETA de filmes
    cache_key_full = "filmes_all_full_list_v3_multi_cat"
    current_time = time.time()
    
    full_results = []
    
    # 1. Tenta recuperar lista completa do cache
    if cache_key_full in search_cache:
        timestamp, cached_data = search_cache[cache_key_full]
        if current_time - timestamp < 3600:  # 1 hora de cache
            logging.info("Cache hit for full filmes list (multi-category)")
            full_results = cached_data
            
    # 2. Se não estiver em cache, faz scraping de TODAS as categorias
    if not full_results:
        logging.info("Fetching filmes from ALL categories...")
        
        # Lista de todas as categorias disponíveis
        categorias = [
            "acao", "animacao", "aventura", "comedia", "crime",
            "documentario", "drama", "familia", "fantasia", "faroeste",
            "ficcao-cientifica", "guerra", "historia", "misterio",
            "romance", "terror", "thriller"
        ]
        
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"}
        
        # Dicionário para evitar duplicatas (slug -> item)
        filmes_dict = {}
        
        async with SafeAsyncClient(follow_redirects=True) as client:
            # Busca todas as categorias em paralelo para ser mais rápido
            async def fetch_categoria(cat):
                try:
                    url = f"https://assistir.app/categoria/{cat}"
                    response = await client.get(url, headers=headers, timeout=30.0)
                    if response.status_code != 200:
                        return []
                    
                    soup = BeautifulSoup(response.text, 'html.parser')
                    cards = soup.find_all('div', class_='card')
                    
                    items = []
                    for card in cards:
                        try:
                            # O slug está no id do card
                            slug = card.get('id', '')
                            if not slug:
                                continue
                            
                            # Verifica se é filme pelo link (não série)
                            link = card.find('a', class_='card__play')
                            if link:
                                href = link.get('href', '')
                                if '/serie/' in href:
                                    continue  # Pula séries
                            
                            # Título está no h3.card__title
                            title_tag = card.find('h3', class_='card__title')
                            name = title_tag.get_text().strip() if title_tag else slug.replace('-', ' ').title()
                            
                            # Categoria e ano
                            cat_tag = card.find('span', class_='card__category')
                            info_text = cat_tag.get_text().strip() if cat_tag else ""
                            
                            # Extrai o ano
                            year = ""
                            year_span = card.find('span', class_='span-year')
                            if year_span:
                                year = year_span.get_text().strip()
                            elif info_text:
                                m = re.search(r'(\d{4})', info_text)
                                if m: year = m.group(1)
                            
                            # Nota
                            rate_tag = card.find('span', class_='card__rate')
                            rate = rate_tag.get_text().strip() if rate_tag else ""
                            
                            # Tag (HD, DUBLADO, etc)
                            tag_text = ""
                            tag_elem = card.find('div', class_='tags-top') or card.find('span', class_='tag-hd')
                            if tag_elem:
                                tag_text = tag_elem.get_text().strip()
                            
                            # Poster original do site
                            poster_url = ""
                            img = card.find('img')
                            if img:
                                poster_url = img.get('data-src') or img.get('src') or ""
                                if poster_url.startswith('//'):
                                    poster_url = 'https:' + poster_url
                            
                            items.append({
                                "nome": name,
                                "slug": slug,
                                "ano": year,
                                "tipo": "filme", 
                                "info": info_text,
                                "nota": rate,
                                "tag": tag_text,
                                "capa_original": poster_url or f"https://assistir.app/capas/{slug}.jpg"
                            })
                        except: continue
                    
                    return items
                except Exception as e:
                    logging.error(f"Erro ao buscar categoria {cat}: {e}")
                    return []
            
            # Executa todas as buscas em paralelo
            tasks = [fetch_categoria(cat) for cat in categorias]
            results = await asyncio.gather(*tasks)
            
            # Combina resultados removendo duplicatas
            for items in results:
                for item in items:
                    slug = item["slug"]
                    if slug not in filmes_dict:
                        filmes_dict[slug] = item
            
            full_results = list(filmes_dict.values())
            logging.info(f"Total unique filmes from all categories: {len(full_results)}")
            
            # Ordena por ano (mais recentes primeiro) e nota
            def sort_key(item):
                year = item.get("ano", "0")
                try:
                    year_int = int(year) if year else 0
                except:
                    year_int = 0
                
                nota = item.get("nota", "0")
                try:
                    nota_float = float(nota) if nota else 0
                except:
                    nota_float = 0
                
                return (-year_int, -nota_float)
            
            full_results.sort(key=sort_key)
            
            if full_results:
                search_cache[cache_key_full] = (current_time, full_results)
                logging.info(f"Cached {len(full_results)} filmes in memory (multi-category).")


    # 3. Paginação em Memória
    total_items = len(full_results)
    per_page = 24
    start = (page - 1) * per_page
    end = start + per_page
    
    page_items = full_results[start:end]
    has_more = end < total_items
    
    logging.info(f"Serving filmes page {page}: items {start} to {end} (total {total_items})")

    # 4. Enriquecimento apenas dos itens da página com TMDB
    async with SafeAsyncClient(follow_redirects=True) as client:
        async def enrich_item(item):
            new_item = item.copy()
            try:
                current_key = get_random_tmdb_key()
                tmdb_params = {
                    "api_key": current_key,
                    "query": new_item["nome"],
                    "language": "pt-BR",
                    "include_adult": "false"
                }
                if new_item["ano"]: tmdb_params["year"] = new_item["ano"]
                
                res = await client.get("https://api.themoviedb.org/3/search/movie", params=tmdb_params, timeout=2.0)
                if res.status_code == 200:
                    data = res.json()
                    if data.get("results"):
                        for r in data["results"]:
                            if r.get("poster_path"):
                                new_item["capa"] = f"https://image.tmdb.org/t/p/w500{r['poster_path']}"
                                if r.get("vote_average"):
                                    new_item["nota"] = str(round(r["vote_average"], 1))
                                break
            except: pass
            
            if "capa" not in new_item:
                new_item["capa"] = new_item.get("capa_original", "")
            return new_item

        tasks = [enrich_item(item) for item in page_items]
        enriched_page_items = await asyncio.gather(*tasks)

    return {
        "items": enriched_page_items,
        "page": page,
        "has_more": has_more,
        "total": total_items
    }


# ===============================================================
# WATCH 2GETHER LIVE - WebSocket & REST Endpoints
# ===============================================================

# Global state for transmissions
# transmissions = {
#     "token_abc": {
#         "host_id": "google_123",
#         "title": "Movie Title",
#         "participants": {
#             "google_123": { "name": "Host", "avatar": "...", "ws": <WebSocket object> },
#             "google_456": { "name": "Guest 1", "avatar": "...", "ws": <WebSocket object> }
#         }
#     }
# }
transmissions = {}

class TransmissionManager:
    def __init__(self):
        self.active_transmissions = {}
        self.sid_to_user = {} # sid -> (token, user_id)

    def create(self, host_id: str, host_info: dict, media_title: str):
        token = str(uuid.uuid4())
        self.active_transmissions[token] = {
            "host_id": host_id,
            "title": media_title,
            "status": "playing", # playing, paused
            "current_time": 0.0,
            "participants": {
                host_id: {
                    **host_info,
                    "sid": None,
                    "role": "host"
                }
            }
        }
        return token

    def join(self, token: str, user_id: str, user_info: dict):
        if token not in self.active_transmissions:
            return False
        
        transmission = self.active_transmissions[token]
        role = "host" if transmission["host_id"] == user_id else "guest"
        
        if user_id not in transmission["participants"]:
            # Limit max 10 participants
            if len(transmission["participants"]) >= 10:
                print(f"Room {token} is full.")
                return False
                
            transmission["participants"][user_id] = {
                **user_info,
                "sid": None,
                "role": role
            }
        return True

    async def connect(self, sid, token: str, user_id: str):
        # Normalização do token para TV Link (Pareamento por Código)
        # Se for um sender, ele deve cair na mesma sala do receiver
        room_token = token.replace('sender_', '')
        
        if room_token.startswith('tv_link_'):
            if room_token not in self.active_transmissions:
                # Cria uma sala temporária "fantasma" para o pareamento
                self.active_transmissions[room_token] = {
                    "host_id": user_id,
                    "title": "TV Link Room",
                    "status": "waiting",
                    "current_time": 0.0,
                    "participants": {}
                }
            
            # Adiciona participante
            if user_id not in self.active_transmissions[room_token]["participants"]:
                self.active_transmissions[room_token]["participants"][user_id] = {
                    "name": "TV Receiver" if "receiver" in user_id else "Controller",
                    "picture": "",
                    "sid": sid,
                    "role": "host"
                }
            else:
                self.active_transmissions[room_token]["participants"][user_id]["sid"] = sid

            self.sid_to_user[sid] = (room_token, user_id)
            await sio.enter_room(sid, room_token)
            logger.info(f"SIO TV-Link Connect: {user_id} na sala {room_token}")
            return True

        if token in self.active_transmissions:
            if user_id in self.active_transmissions[token]["participants"]:
                self.active_transmissions[token]["participants"][user_id]["sid"] = sid
                self.sid_to_user[sid] = (token, user_id)
                await sio.enter_room(sid, token)
                await self.broadcast_state(token)
                logger.info(f"SIO Connect Success: {user_id} na sala {token}")
                return True
            else:
                logger.warning(f"SIO Connect Error: Usuário {user_id} não encontrado na sala {token}.")
        else:
            logger.warning(f"SIO Connect Error: Sala {token} não existe.")
        return False

    async def disconnect(self, sid):
        if sid in self.sid_to_user:
            token, user_id = self.sid_to_user[sid]
            del self.sid_to_user[sid]
            
            if token in self.active_transmissions:
                parts = self.active_transmissions[token]["participants"]
                if user_id in parts:
                    del parts[user_id]
                    
                    # Se o host saiu ou sala vazia, limpa a sala
                    if user_id == self.active_transmissions[token]["host_id"] or len(parts) == 0:
                        await sio.emit('room_closed', room=token)
                        del self.active_transmissions[token]
                        return "closed"
                    
                    await self.broadcast_state(token)
                    return "leaved"
        return "not_found"

    async def broadcast_state(self, token: str):
        if token not in self.active_transmissions:
            return
            
        t = self.active_transmissions[token]
        parts_data = []
        for uid, p in t["participants"].items():
            parts_data.append({
                "id": uid,
                "name": p.get("name", "Unknown"),
                "avatar": p.get("picture", ""),
                "role": p.get("role", "guest")
            })
            
        msg = {
            "type": "state",
            "participants": parts_data,
            "host_id": t["host_id"],
            "title": t["title"]
        }
        await sio.emit('state', msg, room=token)

manager = TransmissionManager()

@sio.event
async def connect(sid, environ):
    # Tenta obter query params dos headers do Socket.io se disponíveis, 
    # senão faz o parsing manual da QUERY_STRING
    query = environ.get('QUERY_STRING', '')
    from urllib.parse import parse_qs
    params = {k: v[0] for k, v in parse_qs(query).items()}
    
    token = params.get('token')
    user_id = params.get('user_id')
    
    if not token or not user_id:
        logger.warning(f"Connection rejected: missing token or user_id in {params}")
        return False
        
    success = await manager.connect(sid, token, user_id)
    return success

@sio.event
async def disconnect(sid):
    await manager.disconnect(sid)

@sio.on('sync_command')
async def on_sync_command(sid, data):
    if sid not in manager.sid_to_user: return
    token, user_id = manager.sid_to_user[sid]
    
    if token in manager.active_transmissions:
        if manager.active_transmissions[token]["host_id"] == user_id or data.get('type') == 'user_mute_status':
            # Broadcast para todos na sala exceto quem enviou
            await sio.emit('sync_command', data, room=token, skip_sid=sid)

@sio.on('signal')
async def on_signal(sid, data):
    if sid not in manager.sid_to_user: return
    token, user_id = manager.sid_to_user[sid]
    
    target_id = data.get("target")
    if target_id and token in manager.active_transmissions:
        target_info = manager.active_transmissions[token]["participants"].get(target_id)
        if target_info and target_info["sid"]:
            await sio.emit('signal', {
                "from": user_id,
                "signalData": data.get("signalData")
            }, room=target_info["sid"])

@sio.on('guest_ready')
async def on_guest_ready(sid, data):
    if sid not in manager.sid_to_user: return
    token, user_id = manager.sid_to_user[sid]
    
    if token in manager.active_transmissions:
        host_id = manager.active_transmissions[token]["host_id"]
        host_info = manager.active_transmissions[token]["participants"].get(host_id)
        if host_info and host_info["sid"]:
            await sio.emit('guest_ready', {"user_id": user_id}, room=host_info["sid"])

# Final app setup: Wrap FastAPI with Socket.io
app = socketio.ASGIApp(sio, other_asgi_app=app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
