from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

from app.core.config import ApiSettings, AppEnvironment
from app.main import create_app


def generated_schema() -> bytes:
    key = base64.b64encode(bytes(32)).decode("ascii")
    settings = ApiSettings(
        APP_ENV=AppEnvironment.TEST,
        DATABASE_URL="postgresql+psycopg://unused:unused@localhost:5432/unused",
        CSRF_HMAC_KEY=key,
        RATE_LIMIT_HMAC_KEY=key,
        PUBLIC_BASE_URL="http://localhost:8080",
        TRUSTED_ORIGINS="http://localhost:8080",
        TRUSTED_HOSTS="localhost,testserver",
        TRUSTED_PROXY_CIDRS="127.0.0.1/32",
        PRIVATE_STORAGE_ROOT="/tmp/clientops-openapi-unused",
    )
    schema = create_app(settings).openapi()
    serialized = json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (serialized + "\n").encode()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", type=Path)
    args = parser.parse_args()
    if bool(args.output) == bool(args.check):
        parser.error("use exatamente um de --output ou --check")
    content = generated_schema()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(content)
        return 0
    if not args.check.is_file() or args.check.read_bytes() != content:
        print(f"OpenAPI desatualizada: {args.check}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
