"""모든 채용 사이트의 공고를 하나의 공통 형태로 표현하는 모델."""

from __future__ import annotations

from dataclasses import dataclass, replace

# 사이트 코드 -> 사람이 읽는 이름
SOURCE_LABELS = {
    "jumpit": "점핏",
    "wanted": "원티드",
    "rallit": "랠릿",
    "jobkorea": "잡코리아",
}


@dataclass(frozen=True)
class JobPosting:
    """한 건의 채용 공고.

    career_min / career_max 는 '요구 경력 연차' 구간입니다.
      - (0, 0)        신입만
      - (0, 3)        신입~3년
      - (5, None)     5년 이상 (상한 없음)
      - (None, None)  경력무관이거나 사이트가 경력 정보를 주지 않음
    """

    source: str
    job_id: str
    title: str
    company: str
    url: str
    tech_stacks: tuple[str, ...] = ()
    # 사이트가 준 직무 분류. 한 공고에 여러 직무를 나열하는 경우가 많다
    # (예: "정보보안, 백엔드개발자, 프론트엔드개발자"). 넓은 값이라 제외 판정에는 쓰지 않는다.
    category: str = ""
    # 고용형태·등급 표시(인턴, 신입 등). 좁고 확실한 값이라 제외 판정에 쓴다.
    tags: tuple[str, ...] = ()
    career_min: int | None = None
    career_max: int | None = None
    location: str = ""
    deadline: str = ""

    def with_tags(self, extra: tuple[str, ...]) -> "JobPosting":
        """태그를 덧붙인 사본. 나중에 알아낸 정보(고용형태 등)를 채울 때 쓴다."""
        merged = self.tags + tuple(t for t in extra if t and t not in self.tags)
        return replace(self, tags=merged)

    @property
    def uid(self) -> str:
        """중복 알림 방지에 쓰는 전역 고유 키."""
        return f"{self.source}:{self.job_id}"

    @property
    def source_label(self) -> str:
        return SOURCE_LABELS.get(self.source, self.source)

    @property
    def career_text(self) -> str:
        """디스코드 카드에 표시할 경력 문구."""
        lo, hi = self.career_min, self.career_max
        if lo is None and hi is None:
            return "경력무관"
        if lo == 0 and hi == 0:
            return "신입"
        if lo == 0 and hi is not None:
            return f"신입~{hi}년"
        if lo is not None and hi is None:
            return f"{lo}년 이상"
        if lo is not None and hi is not None:
            return f"{lo}~{hi}년" if lo != hi else f"{lo}년"
        return "경력무관"

    def haystack(self) -> str:
        """포함(any/all) 판정에 쓰는 문자열. 넓게 잡아 놓친 공고를 줄인다.

        회사명은 일부러 뺐다. 회사 이름에 우연히 'Node' 같은 글자가 들어가면
        엉뚱한 공고가 걸리기 때문이다.
        """
        parts = [self.title, self.category, " ".join(self.tech_stacks), " ".join(self.tags)]
        return " ".join(p for p in parts if p).lower()

    def exclusion_haystack(self) -> str:
        """제외(none) 판정에 쓰는 문자열. 좁게 잡아 오탐 제외를 막는다.

        category 를 뺀 이유: 잡코리아처럼 한 공고에 여러 직무를 나열하는 사이트에서는
        '백엔드개발자, 프론트엔드개발자'로 적힌 정상 공고가
        '프론트엔드' 제외 키워드에 걸려 통째로 사라진다.
        """
        parts = [self.title, " ".join(self.tech_stacks), " ".join(self.tags)]
        return " ".join(p for p in parts if p).lower()
