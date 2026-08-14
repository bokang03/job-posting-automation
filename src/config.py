"""config.yaml 을 읽고 검증한다.

이 파일을 직접 고치는 사람은 개발자가 아닐 수 있으므로,
오류 메시지는 '무엇을 어떻게 고쳐야 하는지'까지 한국어로 알려준다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

VALID_SOURCES = ("jumpit", "wanted", "rallit", "jobkorea")


class ConfigError(Exception):
    """설정 파일이 잘못됐을 때. 메시지를 그대로 사용자에게 보여준다."""


@dataclass(frozen=True)
class KeywordSpec:
    any: tuple[str, ...] = ()
    all: tuple[str, ...] = ()
    none: tuple[str, ...] = ()


@dataclass(frozen=True)
class CareerSpec:
    min_years: int = 0
    max_years: int = 0
    include_irrelevant: bool = True


@dataclass(frozen=True)
class Profile:
    name: str
    enabled: bool
    sources: tuple[str, ...]
    keywords: KeywordSpec
    career: CareerSpec
    locations: tuple[str, ...]
    exclude_companies: tuple[str, ...]
    search_queries: tuple[str, ...]
    webhook_env: str

    def effective_queries(self) -> tuple[str, ...]:
        """잡코리아 검색에 쓸 단어. 지정이 없으면 keywords.any 앞 3개."""
        if self.search_queries:
            return self.search_queries
        return self.keywords.any[:3]


@dataclass(frozen=True)
class Settings:
    max_notifications_per_run: int = 25
    first_run_limit: int = 10
    seen_retention_days: int = 60
    max_pages: int = 3


@dataclass(frozen=True)
class Config:
    settings: Settings
    profiles: tuple[Profile, ...]

    @property
    def active_profiles(self) -> tuple[Profile, ...]:
        return tuple(p for p in self.profiles if p.enabled)


def _as_str_tuple(value, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, list):
        raise ConfigError(f"{where} 는 목록이어야 합니다. 예: {where}: [\"항목1\", \"항목2\"]")
    out = []
    for item in value:
        if item is None:
            continue
        out.append(str(item).strip())
    return tuple(v for v in out if v)


def _as_int(value, where: str, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ConfigError(f"{where} 는 숫자여야 합니다. 지금 값: {value!r}") from None


def _parse_profile(raw: dict, index: int) -> Profile:
    if not isinstance(raw, dict):
        raise ConfigError(f"profiles 의 {index + 1}번째 항목이 올바른 형식이 아닙니다.")

    name = str(raw.get("name") or f"프로필 {index + 1}").strip()
    where = f"프로필 '{name}'"

    sources = _as_str_tuple(raw.get("sources"), f"{where} 의 sources")
    if not sources:
        raise ConfigError(
            f"{where} 에 sources 가 비어 있습니다. "
            f"다음 중 하나 이상을 적어주세요: {', '.join(VALID_SOURCES)}"
        )
    unknown = [s for s in sources if s not in VALID_SOURCES]
    if unknown:
        raise ConfigError(
            f"{where} 의 sources 에 모르는 사이트가 있습니다: {', '.join(unknown)}. "
            f"쓸 수 있는 값: {', '.join(VALID_SOURCES)}"
        )

    kw_raw = raw.get("keywords") or {}
    if not isinstance(kw_raw, dict):
        raise ConfigError(f"{where} 의 keywords 는 any / all / none 하위 항목을 가져야 합니다.")
    keywords = KeywordSpec(
        any=_as_str_tuple(kw_raw.get("any"), f"{where} 의 keywords.any"),
        all=_as_str_tuple(kw_raw.get("all"), f"{where} 의 keywords.all"),
        none=_as_str_tuple(kw_raw.get("none"), f"{where} 의 keywords.none"),
    )

    car_raw = raw.get("career") or {}
    if not isinstance(car_raw, dict):
        raise ConfigError(f"{where} 의 career 는 min_years / max_years 하위 항목을 가져야 합니다.")
    min_years = _as_int(car_raw.get("min_years"), f"{where} 의 career.min_years", 0)
    max_years = _as_int(car_raw.get("max_years"), f"{where} 의 career.max_years", 0)
    if min_years < 0 or max_years < 0:
        raise ConfigError(f"{where} 의 경력 연차는 0 이상이어야 합니다.")
    if min_years > max_years:
        raise ConfigError(
            f"{where} 의 career.min_years({min_years}) 가 career.max_years({max_years}) 보다 큽니다. "
            f"min_years 가 더 작거나 같아야 합니다."
        )

    career = CareerSpec(
        min_years=min_years,
        max_years=max_years,
        include_irrelevant=bool(car_raw.get("include_irrelevant", True)),
    )

    webhook_env = str(raw.get("webhook_env") or "DISCORD_WEBHOOK_URL").strip()

    return Profile(
        name=name,
        enabled=bool(raw.get("enabled", True)),
        sources=sources,
        keywords=keywords,
        career=career,
        locations=_as_str_tuple(raw.get("locations"), f"{where} 의 locations"),
        exclude_companies=_as_str_tuple(raw.get("exclude_companies"), f"{where} 의 exclude_companies"),
        search_queries=_as_str_tuple(raw.get("search_queries"), f"{where} 의 search_queries"),
        webhook_env=webhook_env,
    )


def load_config(path: str | os.PathLike) -> Config:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"설정 파일을 찾을 수 없습니다: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigError(
            f"config.yaml 의 형식이 잘못됐습니다. 들여쓰기에 탭 문자를 쓰지 않았는지 확인해주세요.\n{e}"
        ) from None

    if not isinstance(raw, dict):
        raise ConfigError("config.yaml 의 최상위는 settings / profiles 두 항목을 가져야 합니다.")

    s_raw = raw.get("settings") or {}
    if not isinstance(s_raw, dict):
        raise ConfigError("settings 항목의 형식이 잘못됐습니다.")
    settings = Settings(
        max_notifications_per_run=_as_int(
            s_raw.get("max_notifications_per_run"), "settings.max_notifications_per_run", 25
        ),
        first_run_limit=_as_int(s_raw.get("first_run_limit"), "settings.first_run_limit", 10),
        seen_retention_days=_as_int(s_raw.get("seen_retention_days"), "settings.seen_retention_days", 60),
        max_pages=max(1, _as_int(s_raw.get("max_pages"), "settings.max_pages", 3)),
    )

    p_raw = raw.get("profiles")
    if not isinstance(p_raw, list) or not p_raw:
        raise ConfigError("profiles 에 최소 한 개의 프로필이 있어야 합니다.")

    profiles = tuple(_parse_profile(item, i) for i, item in enumerate(p_raw))
    return Config(settings=settings, profiles=profiles)
