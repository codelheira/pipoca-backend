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

# The magic DNS patch
_original_getaddrinfo = socket.getaddrinfo

def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host in ["assistir.app", "www.assistir.app"]:
        resolved_ip = get_ip_powershell(host)
        if resolved_ip:
            print(f"DNS Redirect: {host} -> {resolved_ip}")
            return _original_getaddrinfo(resolved_ip, port, family, type, proto, flags)
    return _original_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = patched_getaddrinfo

async def main():
    print("--- Test: Global Socket Patch ---")
    try:
        # verify=False is still good because we might hit a Cloudflare edge that is sensitive to something else
        # but the hostname (SNI) will be passed correctly because httpx thinks it's connecting to 'www.assistir.app'
        async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
            url = "https://www.assistir.app/api/home"
            print(f"Fetching {url}...")
            resp = await client.get(url)
            print(f"Status: {resp.status_code}")
            if resp.status_code == 200:
                print("SUCCESS!! Data received.")
                # print(resp.text[:100])
            else:
                print(f"Failed with status {resp.status_code}")
                # print(resp.text[:500])
    except Exception as e:
        print(f"Error during request: {e}")

if __name__ == "__main__":
    asyncio.run(main())
