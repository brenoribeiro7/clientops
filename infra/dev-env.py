from __future__ import annotations

import argparse
import base64
import os
import secrets
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
ENV_FILE = LOCAL / "compose.env"
TLS_DIR = LOCAL / "tls"


def token() -> str:
    return secrets.token_urlsafe(32)


def hmac_key() -> str:
    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")


def write_environment(force: bool) -> None:
    LOCAL.mkdir(mode=0o700, exist_ok=True)
    os.chmod(LOCAL, 0o700)
    if ENV_FILE.exists() and not force:
        return
    postgres = token()
    migration = token()
    runtime = token()
    values = {
        "APP_ENV": "development",
        "POSTGRES_PASSWORD": postgres,
        "MIGRATION_DATABASE_PASSWORD": migration,
        "RUNTIME_DATABASE_PASSWORD": runtime,
        "DATABASE_URL": f"postgresql+psycopg://clientops_runtime:{runtime}@db:5432/clientops",
        "MIGRATION_DATABASE_URL": f"postgresql+psycopg://clientops_migrator:{migration}@db:5432/clientops",
        "CSRF_HMAC_KEY": hmac_key(),
        "RATE_LIMIT_HMAC_KEY": hmac_key(),
        "PUBLIC_BASE_URL": "http://localhost:8080",
        "TRUSTED_ORIGINS": "http://localhost:8080",
        "TRUSTED_HOSTS": "localhost,127.0.0.1,api",
        "TRUSTED_PROXY_CIDRS": "172.28.0.2/32",
        "PRIVATE_STORAGE_ROOT": "/var/lib/clientops/private",
        "LOG_LEVEL": "INFO",
    }
    content = "".join(f"{name}={value}\n" for name, value in values.items())
    descriptor = os.open(ENV_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)


def write_tls(force: bool) -> None:
    TLS_DIR.mkdir(mode=0o755, parents=True, exist_ok=True)
    # The outer .local directory remains 0700; this directory must be
    # traversable by the non-root UID after Docker mounts it.
    os.chmod(TLS_DIR, 0o755)
    certificate = TLS_DIR / "certificate.pem"
    private_key = TLS_DIR / "private-key.pem"
    if certificate.exists() and private_key.exists() and not force:
        return
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-sha256",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost,IP:127.0.0.1",
            "-keyout",
            str(private_key),
            "-out",
            str(certificate),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # The containing directory remains 0700 on the host. Read access inside the
    # bind mount is needed by the non-root Nginx test process.
    os.chmod(private_key, 0o644)
    os.chmod(certificate, 0o644)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare local ClientOps development secrets")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--tls", action="store_true")
    args = parser.parse_args()
    write_environment(args.force)
    if args.tls:
        write_tls(args.force)
    print(f"Prepared local configuration in {LOCAL} (secret values omitted).")


if __name__ == "__main__":
    main()
