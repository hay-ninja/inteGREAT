"""Generate a demo-only local CA and LAN HTTPS certificate. Never installs trust automatically."""
import argparse
import ipaddress
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", required=True, help="Laptop's LAN IPv4 address")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / ".phone-camera")
    args = parser.parse_args()
    ip = ipaddress.ip_address(args.ip)
    if ip.version != 4 or not any(ip in ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")):
        parser.error("Use a private LAN IPv4 address")
    if args.out.exists():
        parser.error("Output directory already exists; choose a new --out directory to avoid overwriting keys")
    args.out.mkdir(parents=True)
    now = datetime.now(UTC)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "inteGREAT local phone camera demo CA")])
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=7)).add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
        .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), True)
        .sign(ca_key, hashes.SHA256()))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, str(ip))]))
        .issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=7))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip)]), False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
        .sign(ca_key, hashes.SHA256()))
    (args.out / "root-ca.cer").write_bytes(ca.public_bytes(serialization.Encoding.DER))
    (args.out / "server.pem").write_bytes(leaf.public_bytes(serialization.Encoding.PEM) + ca.public_bytes(serialization.Encoding.PEM))
    (args.out / "server-key.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    # CA signing key deliberately not saved; this CA cannot issue additional certificates.
    print(f"Created demo certificate for {ip} in {args.out}. Transfer ONLY root-ca.cer to your iPhone.")
    print("Install and explicitly trust the CA on iPhone. Remove the profile after the demo. See docs/phone-camera.md.")


if __name__ == "__main__":
    main()
