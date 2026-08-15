"""매 실행마다 조금씩 옮겨가며 목록 일부를 고른다.

잡코리아는 검색어 기반이라, 검색하지 않은 회사의 공고는 아무리 기다려도 안 잡힌다.
그렇다고 화이트리스트 90곳을 한 번에 검색하면 요청이 90번이라 연결이 끊긴다.
매 실행마다 몇 곳씩 옮겨가며 검색하면 몇 시간에 걸쳐 전부 훑게 된다.
"""

from __future__ import annotations


def rotate(items, count: int, offset: int) -> list:
    """items 에서 offset 위치부터 count 개를 고른다. 끝에 닿으면 처음으로 돌아간다."""
    items = list(items)
    if not items or count <= 0:
        return []

    count = min(count, len(items))
    start = offset % len(items)
    doubled = items + items
    return doubled[start : start + count]
