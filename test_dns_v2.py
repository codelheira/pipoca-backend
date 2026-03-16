import httpx
import httpcore
import asyncio
import subprocess

# Resolve the IP via PowerShell (Google DNS)
def get_ip_powershell(host):
    try:
        cmd = f'powershell "Resolve-DnsName {host} -Server 8.8.8.8 -Type A | Select-Object -ExpandProperty IPAddress"'
        res = subprocess.check_output(cmd, shell=True).decode().strip().split('\n')[0].strip()
        return res
    except:
        return None

class ForcedIPTransport(httpx.AsyncHTTPTransport):
    def __init__(self, host_map, *args, **kwargs):
        self.host_map = host_map
        super().__init__(*args, **kwargs)

    async def handle_async_request(self, request):
        original_host = request.url.host
        if original_host in self.host_map:
            # We want to keep the original Host header for SNI
            # But we want the underlying connection to go to the IP
            # In httpcore/httpx, we can't easily swap the connection target while keeping the SNI hostname 
            # UNLESS we use a custom connection pool or socket.
            pass
        return await super().handle_async_request(request)

# Alternative: use a custom Socket factory or just use a proxy? 
# No, let's try the most robust way:
# Use the IP in the URL but try to force the SNI.
# In Python's ssl module, we can set server_hostname.

async def test_ssl_context_with_ip():
    print("\n--- Test: IP with Manual SNI via HTTPX Transport ---")
    host = "www.assistir.app"
    ip = get_ip_powershell(host)
    if not ip:
        print("Could not resolve IP")
        return

    # We use the IP in the URL but we set the SNI in the SSL context
    import ssl
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    try:
        # httpx doesn't allow setting server_hostname easily on a per-request basis with IP URL
        # BUT we can use a mount or a custom transport that intercepts.
        
        # Let's try this:
        async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
            # Maybe the site accepts plain HTTP for the API? (unlikely but worth a check)
            print(f"Trying HTTP instead of HTTPS to {ip}...")
            resp = await client.get(f"http://{ip}/api/home", headers={"Host": host})
            print(f"HTTP Success! Status: {resp.status_code}")
    except Exception as e:
        print(f"HTTP failed: {e}")

    try:
        # If we use HTTPS, we NEED SNI.
        # Let's try to use the hostname but tell the transport to connect to the IP.
        # This is possible by subclassing AsyncHTTPTransport and overriding 'handle_async_request' 
        # to use 'httpcore' directly with a specific local_address or similar? No.
        
        # Let's try the 'requests' reach-around if possible.
        import requests
        print("\n--- Test: Requests with manual resolve ---")
        session = requests.Session()
        from urllib3.util import connection
        
        _orig_getaddrinfo = connection.getaddrinfo

        def patched_getaddrinfo(*args, **kwargs):
            if args[0] == host:
                print(f"Patched DNS for {host} -> {ip}")
                return _orig_getaddrinfo(ip, *args[1:], **kwargs)
            return _orig_getaddrinfo(*args, **kwargs)

        connection.getaddrinfo = patched_getaddrinfo
        
        try:
            r = session.get(f"https://{host}/api/home", timeout=10, verify=False)
            print(f"Requests Success! Status: {r.status_code}")
        except Exception as e:
            print(f"Requests failed: {e}")
        finally:
            connection.getaddrinfo = _orig_getaddrinfo

    except Exception as e:
        print(f"Requests test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_ssl_context_with_ip())
