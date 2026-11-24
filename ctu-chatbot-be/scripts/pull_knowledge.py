"""Copy admin knowledge and its vectors from a deployed server to local.

Run: python scripts/pull_knowledge.py https://your-server.example http://127.0.0.1:8000
Both instances must run a version with the knowledge transfer API.
"""

import getpass
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request(url: str, token: str, body: bytes | None = None) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    with urlopen(Request(url, data=body, headers=headers), timeout=120) as response:
        return json.load(response)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    source, target = (url.rstrip("/") + "/api/v1/admin/knowledge/transfer" for url in sys.argv[1:])
    source_token = getpass.getpass("Server admin access token: ")
    target_token = getpass.getpass("Local admin access token: ")
    try:
        snapshot = request(source, source_token)
        result = request(target, target_token, json.dumps(snapshot, ensure_ascii=False, allow_nan=False).encode("utf-8"))
    except (HTTPError, URLError, ValueError) as exc:
        print(f"Sync failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
