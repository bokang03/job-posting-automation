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


def parse_employment_type(html: str) -> str:
    """상세 페이지에서 고용형태(정규직 / 인턴 / 연수생·교육생 ...)를 읽는다.

    검색 결과 목록에는 이 값이 없어서 상세 페이지를 따로 봐야 한다.
    페이지에는 '고용형태' 라벨 바로 뒤에 값이 온다.

    '인턴 (근무기간 2개월, 정규직 전환 가능)' 처럼 괄호 설명이 붙는 경우가 있는데,
    괄호 안에 '정규직' 이 들어 있어서 그대로 두면 인턴이 정규직으로 잘못 분류된다.
    그래서 괄호 이후는 버린다.
    """
    if "고용형태" not in (html or ""):
        return ""

    soup = BeautifulSoup(html, "html.parser")
    # 태그를 줄바꿈으로 바꿔 라벨과 값을 분리한다.
    lines = [line.strip() for line in soup.get_text("\n").split("\n")]
    lines = [line for line in lines if line]

    for i, line in enumerate(lines):
        if line != "고용형태":
            continue
        for value in lines[i + 1 :]:
            if value == "고용형태":
                continue
            return value.split("(")[0].strip()
    return ""


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

    def enrich(self, postings: list[JobPosting]) -> list[JobPosting]:
        """공고마다 상세 페이지를 열어 고용형태를 채운다.

        실패해도 공고를 버리지 않는다. 상세 조회가 막혔다고 진짜 기회를 놓치는 것보다,
        고용형태를 모른 채로 알림이 한 번 오는 편이 낫다.
        """
        out: list[JobPosting] = []
        for posting in postings:
            try:
                html = self.http.get_text(READ_URL.format(id=posting.job_id))
                label = parse_employment_type(html)
            except Exception as e:
                log.info("  잡코리아 상세 조회 실패(%s): %s", posting.job_id, e)
                out.append(posting)
                continue
            out.append(posting.with_tags((label,)) if label else posting)
        return out
