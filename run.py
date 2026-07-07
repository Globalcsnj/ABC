import uvicorn
from app.certs import ensure_cert, get_lan_ip

if __name__ == "__main__":
    cert_path, key_path = ensure_cert()
    ip = get_lan_ip()
    if cert_path and key_path:
        print("=" * 56)
        print("  ABC Inventory running with HTTPS (camera works on phones)")
        print(f"  On this PC:   https://localhost:8000")
        print(f"  On a phone:   https://{ip}:8000   (same WiFi)")
        print("  First visit shows a 'not secure' warning — click")
        print("  Advanced -> Proceed. It's your own local certificate.")
        print("=" * 56)
        uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True,
                    ssl_certfile=cert_path, ssl_keyfile=key_path)
    else:
        print("=" * 56)
        print("  ABC Inventory running with HTTP (no HTTPS certificate).")
        print(f"  On this PC:   http://localhost:8000")
        print("  Phone camera needs HTTPS; install dependencies to enable it:")
        print("    pip install -r requirements.txt")
        print("=" * 56)
        uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
