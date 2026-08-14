"""실행 진입점.

  python -m src.main            평소 실행 (디스코드로 전송)
  python -m src.main --dry-run  전송 없이 어떤 공고가 걸리는지만 확인
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from .config import Config, ConfigError, Profile, load_config
from .filters import matches_profile
from .http import HttpClient
from .notifiers.discord import DiscordNotifier
from .pipeline import RunReport, gather, run
from .sources import SOURCES
from .state import SeenStore

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("joballert")


def load_dotenv(path: Path) -> None:
    """로컬 실행 편의를 위한 최소한의 .env 로더.

    GitHub Actions 에서는 Secrets 가 이미 환경변수로 들어오므로 이 파일이 없어도 된다.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def build_sources(config: Config, http: HttpClient) -> dict:
    needed = {name for profile in config.active_profiles for name in profile.sources}
    return {name: SOURCES[name](http) for name in needed if name in SOURCES}


def make_notifier_factory(cache: dict):
    def factory(profile: Profile) -> DiscordNotifier:
        if profile.webhook_env not in cache:
            url = os.environ.get(profile.webhook_env, "")
            if not url:
                raise ConfigError(
                    f"프로필 '{profile.name}' 이(가) 요구하는 환경변수 {profile.webhook_env} 가 비어 있습니다.\n"
                    f"  - GitHub Actions: 저장소 Settings > Secrets and variables > Actions 에 "
                    f"{profile.webhook_env} 를 등록하세요.\n"
                    f"  - 내 PC: 프로젝트 폴더의 .env 파일에 {profile.webhook_env}=... 를 적어주세요."
                )
            cache[profile.webhook_env] = DiscordNotifier(url)
        return cache[profile.webhook_env]

    return factory


def print_preview(config: Config, sources: dict) -> None:
    """--dry-run 일 때 어떤 공고가 걸렸는지 화면에 보여준다."""
    collected = gather(config, sources, RunReport())
    for profile in config.active_profiles:
        matched = [
            p
            for name in profile.sources
            for p in collected.get(name, [])
            if matches_profile(p, profile)
        ]
        print(f"\n=== {profile.name} — 조건에 맞는 공고 {len(matched)}건 ===")
        for p in matched[:30]:
            print(f"  [{p.source_label}] {p.company} | {p.title}")
            print(f"      경력={p.career_text}  지역={p.location or '-'}  {p.url}")
        if len(matched) > 30:
            print(f"  ... 외 {len(matched) - 30}건")


def print_summary(report: RunReport) -> None:
    print("\n" + "=" * 60)
    if report.first_run:
        print("첫 실행입니다. 과거 공고가 쏟아지지 않도록 최신 일부만 보냈습니다.")
    for name, count in report.fetched_by_source.items():
        print(f"  수집  {name:10s} {count:4d}건")
    for name, count in report.matched_by_profile.items():
        sent = report.sent_by_profile.get(name, 0)
        print(f"  프로필 '{name}': 조건 일치 {count}건 / 새로 보낸 알림 {sent}건")
    for name, reason in report.failed_sources.items():
        print(f"  [실패] {name}: {reason}")
    print("=" * 60)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="직무 공고를 모아 디스코드로 알려줍니다.")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"), help="설정 파일 경로")
    parser.add_argument("--state", default=str(ROOT / "state" / "seen.json"), help="중복 방지 기록 파일 경로")
    parser.add_argument(
        "--dry-run", action="store_true", help="디스코드로 보내지 않고 걸린 공고만 화면에 출력"
    )
    parser.add_argument("--verbose", action="store_true", help="자세한 로그 출력")
    args = parser.parse_args(argv)

    setup_logging(args.verbose)
    load_dotenv(ROOT / ".env")

    try:
        config = load_config(args.config)
    except ConfigError as e:
        print(f"\n[설정 오류] {e}\n", file=sys.stderr)
        return 2

    if not config.active_profiles:
        print("활성화된 프로필이 없습니다. config.yaml 에서 enabled: true 인 프로필을 만들어주세요.")
        return 0

    http = HttpClient()
    sources = build_sources(config, http)
    store = SeenStore(args.state, retention_days=config.settings.seen_retention_days)
    store.load()

    if args.dry_run:
        print_preview(config, sources)
        print("\n(--dry-run 이므로 디스코드로 아무것도 보내지 않았고, 기록도 남기지 않았습니다.)")
        return 0

    try:
        notifier_factory = make_notifier_factory({})
        report = run(config, sources, notifier_factory, store)
    except ConfigError as e:
        print(f"\n[설정 오류] {e}\n", file=sys.stderr)
        return 2

    print_summary(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
