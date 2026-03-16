import httpx
import asyncio
import socket

# Forçar resolução via Google DNS se o sistema falhar
def resolve_custom(host):
    try:
        return socket.gethostbyname(host)
    except:
        # Tenta via shell (mais garantido no ambiente do user se o python estiver limitado)
        import subprocess
        try:
            cmd = f'powershell "Resolve-DnsName {host} -Server 8.8.8.8 -Type A | Select-Object -ExpandProperty IPAddress"'
            res = subprocess.check_output(cmd, shell=True).decode().strip().split('\n')[0].strip()
            if res: return res
        except:
            pass
    return None

async def test_scraping():
    host = "assistir.app"
    ip = resolve_custom(host)
    print(f"Resolvido {host} -> {ip}")
    
    if not ip:
        print("Falha total na resolução")
        return

    # Se for IPv6, precisa de colchetes
    ip_str = f"[{ip}]" if ":" in ip else ip
    url = f"https://{ip_str}/inicio"
    headers = {
        "Host": host,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    }
    
    async with httpx.AsyncClient(verify=False) as client: # verify=False pois o cert será para o domínio, não IP
        try:
            resp = await client.get(url, headers=headers, timeout=10.0)
            print(f"Status: {resp.status_code}")
            print(f"HTML Length: {len(resp.text)}")
            if "card" in resp.text:
                print("Encontrou cards!")
            else:
                print("Não encontrou cards. Estrutura pode ter mudado.")
                print(resp.text[:500])
        except Exception as e:
            print(f"Erro no scraping: {e}")

if __name__ == "__main__":
    asyncio.run(test_scraping())
