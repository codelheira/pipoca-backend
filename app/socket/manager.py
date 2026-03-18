import uuid
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("pipoca-api")

class TransmissionManager:
    def __init__(self):
        self.active_transmissions = {}
        self.sid_to_user = {} # sid -> (token, user_id)

    def create(self, host_id: str, host_info: dict, media_title: str) -> str:
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

    def join(self, token: str, user_id: str, user_info: dict) -> bool:
        if token not in self.active_transmissions:
            return False
        
        transmission = self.active_transmissions[token]
        role = "host" if transmission["host_id"] == user_id else "guest"
        
        if user_id not in transmission["participants"]:
            if len(transmission["participants"]) >= 10:
                logger.warning(f"Room {token} is full.")
                return False
                
            transmission["participants"][user_id] = {
                **user_info,
                "sid": None,
                "role": role
            }
        return True

    def get_transmission(self, token: str) -> Optional[Dict[str, Any]]:
        return self.active_transmissions.get(token)

    def remove_transmission(self, token: str):
        if token in self.active_transmissions:
            del self.active_transmissions[token]

# Global instance
manager = TransmissionManager()
