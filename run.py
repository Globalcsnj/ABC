import uvicorn
from app.certs import get_lan_ip

if __name__ == "__main__":
    ip = get_lan_ip()
    print("=" * 56)
    print("  ABC Inventory running")
    print(f"  On this PC:   http://localhost:8000")
    print(f"  On a phone:   http://{ip}:8000   (same WiFi)")
    print("  Note: phone camera scanning needs HTTPS or localhost, so it")
    print("  won't work over plain HTTP on a phone — use the manual entry")
    print("  option or a USB scanner instead.")
    print("=" * 56)
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
