import httpx
import socket
import subprocess
import re
import asyncio

async def test_standard():
    print("\n--- Test 1: Standard httpx ---")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://www.assistir.app")
            print(f"Success! Status: {resp.status_code}")
    except Exception as e:
        print(f"Failed: {e}")

async def test_no_verify():
    print("\n--- Test 2: httpx verify=False ---")
    try:
        async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
            resp = await client.get("https://www.assistir.app")
            print(f"Success! Status: {resp.status_code}")
    except Exception as e:
        print(f"Failed: {e}")

def get_ip_powershell(host):
    print(f"\n--- Test 3: PowerShell DNS (8.8.8.8) ---")
    try:
        cmd = f'powershell "Resolve-DnsName {host} -Server 8.8.8.8 -Type A | Select-Object -ExpandProperty IPAddress"'
        res = subprocess.check_output(cmd, shell=True).decode().strip().split('\n')[0].strip()
        print(f"PowerShell result for {host}: {res}")
        return res
    except Exception as e:
        print(f"PowerShell failed: {e}")
        return None

async def test_ip_direct(ip, host):
    print(f"\n--- Test 4: Direct IP ({ip}) with Host Header ({host}) ---")
    try:
        async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
            resp = await client.get(f"https://{ip}/", headers={"Host": host})
            print(f"Success! Status: {resp.status_code}")
            # print(resp.text[:200])
    except Exception as e:
        print(f"Direct IP failed: {e}")

async def main():
    await test_standard()
    await test_no_verify()
    ip = get_ip_powershell("www.assistir.app")
    if ip:
        await test_ip_direct(ip, "www.assistir.app")
    
    # Try another IP if first is suspicious
    ip2 = get_ip_powershell("assistir.app")
    if ip2:
        await test_ip_direct(ip2, "assistir.app")

if __name__ == "__main__":
    asyncio.run(main())
