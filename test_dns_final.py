import socket
import httpx
import asyncio
import subprocess

def get_ip_powershell(host):
    try:
        cmd = f'powershell "Resolve-DnsName {host} -Server 8.8.8.8 -Type A | Select-Object -ExpandProperty IPAddress"'
        res = subprocess.check_output(cmd, shell=True).decode().strip().split('\n')[0].strip()
        return res
    except:
        return None

_original_getaddrinfo = socket.getaddrinfo

def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    # Handle both string and bytes
    h = host.decode() if isinstance(host, bytes) else host
    
    if h in ["assistir.app", "www.assistir.app"]:
        resolved_ip = get_ip_powershell(h)
        if resolved_ip:
            # print(f"Redirecting {h} -> {resolved_ip}")
            return _original_getaddrinfo(resolved_ip, port, family, type, proto, flags)
    return _original_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = patched_getaddrinfo

async def main():
    print("--- Final Global Patch Test ---")
    try:
        async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
            resp = await client.get("https://www.assistir.app/api/home")
            print(f"Status: {resp.status_code}")
            if resp.status_code == 200:
                print("DATA FETCHED SUCCESSFULLY!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
