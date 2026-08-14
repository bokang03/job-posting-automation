"""랠릿(rallit.com) 어댑터.

랠릿은 경력을 연차 숫자가 아니라 단계(BEGINNER/JUNIOR/MIDDLE/...)로 준다.
아래 표로 연차 구간에 대응시킨다. 실제 응답에서 확인한 단계는 7종이다.

JUNIOR 의 하한을 0 이 아니라 1 로 둔 이유: 랠릿은 '3-8년차 채용' 같은 공고에도
JUNIOR 를 함께 붙이는 경우가 많아서, 0 으로 두면 신입 필터에 경력직 공고가 대거 섞인다.
신입 공고는 BEGINNER 와 IRRELEVANT 로 충분히 잡힌다.
"""

from __future__ import annotations

import logging

from ..models import JobPosting
from .base import JobSource, dedupe

log = logging.getLogger(__name__)

API = (
    "https://www.rallit.com/api/v1/position"
    "?jobGroup=DEVELOPER&pageNumber={page}&pageSize={size}&sort=createdAt%2CDESC"
)
PAGE_SIZE = 50

# 단계 -> (최소 연차, 최대 연차). None 은 상한 없음.
LEVEL_RANGES: dict[str, tuple[int, int | None]] = {
    "INTERN": (0, 0),
    "BEGINNER": (0, 0),
    "JUNIOR": (1, 3),
    "MIDDLE": (3, 7),
    "SENIOR": (7, None),
    "TOP": (10, None),
}

# 랠릿 지역 코드 -> 한글. 모르는 코드는 빈 문자열로 두어
# 지역 필터가 공고를 잘못 걸러내지 않게 한다.
REGIONS: dict[str, str] = {
    "SEOUL": "서울",
    "GANGNAM": "서울 강남",
    "GURO_GASAN": "서울 구로/가산",
    "MAPO": "서울 마포",
    "PANGYO": "경기 판교",
    "GYEONGGI": "경기",
    "INCHEON": "인천",
    "BUSAN": "부산",
    "DAEGU": "대구",
    "DAEJEON": "대전",
    "GWANGJU": "광주",
    "ULSAN": "울산",
    "SEJONG": "세종",
    "GANGWON": "강원",
    "CHUNGCHEONG": "충청",
    "JEOLLA": "전라",
    "GYEONGSANG": "경상",
    "JEJU": "제주",
}


def region_to_korean(code: str | None) -> str:
    if not code:
        return ""
    return REGIONS.get(str(code).upper(), "")


def levels_to_range(levels) -> tuple[int | None, int | None]:
    known = [LEVEL_RANGES[str(lv).upper()] for lv in (levels or []) if str(lv).upper() in LEVEL_RANGES]
    if not known:
        return None, None

    lo = min(r[0] for r in known)
    # 하나라도 상한이 없으면 전체도 상한이 없다.
    hi = None if any(r[1] is None for r in known) else max(r[1] for r in known)
    return lo, hi


def _tags(raw: dict) -> tuple[str, ...]:
    """키워드 필터가 볼 수 있도록 고용형태·등급을 한글 태그로 남긴다."""
    levels = {str(lv).upper() for lv in (raw.get("jobLevels") or [])}
    tags = []
    if "INTERN" in levels:
        tags.append("인턴")
    if "BEGINNER" in levels:
        tags.append("신입")
    return tuple(tags)


def parse_page(data: dict) -> list[JobPosting]:
    items = ((data or {}).get("data") or {}).get("items") or []
    out: list[JobPosting] = []
    for raw in items:
        job_id = raw.get("id")
        if job_id is None:
            continue
        lo, hi = levels_to_range(raw.get("jobLevels"))
        out.append(
            JobPosting(
                source="rallit",
                job_id=str(job_id),
                title=str(raw.get("title") or "").strip(),
                company=str(raw.get("companyName") or "").strip(),
                url=str(raw.get("url") or f"https://www.rallit.com/positions/{job_id}"),
                tech_stacks=tuple(raw.get("jobSkillKeywords") or ()),
                category="",
                tags=_tags(raw),
                career_min=lo,
                career_max=hi,
                location=region_to_korean(raw.get("addressRegion")),
                deadline="",
            )
        )
    return out


class RallitSource(JobSource):
    name = "rallit"

    def fetch(self, queries: tuple[str, ...], max_pages: int) -> list[JobPosting]:
        collected: list[JobPosting] = []
        for page in range(1, max_pages + 1):
            postings = parse_page(
                self.http.get_json(
                    API.format(page=page, size=PAGE_SIZE), {"Referer": "https://www.rallit.com/"}
                )
            )
            if not postings:
                break
            collected.extend(postings)
        return dedupe(collected)
