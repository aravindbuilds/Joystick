import argparse
import datetime as dt
import importlib
import ipaddress
import socket
from pathlib import Path


def detect_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def generate(common_name: str, days: int, ip_address_value: str, out_dir: Path) -> tuple[Path, Path]:
    x509 = importlib.import_module("cryptography.x509")
    hashes = importlib.import_module("cryptography.hazmat.primitives.hashes")
    serialization = importlib.import_module("cryptography.hazmat.primitives.serialization")
    rsa = importlib.import_module("cryptography.hazmat.primitives.asymmetric.rsa")
    NameOID = importlib.import_module("cryptography.x509.oid").NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Joystick Local"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )

    san_entries = [x509.DNSName("localhost")]
    try:
        san_entries.append(x509.IPAddress(ipaddress.ip_address(ip_address_value)))
    except ValueError:
        pass

    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=2))
        .not_valid_after(now + dt.timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .sign(private_key=key, algorithm=hashes.SHA256())
    )

    key_path = out_dir / "key.pem"
    cert_path = out_dir / "cert.pem"

    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    return cert_path, key_path


def main() -> int:
    try:
        importlib.import_module("cryptography")
    except ModuleNotFoundError:
        print("Missing dependency: cryptography")
        print("Run: python -m pip install cryptography")
        return 1

    parser = argparse.ArgumentParser(description="Generate local TLS cert.pem/key.pem for Joystick")
    parser.add_argument("--common-name", default="JoystickLocal")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--ip-address", default=None)
    parser.add_argument("--out-dir", default=".")
    args = parser.parse_args()

    ip_value = args.ip_address or detect_ip()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    cert_path, key_path = generate(args.common_name, args.days, ip_value, out_dir)
    print(f"Generated {cert_path.name} and {key_path.name} in {out_dir}")
    print(f"SAN includes localhost and {ip_value}")
    print(f"Open https://{ip_value}:8443 on your phone")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
