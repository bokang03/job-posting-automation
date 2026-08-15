"""디스코드 웹훅으로 공고 카드를 보낸다."""

from __future__ import annotations

import logging
import time

import requests

from ..models import JobPosting

log = logging.getLogger(__name__)

# 디스코드가 정한 한계값
MAX_EMBEDS_PER_MESSAGE = 10
MAX_TITLE = 256
MAX_FIELD_VALUE = 1024

HEALTHY_COLOR = 0x2ECC71  # 초록 - 정상
WARNING_COLOR = 0xE67E22  # 주황 - 일부 사이트 실패

SOURCE_COLORS = {
    "jumpit": 0x4A6EE0,
    "wanted": 0x3366FF,
    "rallit": 0x6C5CE7,
    "jobkorea": 0x1F8CE6,
}
DEFAULT_COLOR = 0x5865F2


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def build_embed(posting: JobPosting, profile_name: str) -> dict:
    fields = [{"name": "경력", "value": posting.career_text, "inline": True}]
    if posting.tags:
        fields.append(
            {"name": "고용형태", "value": _clip(", ".join(posting.tags), MAX_FIELD_VALUE), "inline": True}
        )
    if posting.location:
        fields.append({"name": "지역", "value": _clip(posting.location, MAX_FIELD_VALUE), "inline": True})
    if posting.deadline:
        fields.append({"name": "마감", "value": _clip(posting.deadline, MAX_FIELD_VALUE), "inline": True})
    if posting.tech_stacks:
        fields.append(
            {
                "name": "기술스택",
                "value": _clip(", ".join(posting.tech_stacks), MAX_FIELD_VALUE),
                "inline": False,
            }
        )

    return {
        "title": _clip(f"[{posting.company}] {posting.title}", MAX_TITLE),
        "url": posting.url,
        "color": SOURCE_COLORS.get(posting.source, DEFAULT_COLOR),
        "fields": fields,
        "footer": {"text": f"{posting.source_label} · {profile_name}"},
    }


def build_status_embed(report) -> dict:
    """새 공고가 없을 때 '살아있다'는 것을 알리는 카드.

    조용한 게 정상인지 고장인지 구분되지 않는 문제를 해결하려고 만든다.
    수집 건수와 조건 일치 건수를 함께 보여주면, 필터가 너무 좁은 건지
    정말 새 공고가 없는 건지도 판단할 수 있다.
    """
    failed = getattr(report, "failed_sources", {}) or {}

    fields = []
    if report.fetched_by_source:
        fields.append(
            {
                "name": "수집",
                "value": _clip(
                    "\n".join(f"{name} {count}건" for name, count in report.fetched_by_source.items()),
                    MAX_FIELD_VALUE,
                ),
                "inline": True,
            }
        )
    if report.matched_by_profile:
        fields.append(
            {
                "name": "조건 일치",
                "value": _clip(
                    "\n".join(f"{name} {count}건" for name, count in report.matched_by_profile.items()),
                    MAX_FIELD_VALUE,
                ),
                "inline": True,
            }
        )
    if failed:
        fields.append(
            {
                "name": "수집 실패",
                "value": _clip(
                    "\n".join(f"{name}: {reason}" for name, reason in failed.items()), MAX_FIELD_VALUE
                ),
                "inline": False,
            }
        )

    if failed:
        title = f"⚠️ 일부 사이트 수집 실패 ({len(failed)}곳)"
        description = "나머지 사이트는 정상 동작 중입니다. 계속되면 해당 사이트가 막힌 것일 수 있습니다."
    else:
        title = "✅ 정상 동작 중 — 새 공고 없음"
        description = "조건에 맞는 새 공고가 없어 알림을 보내지 않았습니다."

    return {
        "title": title,
        "description": description,
        "color": WARNING_COLOR if failed else HEALTHY_COLOR,
        "fields": fields,
        "footer": {"text": "이 메시지는 조용한 상태가 이어질 때만 옵니다"},
    }


def _batches(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


class DiscordNotifier:
    def __init__(
        self,
        webhook_url: str,
        transport=None,
        sleep=time.sleep,
        max_retries: int = 3,
        pause: float = 0.6,
    ):
        if not webhook_url:
            raise ValueError(
                "디스코드 웹훅 URL 이 비어 있습니다. "
                "GitHub Secrets 또는 .env 파일에 DISCORD_WEBHOOK_URL 을 등록했는지 확인해주세요."
            )
        self.webhook_url = webhook_url
        self.transport = transport or requests.Session()
        self.sleep = sleep
        self.max_retries = max_retries
        self.pause = pause

    def _post_batch(self, payload: dict) -> bool:
        for attempt in range(self.max_retries):
            try:
                resp = self.transport.post(self.webhook_url, json=payload)
            except Exception as e:
                log.warning("디스코드 전송 중 오류: %s", e)
                if attempt < self.max_retries - 1:
                    self.sleep(self.pause * (attempt + 1))
                continue

            if 200 <= resp.status_code < 300:
                return True

            if resp.status_code == 429:
                retry_after = 1.0
                try:
                    retry_after = float(resp.json().get("retry_after", 1.0))
                except Exception:
                    pass
                log.info("디스코드 속도 제한, %.1f초 대기", retry_after)
                self.sleep(retry_after)
                continue

            log.warning("디스코드가 %s 응답을 반환했습니다.", resp.status_code)
            if attempt < self.max_retries - 1:
                self.sleep(self.pause * (attempt + 1))

        return False

    def send_status(self, report) -> bool:
        """상태 메시지 한 건. 보냈으면 True."""
        return self._post_batch({"embeds": [build_status_embed(report)]})

    def send(self, postings: list[JobPosting], profile_name: str) -> int:
        """보낸 공고 수를 반환한다. 일부 배치가 실패해도 나머지는 계속 보낸다."""
        if not postings:
            return 0

        sent = 0
        for batch in _batches(list(postings), MAX_EMBEDS_PER_MESSAGE):
            payload = {
                "content": f"**{profile_name}** 새 공고 {len(batch)}건",
                "embeds": [build_embed(p, profile_name) for p in batch],
            }
            if self._post_batch(payload):
                sent += len(batch)
            else:
                log.warning("공고 %d건 전송에 실패했습니다.", len(batch))
            self.sleep(self.pause)
        return sent
