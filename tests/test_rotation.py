"""잡코리아 회사명 검색어 순환.

잡코리아는 검색어 기반이라 검색하지 않은 회사의 공고는 절대 안 잡힌다.
화이트리스트에 회사가 90곳인데 한 실행에 다 검색하면 요청이 90번이라 차단당한다.
그래서 매 실행마다 조금씩 옮겨가며 검색해, 몇 시간에 걸쳐 전부 훑는다.
"""

from src.rotation import rotate


def test_takes_the_first_slice_at_offset_zero():
    assert rotate(["a", "b", "c", "d", "e"], count=2, offset=0) == ["a", "b"]


def test_moves_forward_with_the_offset():
    assert rotate(["a", "b", "c", "d", "e"], count=2, offset=2) == ["c", "d"]


def test_wraps_around_at_the_end():
    assert rotate(["a", "b", "c", "d", "e"], count=3, offset=4) == ["e", "a", "b"]


def test_offset_larger_than_the_list_still_works():
    assert rotate(["a", "b", "c"], count=2, offset=7) == ["b", "c"]


def test_asking_for_more_than_exists_returns_each_item_once():
    assert rotate(["a", "b", "c"], count=10, offset=0) == ["a", "b", "c"]


def test_empty_list_gives_nothing():
    assert rotate([], count=5, offset=3) == []


def test_zero_count_gives_nothing():
    assert rotate(["a", "b"], count=0, offset=0) == []


def test_whitelist_companies_become_search_queries(tmp_path):
    """화이트리스트에 넣은 회사가 실제로 잡코리아 검색어가 되어야 한다."""
    from src.config import CareerSpec, Config, KeywordSpec, Profile, Settings
    from src.pipeline import _queries_for
    from src.status import StatusStore

    profile = Profile(
        name="대기업", enabled=True, sources=("jobkorea",),
        keywords=KeywordSpec(), career=CareerSpec(0, 0, True), locations=(),
        include_companies=("넥슨", "카카오", "네이버", "쿠팡"),
        exclude_companies=(), search_queries=("백엔드",), search_companies=True,
        webhook_env="DISCORD_WEBHOOK_URL",
    )
    cfg = Config(settings=Settings(company_queries_per_run=2), profiles=(profile,))

    status = StatusStore(tmp_path / "status.json")
    status.load()

    first = _queries_for(cfg, status)
    assert "백엔드" in first
    assert "넥슨" in first and "카카오" in first

    # 다음 실행에서는 나머지 회사를 검색한다
    second = _queries_for(cfg, status)
    assert "네이버" in second and "쿠팡" in second


def test_companies_are_not_searched_when_the_flag_is_off(tmp_path):
    from src.config import CareerSpec, Config, KeywordSpec, Profile, Settings
    from src.pipeline import _queries_for
    from src.status import StatusStore

    profile = Profile(
        name="일반", enabled=True, sources=("jobkorea",),
        keywords=KeywordSpec(), career=CareerSpec(0, 0, True), locations=(),
        include_companies=("넥슨",), exclude_companies=(),
        search_queries=("백엔드",), search_companies=False,
        webhook_env="DISCORD_WEBHOOK_URL",
    )
    cfg = Config(settings=Settings(), profiles=(profile,))
    status = StatusStore(tmp_path / "status.json")
    status.load()
    assert _queries_for(cfg, status) == ("백엔드",)


def test_rotation_offset_survives_a_reload(tmp_path):
    from src.status import StatusStore

    s = StatusStore(tmp_path / "status.json")
    s.load()
    s.advance_queries(8)
    s.save()

    again = StatusStore(tmp_path / "status.json")
    again.load()
    assert again.query_offset == 8


def test_every_item_is_reached_within_one_full_cycle():
    """몇 번 돌면 화이트리스트 전체가 한 번씩 검색되어야 한다."""
    items = [str(i) for i in range(9)]
    seen = set()
    offset = 0
    for _ in range(3):
        picked = rotate(items, count=3, offset=offset)
        seen.update(picked)
        offset += 3
    assert seen == set(items)
