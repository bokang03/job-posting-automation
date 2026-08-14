"""원티드(wanted.co.kr) 어댑터.

개발 직군(job_group_id=518) 전체를 최신순으로 읽고, 실제 직무 구분은 필터가 한다.

주의: 원티드 목록 응답의 skill_tags 는 숫자 ID 라서 기술스택 이름을 알 수 없다.
따라서 원티드 공고는 '제목'만으로 키워드 매칭이 이뤄진다.
"""

from __future__ import annotations

import logging

from ..models import JobPosting
from .base import JobSource, dedupe

log = logging.getLogger(__name__)

DEV_JOB_GROUP = 518
API = (
    "https://www.wanted.co.kr/api/chaos/navigation/v1/results"
    "?job_group_id={group}&country=kr&job_sort=job.latest_order"
    "&locations=all&years=-1&limit={limit}&offset={offset}"
)
POSITION_URL = "https://www.wanted.co.kr/wd/{id}"
PAGE_SIZE = 100


# 원티드는 고용형태를 코드로 준다. 다른 세 사이트에는 없는 정보라 태그로 노출해
# none 키워드("인턴", "계약직")로 걸러낼 수 있게 한다.
EMPLOYMENT_TYPES = {
    "regular": "정규직",
    "intern": "인턴",
    "contract": "계약직",
    "freelance": "프리랜서",
    "parttime": "아르바이트",
}


def _tags(raw: dict) -> tuple[str, ...]:
    label = EMPLOYMENT_TYPES.get(str(raw.get("employment_type") or "").lower())
    return (label,) if label else ()


def _location(raw: dict) -> str:
    addr = raw.get("address") or {}
    parts = [addr.get("location"), addr.get("district")]
    return " ".join(p for p in parts if p).strip()


def parse_page(data: dict) -> list[JobPosting]:
    items = (data or {}).get("data") or []
    out: list[JobPosting] = []
    for raw in items:
        job_id = raw.get("id")
        if job_id is None:
            continue
        lo, hi = raw.get("annual_from"), raw.get("annual_to")
        out.append(
            JobPosting(
                source="wanted",
                job_id=str(job_id),
                title=str(raw.get("position") or "").strip(),
                company=str((raw.get("company") or {}).get("name") or "").strip(),
                url=POSITION_URL.format(id=job_id),
                tech_stacks=(),
                category="",
                tags=_tags(raw),
                career_min=int(lo) if lo is not None else None,
                career_max=int(hi) if hi is not None else None,
                location=_location(raw),
                deadline="",
            )
        )
    return out


class WantedSource(JobSource):
    name = "wanted"

    def fetch(self, queries: tuple[str, ...], max_pages: int) -> list[JobPosting]:
        collected: list[JobPosting] = []
        for page in range(max_pages):
            url = API.format(group=DEV_JOB_GROUP, limit=PAGE_SIZE, offset=page * PAGE_SIZE)
            postings = parse_page(self.http.get_json(url, {"Referer": "https://www.wanted.co.kr/"}))
            if not postings:
                break
            collected.extend(postings)
        return dedupe(collected)
