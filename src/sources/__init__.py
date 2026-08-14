"""소스 레지스트리.

새 채용 사이트를 붙이려면 JobSource 를 상속한 클래스를 만들고
아래 SOURCES 에 등록한 뒤, config.py 의 VALID_SOURCES 에 이름을 추가하면 된다.
"""

from __future__ import annotations

from .base import JobSource
from .jobkorea import JobKoreaSource
from .jumpit import JumpitSource
from .rallit import RallitSource
from .wanted import WantedSource

SOURCES: dict[str, type[JobSource]] = {
    JumpitSource.name: JumpitSource,
    WantedSource.name: WantedSource,
    RallitSource.name: RallitSource,
    JobKoreaSource.name: JobKoreaSource,
}

__all__ = ["JobSource", "SOURCES", "JumpitSource", "WantedSource", "RallitSource", "JobKoreaSource"]
