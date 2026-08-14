"""이미 알림을 보낸 공고를 기억해서 같은 공고가 두 번 오지 않게 한다."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path


class SeenStore:
    """uid -> 알림 보낸 시각(ISO 문자열) 매핑을 JSON 파일로 보관한다."""

    def __init__(self, path: str | os.PathLike, retention_days: int = 60):
        self.path = Path(path)
        self.retention_days = retention_days
        self._seen: dict[str, str] = {}
        self._existed = False

    def load(self) -> None:
        if not self.path.exists():
            self._seen, self._existed = {}, False
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # 파일이 깨졌으면 처음부터 시작한다. 최악의 경우 알림이 한 번 더 올 뿐이다.
            self._seen, self._existed = {}, False
            return
        if not isinstance(data, dict):
            self._seen, self._existed = {}, False
            return
        self._seen = {str(k): str(v) for k, v in data.items()}
        self._existed = bool(self._seen)

    @property
    def is_first_run(self) -> bool:
        """기록이 하나도 없으면 첫 실행으로 본다."""
        return not self._existed

    def has_seen(self, uid: str) -> bool:
        return uid in self._seen

    def mark(self, uid: str) -> None:
        self._seen[uid] = datetime.now(timezone.utc).isoformat()

    def _prune(self) -> dict[str, str]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        kept = {}
        for uid, stamp in self._seen.items():
            try:
                when = datetime.fromisoformat(stamp)
            except ValueError:
                continue
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            if when >= cutoff:
                kept[uid] = stamp
        return kept

    def save(self) -> None:
        self._seen = self._prune()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._seen, ensure_ascii=False, indent=1, sort_keys=True)
        # 끝에 줄바꿈을 넣어, 보낸 공고가 없을 때 파일 내용이 그대로 유지되도록 한다.
        # (그러지 않으면 워크플로가 매번 공백만 바뀐 커밋을 만든다)
        self.path.write_text(payload + "\n", encoding="utf-8")

    def __len__(self) -> int:
        return len(self._seen)
