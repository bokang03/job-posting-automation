"""잡코리아(jobkorea.co.kr) 어댑터.

잡코리아는 공개 API 가 없어 검색 결과 HTML 을 파싱한다.
다른 세 사이트와 달리 사이트 개편에 취약하므로, 여기서 예외가 나도
전체 실행이 멈추지 않도록 main.py 가 소스별로 예외를 잡는다.

또한 검색어 기반이라 프로필의 search_queries 를 그대로 검색창에 넣는 방식으로 동작한다.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from ..models import JobPosting
from .base import JobSource, dedupe

log = logging.getLogger(__name__)

SEARCH_URL = "https://www.jobkorea.co.kr/Search/?stext={query}&tabType=recruit"
READ_URL = "https://www.jobkorea.co.kr/Recruit/GI_Read/{id}"

_GINO_RE = re.compile(r"GI_Read/(\d+)")
_REGION_RE = re.compile(
    r"^(서울|경기|인천|부산|대구|대전|광주|울산|세종|강원|충북|충남|전북|전남|경북|경남|제주|해외)"
)
_CAREER_RE = re.compile(r"(신입|경력)")


def parse_career_text(text: str) -> tuple[int | None, int | None]:
    """'경력5년↑' 같은 잡코리아 표기를 연차 구간으로 바꾼다."""
    t = (text or "").strip()
    if not t:
        return None, None
    if "무관" in t:
        return None, None

    has_new = "신입" in t
    has_exp = "경력" in t

    m = re.search(r"(\d+)\s*~\s*(\d+)\s*년", t)
    if m:
        return (0 if has_new else int(m.group(1))), int(m.group(2))

    m = re.search(r"(\d+)\s*년", t)
    if m:
        return (0 if has_new else int(m.group(1))), None

    if has_new and has_exp:
        return 0, None
    if has_new:
        return 0, 0
    if has_exp:
        # 연차를 밝히지 않은 경력직. 신입 필터에 걸리지 않도록 최소 1년으로 본다.
        return 1, None
    return None, None


def _card_texts(card) -> list[str]:
    out = []
    for span in card.find_all("span"):
        t = span.get_text(strip=True)
        if t and t not in out:
            out.append(t)
    return out


def _parse_card(card) -> JobPosting | None:
    anchors = [a for a in card.find_all("a", href=True) if "GI_Read/" in a["href"]]
    if not anchors:
        return None

    m = _GINO_RE.search(anchors[0]["href"])
    if not m:
        return None
    job_id = m.group(1)

    labels = [a.get_text(strip=True) for a in anchors]
    labels = [t for t in labels if t]
    if not labels:
        return None

    title = labels[0]
    company = next((t for t in labels[1:] if t != title), "")

    texts = _card_texts(card)
    location = next((t for t in texts if _REGION_RE.match(t)), "")
    category = next((t for t in texts if "," in t and not _REGION_RE.match(t)), "")
    career_text = next(
        (t for t in texts if _CAREER_RE.search(t) and t not in (title, company, category)),
        "",
    )
    lo, hi = parse_career_text(career_text)

    return JobPosting(
        source="jobkorea",
        job_id=job_id,
        title=title,
        company=company,
        url=READ_URL.format(id=job_id),
        tech_stacks=(),
        category=category,
        career_min=lo,
        career_max=hi,
        location=location,
        deadline="",
    )


def parse_html(html: str) -> list[JobPosting]:
    soup = BeautifulSoup(html or "", "html.parser")
    cards = soup.find_all(attrs={"data-sentry-component": "CardJob"})
    out: list[JobPosting] = []
    for card in cards:
        try:
            posting = _parse_card(card)
        except Exception:  # 카드 하나가 깨져도 나머지는 살린다
            log.debug("잡코리아 카드 파싱 실패", exc_info=True)
            continue
        if posting and posting.title:
            out.append(posting)
    return dedupe(out)


class JobKoreaSource(JobSource):
    name = "jobkorea"

    def fetch(self, queries: tuple[str, ...], max_pages: int) -> list[JobPosting]:
        if not queries:
            log.warning("잡코리아는 검색어가 필요합니다. config.yaml 의 search_queries 를 채워주세요.")
            return []

        collected: list[JobPosting] = []
        for query in queries:
            html = self.http.get_text(SEARCH_URL.format(query=quote(query)))
            found = parse_html(html)
            log.info("  잡코리아 '%s' 검색: %d건", query, len(found))
            collected.extend(found)
        return dedupe(collected)
