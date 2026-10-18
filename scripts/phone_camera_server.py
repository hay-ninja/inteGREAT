"""One shared service: loopback API plus restricted HTTPS phone capture gateway.

Run instead of the usual API process; start the Vite UI separately.
"""
import argparse
import asyncio
import ipaddress
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", required=True, help="Laptop LAN IPv4 address, matching the certificate")
    parser.add_argument("--cert-dir", type=Path, default=ROOT / ".phone-camera")
    args = parser.parse_args()
    ip = ipaddress.ip_address(args.ip)
    if ip.version != 4 or not any(ip in ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")):
        parser.error("Use the laptop's private LAN IPv4 address")
    cert, key = args.cert_dir / "server.pem", args.cert_dir / "server-key.pem"
    if not cert.is_file() or not key.is_file():
        parser.error("Generate certificates first: python scripts/make_phone_cert.py --ip YOUR_LAN_IP")
    import uvicorn
    from integreat.main import create_app
    from integreat.api.phone import create_phone_app
    app = create_app()
    app.state.phone_camera_url = f"https://{ip}:8443"
    phone = create_phone_app(app.state.service.devices.camera)

    async def serve():
        api = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8000))
        gateway = uvicorn.Server(uvicorn.Config(phone, host=str(ip), port=8443,
            ssl_certfile=str(cert), ssl_keyfile=str(key), access_log=False))
        tasks = [asyncio.create_task(api.serve()), asyncio.create_task(gateway.serve())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            api.should_exit = gateway.should_exit = True
            await asyncio.gather(*tasks)
    print(f"Phone gateway: https://{ip}:8443/phone (create a pairing link in Rig setup)")
    asyncio.run(serve())


if __name__ == "__main__":
    main()
