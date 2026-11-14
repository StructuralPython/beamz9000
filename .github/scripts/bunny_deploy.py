"""
Mirrors a built site to a bunny.net Storage Zone, then purges the Pull Zone.

Uploads every file under SITE_DIR, deletes remote files that are no longer in
the build, and purges the CDN cache so the new pages are served at once.
Standard library only, so it runs without installing anything.

Environment:
    BUNNY_STORAGE_ZONE       Storage Zone name.
    BUNNY_STORAGE_PASSWORD   Storage Zone password (FTP & API access).
    BUNNY_STORAGE_HOST       Storage endpoint for the zone's region, e.g.
                             storage.bunnycdn.com (Falkenstein) or
                             ny.storage.bunnycdn.com. Default: storage.bunnycdn.com.
    BUNNY_API_KEY            Account API key, for the cache purge. Optional.
    BUNNY_PULL_ZONE_ID       Pull Zone id, for the cache purge. Optional.

Usage:
    python bunny_deploy.py docs/_build/html
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

WORKERS = 8
RETRIES = 4


def request(method: str, url: str, key: str, data: bytes | None = None, headers: dict | None = None) -> bytes:
    """Sends a request, retrying on network errors and 5xx/429 responses."""
    for attempt in range(RETRIES):
        req = urllib.request.Request(url, data=data, method=method, headers={"AccessKey": key, **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as err:
            if err.code == 404 and method in ("GET", "DELETE"):
                return b"[]" if method == "GET" else b""
            if err.code < 500 and err.code != 429 or attempt == RETRIES - 1:
                body = err.read().decode(errors="replace")[:300]
                raise SystemExit(f"{method} {url} failed: HTTP {err.code} {body}") from None
        except urllib.error.URLError as err:
            if attempt == RETRIES - 1:
                raise SystemExit(f"{method} {url} failed: {err.reason}") from None
        time.sleep(2**attempt)
    raise AssertionError("unreachable")


class Storage:
    def __init__(self, host: str, zone: str, key: str):
        origin = host if "://" in host else f"https://{host}"
        self.base = f"{origin.rstrip('/')}/{urllib.parse.quote(zone)}/"
        self.key = key

    def url(self, path: str) -> str:
        return self.base + urllib.parse.quote(path)

    def list_files(self, prefix: str = "") -> list[str]:
        """Returns every file path in the zone under 'prefix', recursively."""
        items = json.loads(request("GET", self.url(prefix), self.key, headers={"Accept": "application/json"}))
        files: list[str] = []
        for item in items:
            path = prefix + item["ObjectName"]
            if item["IsDirectory"]:
                files.extend(self.list_files(path + "/"))
            else:
                files.append(path)
        return files

    def upload(self, path: str, local: pathlib.Path) -> None:
        data = local.read_bytes()
        content_type = mimetypes.guess_type(local.name)[0] or "application/octet-stream"
        request("PUT", self.url(path), self.key, data=data, headers={
            "Content-Type": content_type,
            "Checksum": hashlib.sha256(data).hexdigest().upper(),
        })

    def delete(self, path: str) -> None:
        request("DELETE", self.url(path), self.key)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    site = pathlib.Path(sys.argv[1])
    if not (site / "index.html").is_file():
        raise SystemExit(f"{site} has no index.html; build the site first")
    env = os.environ
    for name in ("BUNNY_STORAGE_ZONE", "BUNNY_STORAGE_PASSWORD"):
        if not env.get(name):
            raise SystemExit(f"{name} is not set")
    storage = Storage(env.get("BUNNY_STORAGE_HOST") or "storage.bunnycdn.com",
                      env["BUNNY_STORAGE_ZONE"], env["BUNNY_STORAGE_PASSWORD"])

    local = {p.relative_to(site).as_posix(): p for p in sorted(site.rglob("*"))
             if p.is_file() and not any(part.startswith(".") for part in p.relative_to(site).parts)}
    remote = set(storage.list_files())

    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(lambda item: storage.upload(*item), local.items()))
        print(f"Uploaded {len(local)} files")
        stale = sorted(remote - set(local))
        list(pool.map(storage.delete, stale))
        print(f"Deleted {len(stale)} stale files")

    if env.get("BUNNY_API_KEY") and env.get("BUNNY_PULL_ZONE_ID"):
        zone_id = urllib.parse.quote(env["BUNNY_PULL_ZONE_ID"])
        request("POST", f"https://api.bunny.net/pullzone/{zone_id}/purgeCache", env["BUNNY_API_KEY"])
        print("Purged the Pull Zone cache")
    else:
        print("BUNNY_API_KEY or BUNNY_PULL_ZONE_ID not set; skipped the cache purge")


if __name__ == "__main__":
    main()
