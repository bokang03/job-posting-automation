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
