import socket
import httpx
import asyncio
import subprocess

def get_ip_powershell(host):
    try:
        cmd = f'powershell "Resolve-DnsName {host} -Server 8.8.8.8 -Type A | Select-Object -ExpandProperty IPAddress"'
        res = subprocess.check_output(cmd, shell=True).decode().strip().split('\n')[0].strip()
        return res
    except Exception as e:
        print(f"PS Error: {e}")
        return None

_original_getaddrinfo = socket.getaddrinfo

def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    print(f"Intercepted DNS call for: {host}")
    if host in ["assistir.app", "www.assistir.app"]:
        resolved_ip = get_ip_powershell(host)
        if resolved_ip:
            print(f"DNS Redirecting {host} to {resolved_ip}")
            return _original_getaddrinfo(resolved_ip, port, family, type, proto, flags)
    return _original_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = patched_getaddrinfo

async def main():
    try:
        # TEST 1: Direct socket call
        print("--- Direct Socket Test ---")
        res = socket.getaddrinfo("www.assistir.app", 443)
        print(f"Socket result: {res}")

        # TEST 2: HTTPX
        print("\n--- HTTPX Test ---")
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.get("https://www.assistir.app/api/home")
            print(f"HTTPX Status: {resp.status_code}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
