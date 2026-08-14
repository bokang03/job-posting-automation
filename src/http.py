"""모든 사이트 요청이 공유하는 HTTP 클라이언트."""

from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class HttpClient:
    def __init__(self, timeout: int = 20, retries: int = 2, pause: float = 0.7):
        self.timeout = timeout
        self.retries = retries
        self.pause = pause
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            }
        )

    def _request(self, url: str, headers: dict | None = None) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                resp = self.session.get(url, headers=headers, timeout=self.timeout)
                resp.raise_for_status()
                return resp
            except requests.RequestException as e:
                last_error = e
                if attempt < self.retries:
                    wait = self.pause * (attempt + 1)
                    log.debug("요청 실패, %.1f초 후 재시도: %s", wait, url)
                    time.sleep(wait)
        raise last_error  # type: ignore[misc]

    def get_json(self, url: str, headers: dict | None = None):
        merged = {"Accept": "application/json, text/plain, */*"}
        if headers:
            merged.update(headers)
        resp = self._request(url, merged)
        time.sleep(self.pause)
        return resp.json()

    def get_text(self, url: str, headers: dict | None = None) -> str:
        merged = {"Accept": "text/html,application/xhtml+xml"}
        if headers:
            merged.update(headers)
        resp = self._request(url, merged)
        time.sleep(self.pause)
        return resp.text
