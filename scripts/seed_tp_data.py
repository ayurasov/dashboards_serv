#!/usr/bin/env python3
"""
One-time seed script: reads tp-report/seed_data.json and POSTs it to
the unified backend via the /api/tp/rows/bulk_import endpoint.

Usage:
    python scripts/seed_tp_data.py [--url http://localhost:8000] [--token <JWT>]

The JWT token of an admin user is required (use /api/auth/login first).
If --token is omitted the script will prompt for it.
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / 'tp-report' / 'seed_data.json'


def main():
    parser = argparse.ArgumentParser(description='Seed TP data into unified backend')
    parser.add_argument('--url',   default='http://localhost:8000', help='Backend base URL')
    parser.add_argument('--token', default='', help='Admin JWT access token')
    args = parser.parse_args()

    token = args.token.strip()
    if not token:
        token = input('Enter admin JWT token: ').strip()
    if not token:
        print('Token is required.', file=sys.stderr)
        sys.exit(1)

    if not SEED.exists():
        print(f'Seed file not found: {SEED}', file=sys.stderr)
        sys.exit(1)

    with open(SEED, encoding='utf-8') as f:
        rows = json.load(f)

    print(f'Loaded {len(rows)} rows from {SEED}')

    payload = json.dumps({'rows': rows}).encode('utf-8')
    url = f"{args.url.rstrip('/')}/api/tp/rows/bulk_import"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}',
        },
        method='POST',
    )

    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            print(f'Done: {result}')
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f'HTTP {e.code}: {body}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
