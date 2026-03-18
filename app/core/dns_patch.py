import socket
import time
import re
import subprocess
import logging

logger = logging.getLogger("pipoca-api")

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
            cmd = f'powershell "Resolve-DnsName {host} -Server 8.8.8.8 -Type A | Select-Object -ExpandProperty IPAddress"'
            res = subprocess.check_output(cmd, shell=True).decode().strip().split('\n')[0].strip()
            if res and re.match(r"^\d{1,3}(\.\d{1,3}){3}$", res):
                 logger.debug(f"DNS Fallback: {host} -> {res}")
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

def apply_dns_patch():
    """Aplica patch global no socket para contornar bloqueios de DNS."""
    socket.getaddrinfo = patched_getaddrinfo
    logger.info("DNS Patch applied for proxy providers.")
