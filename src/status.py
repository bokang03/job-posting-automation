"""'시스템이 살아있다'는 상태 메시지를 언제 보낼지 결정한다.

새 공고가 없으면 알림이 안 오는데, 그게 정상인지 고장인지 구분이 안 된다.
그렇다고 매 실행마다 보내면 30분마다 하루 48번이라 알림 채널을 못 쓰게 된다.

그래서 '조용한 상태가 일정 시간 이어질 때만' 한 번 보낸다.
공고 알림이 나간 실행은 그 자체로 살아있음의 증거이므로 상태 메시지를 보내지 않는다.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 사이트 수집이 실패했을 때는 더 빨리 알린다. 손봐야 하는 상황이기 때문이다.
FAILURE_INTERVAL_HOURS = 1.0


class StatusStore:
    """상태 메시지를 마지막으로 보낸 시각만 기억한다."""

    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)
        self.last_sent_at: datetime | None = None

    def load(self) -> None:
        if not self.path.exists():
            self.last_sent_at = None
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            stamp = data.get("last_sent_at") if isinstance(data, dict) else None
            self.last_sent_at = datetime.fromisoformat(stamp) if stamp else None
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            # 깨졌으면 처음부터. 최악의 경우 상태 메시지가 한 번 더 올 뿐이다.
            self.last_sent_at = None

    def mark_sent(self, now: datetime) -> None:
        self.last_sent_at = now

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"last_sent_at": self.last_sent_at.isoformat() if self.last_sent_at else None}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    def should_send(
        self,
        *,
        sent_count: int,
        has_failures: bool,
        heartbeat_hours: float,
        now: datetime | None = None,
    ) -> bool:
        if heartbeat_hours <= 0:
            return False
        if sent_count > 0:
            return False
        if self.last_sent_at is None:
            # 첫 실행에서는 설정이 제대로 됐는지 한 번 알려준다.
            return True

        hours = min(heartbeat_hours, FAILURE_INTERVAL_HOURS) if has_failures else heartbeat_hours
        now = now or datetime.now(timezone.utc)
        return now - self.last_sent_at >= timedelta(hours=hours)
