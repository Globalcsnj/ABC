"""Generate a self-signed TLS certificate so phones can use the camera over WiFi.

Browsers only allow camera access on https:// (or localhost). This creates a
local self-signed cert covering localhost + the PC's LAN IP. Returns
(cert_path, key_path) or (None, None) if the cryptography library isn't available.
"""
import os
import socket
import datetime

CERT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "certs")


def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def ensure_cert():
    cert_path = os.path.join(CERT_DIR, "cert.pem")
    key_path = os.path.join(CERT_DIR, "key.pem")
    ip = get_lan_ip()
    ip_file = os.path.join(CERT_DIR, "ip.txt")

    # Regenerate if the LAN IP changed (so the cert still covers this machine)
    prev_ip = ""
    if os.path.exists(ip_file):
        try:
            prev_ip = open(ip_file).read().strip()
        except Exception:
            prev_ip = ""

    if os.path.exists(cert_path) and os.path.exists(key_path) and prev_ip == ip:
        return cert_path, key_path

    try:
        return _generate(cert_path, key_path, ip, ip_file)
    except BaseException as e:  # includes pyo3 PanicException when lib is broken
        print(f"[certs] HTTPS unavailable ({type(e).__name__}); falling back to HTTP.")
        return None, None


def _generate(cert_path, key_path, ip, ip_file):
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    import ipaddress

    os.makedirs(CERT_DIR, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ABC Inventory")])
    alt_names = [x509.DNSName("localhost")]
    for candidate in ("127.0.0.1", ip):
        try:
            alt_names.append(x509.IPAddress(ipaddress.ip_address(candidate)))
        except ValueError:
            pass

    now = datetime.datetime.utcnow()
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
        .sign(key, hashes.SHA256())
    )

    with open(key_path, "wb") as f:
        f.write(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ))
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(ip_file, "w") as f:
        f.write(ip)
    return cert_path, key_path
