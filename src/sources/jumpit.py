"""점핏(jumpit.saramin.co.kr) 어댑터.

공개 JSON API 를 최신 등록순으로 읽는다.
응답 예시는 tests/fixtures/jumpit_page.json 에 저장돼 있다.
"""

from __future__ import annotations

import logging

from ..models import JobPosting
from .base import JobSource, dedupe

log = logging.getLogger(__name__)

API = "https://api.jumpit.co.kr/api/positions?sort=reg_dt&highlight=false&page={page}"
POSITION_URL = "https://www.jumpit.co.kr/position/{id}"


def _career(raw: dict) -> tuple[int | None, int | None]:
    lo, hi = raw.get("minCareer"), raw.get("maxCareer")
    if lo is None and hi is None:
        return None, None
    return (int(lo) if lo is not None else None, int(hi) if hi is not None else None)


def _deadline(raw: dict) -> str:
    if raw.get("alwaysOpen"):
        return "상시채용"
    closed = raw.get("closedAt")
    if not closed:
        return ""
    return str(closed)[:10]


def parse_page(data: dict) -> list[JobPosting]:
    positions = ((data or {}).get("result") or {}).get("positions") or []
    out: list[JobPosting] = []
    for raw in positions:
        job_id = raw.get("id")
        if job_id is None:
            continue
        lo, hi = _career(raw)
        out.append(
            JobPosting(
                source="jumpit",
                job_id=str(job_id),
                title=str(raw.get("title") or "").strip(),
                company=str(raw.get("companyName") or "").strip(),
                url=POSITION_URL.format(id=job_id),
                tech_stacks=tuple(raw.get("techStacks") or ()),
                category=str(raw.get("jobCategory") or "").strip(),
                career_min=lo,
                career_max=hi,
                location=(raw.get("locations") or [""])[0],
                deadline=_deadline(raw),
            )
        )
    return out


class JumpitSource(JobSource):
    name = "jumpit"

    def fetch(self, queries: tuple[str, ...], max_pages: int) -> list[JobPosting]:
        collected: list[JobPosting] = []
        for page in range(1, max_pages + 1):
            data = self.http.get_json(API.format(page=page))
            postings = parse_page(data)
            if not postings:
                break
            collected.extend(postings)
        return dedupe(collected)
