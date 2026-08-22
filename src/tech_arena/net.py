from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


USER_AGENT = "Huawei-Tech-Arena-Topic-2/0.1 (academic competition project)"


def _request(url: str) -> Request:
    return Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/csv,*/*",
        },
    )


def get_bytes(url: str, retries: int = 3, timeout: int = 90) -> bytes:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urlopen(_request(url), timeout=timeout) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                retry_after = None
                if isinstance(exc, HTTPError):
                    retry_after = exc.headers.get("Retry-After")
                if retry_after and str(retry_after).isdigit():
                    delay = min(60, int(retry_after))
                elif isinstance(exc, HTTPError) and exc.code == 429:
                    delay = min(60, 5 * (2**attempt))
                else:
                    delay = min(30, 2**attempt)
                time.sleep(delay)
    raise RuntimeError(f"Unable to fetch {url}") from last_error


def get_json(url: str, retries: int = 3, timeout: int = 90) -> dict[str, Any]:
    return json.loads(get_bytes(url, retries=retries, timeout=timeout).decode("utf-8"))


def post_form_json(
    url: str,
    fields: dict[str, str],
    retries: int = 3,
    timeout: int = 180,
) -> dict[str, Any]:
    payload = urlencode(fields).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = Request(
                url,
                data=payload,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(min(30, 5 * (2**attempt)))
    raise RuntimeError(f"Unable to post to {url}") from last_error


def download_file(url: str, destination: Path, force: bool = False) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not force:
        payload = destination.read_bytes()
    else:
        payload = get_bytes(url)
        temporary = destination.with_suffix(destination.suffix + ".part")
        temporary.write_bytes(payload)
        temporary.replace(destination)
    return {
        "url": url,
        "path": str(destination),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
