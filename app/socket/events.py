from urllib.parse import parse_qs
import logging
from .manager import manager

logger = logging.getLogger("pipoca-api")

def register_socket_events(sio):
    """Registra todos os handlers de eventos do Socket.io."""

    @sio.event
    async def connect(sid, environ):
        query = environ.get('QUERY_STRING', '')
        params = {k: v[0] for k, v in parse_qs(query).items()}
        
        token = params.get('token')
        user_id = params.get('user_id')
        
        if not token or not user_id:
            logger.warning(f"Connection rejected: missing info in {params}")
            return False
            
        # Normalização do token para TV Link (Pareamento por Código)
        room_token = token.replace('sender_', '')
        
        # Lógica de conexão na sala
        transmission = manager.get_transmission(room_token)
        if not transmission and room_token.startswith('tv_link_'):
             # Cria sala fantasma para TV Link
             manager.create(user_id, {"name": "TV Room", "picture": ""}, "TV Link")
             transmission = manager.get_transmission(room_token)

        if room_token in manager.active_transmissions:
            manager.active_transmissions[room_token]["participants"][user_id] = {
                "name": params.get("name", "User"),
                "picture": params.get("picture", ""),
                "sid": sid,
                "role": "host" if manager.active_transmissions[room_token]["host_id"] == user_id else "guest"
            }
            manager.sid_to_user[sid] = (room_token, user_id)
            await sio.enter_room(sid, room_token)
            
            # Broadcast do novo estado
            await broadcast_state(sio, room_token)
            logger.info(f"Socket IO: {user_id} connected to {room_token}")
            return True
        
        return False

    @sio.event
    async def disconnect(sid):
        if sid in manager.sid_to_user:
            room_token, user_id = manager.sid_to_user[sid]
            del manager.sid_to_user[sid]
            
            t = manager.get_transmission(room_token)
            if t and user_id in t["participants"]:
                t["participants"][user_id]["sid"] = None
                
                # Close room if empty
                has_active = any(p.get("sid") is not None for p in t["participants"].values())
                if not has_active:
                    manager.remove_transmission(room_token)
                else:
                    await broadcast_state(sio, room_token)

    @sio.on('sync_command')
    async def on_sync_command(sid, data):
        if sid not in manager.sid_to_user: return
        room_token, user_id = manager.sid_to_user[sid]
        
        t = manager.get_transmission(room_token)
        if t:
            is_host = t["host_id"] == user_id
            is_tv = room_token.startswith('tv_link_')
            
            if is_host or is_tv or data.get('type') == 'user_mute_status':
                await sio.emit('sync_command', data, room=room_token, skip_sid=sid)

    @sio.on('signal')
    async def on_signal(sid, data):
        """WebRTC Signaling for Voice Chat."""
        if sid not in manager.sid_to_user: return
        room_token, user_id = manager.sid_to_user[sid]
        
        target_id = data.get("target")
        t = manager.get_transmission(room_token)
        if t and target_id in t["participants"]:
            target_sid = t["participants"][target_id].get("sid")
            if target_sid:
                await sio.emit('signal', {
                    "from": user_id,
                    "signalData": data.get("signalData")
                }, room=target_sid)

    @sio.on('guest_ready')
    async def on_guest_ready(sid, data):
        if sid not in manager.sid_to_user: return
        room_token, user_id = manager.sid_to_user[sid]
        
        t = manager.get_transmission(room_token)
        if t:
            host_sid = t["participants"].get(t["host_id"], {}).get("sid")
            if host_sid:
                await sio.emit('guest_ready', {"user_id": user_id}, room=host_sid)

async def broadcast_state(sio, room_token: str):
    t = manager.get_transmission(room_token)
    if not t: return
    
    parts_data = []
    for uid, p in t["participants"].items():
        parts_data.append({
            "id": uid,
            "name": p.get("name", "Unknown"),
            "avatar": p.get("picture", ""),
            "role": p.get("role", "guest")
        })
        
    await sio.emit('state', {
        "type": "state",
        "participants": parts_data,
        "host_id": t["host_id"],
        "title": t["title"]
    }, room=room_token)
