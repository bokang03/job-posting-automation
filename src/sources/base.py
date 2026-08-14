"""소스 어댑터가 지켜야 하는 최소 규약."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from ..http import HttpClient
from ..models import JobPosting

log = logging.getLogger(__name__)


class JobSource(ABC):
    """채용 사이트 하나에서 최신 공고를 가져온다.

    새 사이트를 추가하려면 이 클래스를 상속해 name 과 fetch 만 구현하고
    src/sources/__init__.py 의 SOURCES 에 등록하면 된다.
    """

    name: str = ""

    def __init__(self, http: HttpClient):
        self.http = http

    @abstractmethod
    def fetch(self, queries: tuple[str, ...], max_pages: int) -> list[JobPosting]:
        """최신 공고 목록. queries 는 검색어 기반 사이트만 사용한다."""


def dedupe(postings: list[JobPosting]) -> list[JobPosting]:
    """같은 공고가 여러 페이지/검색어에 걸쳐 중복으로 잡히는 것을 제거한다."""
    seen: set[str] = set()
    out: list[JobPosting] = []
    for p in postings:
        if p.uid in seen:
            continue
        seen.add(p.uid)
        out.append(p)
    return out
