"""One-shot script: import tp-report/seed_data.json into the main database.

Usage (from repo root):
    python -m backend.scripts.import_tp_seed

Or with a custom path:
    python -m backend.scripts.import_tp_seed --seed tp-report/seed_data.json

The script calls the running FastAPI service via HTTP, so the backend must be up:
    uvicorn backend.app.main:app ...

Authenticate with --url, --user, --password (defaults: localhost:8000, admin, admin).
"""
import argparse
import json
import sys
import httpx
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Import TP seed data")
    parser.add_argument("--seed", default="tp-report/seed_data.json",
                        help="Path to seed_data.json")
    parser.add_argument("--url", default="http://localhost:8000",
                        help="Backend base URL")
    parser.add_argument("--user", default="admin", help="Admin username")
    parser.add_argument("--password", default="admin", help="Admin password")
    args = parser.parse_args()

    seed_path = Path(args.seed)
    if not seed_path.exists():
        print(f"❌ Seed file not found: {seed_path}", file=sys.stderr)
        sys.exit(1)

    with open(seed_path, encoding="utf-8") as f:
        rows = json.load(f)

    print(f"ℹ️  Loaded {len(rows)} rows from {seed_path}")

    # Authenticate
    resp = httpx.post(
        f"{args.url}/api/auth/login",
        json={"username": args.user, "password": args.password},
        timeout=10,
    )
    if resp.status_code != 200:
        print(f"❌ Login failed: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)

    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("✅ Authenticated")

    # Bulk import
    resp = httpx.post(
        f"{args.url}/api/tp/rows/bulk_import",
        json={"rows": rows},
        headers=headers,
        timeout=60,
    )
    if resp.status_code != 200:
        print(f"❌ Import failed: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)

    result = resp.json()
    print(f"✅ Imported {result.get('count', '?')} rows into tp_report_rows")


if __name__ == "__main__":
    main()
