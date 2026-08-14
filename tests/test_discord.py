import pytest

from src.models import JobPosting
from src.notifiers.discord import DiscordNotifier, build_embed


def posting(**overrides) -> JobPosting:
    base = dict(
        source="jumpit",
        job_id="1",
        title="백엔드 개발자",
        company="테스트회사",
        url="https://example.com/1",
        tech_stacks=("Java", "Spring"),
        category="서버/백엔드 개발자",
        tags=(),
        career_min=0,
        career_max=0,
        location="서울 강남구",
        deadline="2026-09-12",
    )
    base.update(overrides)
    return JobPosting(**base)


class FakeResponse:
    def __init__(self, status_code=204, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeTransport:
    """디스코드 웹훅 대신 호출 내역만 기록한다."""

    def __init__(self, responses=None):
        self.calls = []
        self._responses = list(responses or [])

    def post(self, url, json):
        self.calls.append((url, json))
        if self._responses:
            return self._responses.pop(0)
        return FakeResponse()


def make_notifier(transport, **kwargs):
    slept = []
    notifier = DiscordNotifier(
        "https://discord.test/webhook", transport=transport, sleep=slept.append, **kwargs
    )
    return notifier, slept


# --- 임베드 생성 -----------------------------------------------------------


def test_embed_title_shows_company_then_position():
    embed = build_embed(posting(), "백엔드 신입")
    assert embed["title"] == "[테스트회사] 백엔드 개발자"


def test_embed_links_to_the_posting():
    assert build_embed(posting(), "p")["url"] == "https://example.com/1"


def test_embed_shows_career_location_and_deadline():
    fields = {f["name"]: f["value"] for f in build_embed(posting(), "p")["fields"]}
    assert fields["경력"] == "신입"
    assert fields["지역"] == "서울 강남구"
    assert fields["마감"] == "2026-09-12"


def test_embed_omits_fields_with_no_data():
    fields = {f["name"] for f in build_embed(posting(location="", deadline="", tech_stacks=()), "p")["fields"]}
    assert "지역" not in fields
    assert "마감" not in fields
    assert "기술스택" not in fields
    # 경력은 정보가 없어도 '경력무관'으로 항상 보여준다
    assert "경력" in fields


def test_embed_shows_employment_type_when_known():
    fields = {f["name"]: f["value"] for f in build_embed(posting(tags=("정규직",)), "p")["fields"]}
    assert fields["고용형태"] == "정규직"


def test_embed_omits_employment_type_when_unknown():
    fields = {f["name"] for f in build_embed(posting(tags=()), "p")["fields"]}
    assert "고용형태" not in fields


def test_embed_footer_names_the_site_and_profile():
    assert build_embed(posting(), "백엔드 신입")["footer"]["text"] == "점핏 · 백엔드 신입"


def test_embed_title_is_truncated_to_discord_limit():
    embed = build_embed(posting(title="가" * 400), "p")
    assert len(embed["title"]) <= 256


def test_embed_tech_stack_value_is_truncated_to_discord_limit():
    embed = build_embed(posting(tech_stacks=tuple(f"기술{i}" for i in range(400))), "p")
    value = next(f["value"] for f in embed["fields"] if f["name"] == "기술스택")
    assert len(value) <= 1024


# --- 전송 -----------------------------------------------------------------


def test_all_postings_are_delivered():
    transport = FakeTransport()
    notifier, _ = make_notifier(transport)
    sent = notifier.send([posting(job_id=str(i)) for i in range(3)], "백엔드 신입")
    assert sent == 3
    assert len(transport.calls) == 1


def test_batches_are_capped_at_ten_embeds_per_request():
    transport = FakeTransport()
    notifier, _ = make_notifier(transport)
    sent = notifier.send([posting(job_id=str(i)) for i in range(25)], "백엔드 신입")
    assert sent == 25
    assert len(transport.calls) == 3
    assert [len(call[1]["embeds"]) for call in transport.calls] == [10, 10, 5]


def test_empty_posting_list_sends_nothing():
    transport = FakeTransport()
    notifier, _ = make_notifier(transport)
    assert notifier.send([], "p") == 0
    assert transport.calls == []


def test_rate_limited_request_is_retried_after_waiting():
    transport = FakeTransport([FakeResponse(429, {"retry_after": 1.5}), FakeResponse(204)])
    notifier, slept = make_notifier(transport)
    sent = notifier.send([posting()], "p")
    assert sent == 1
    assert len(transport.calls) == 2
    assert 1.5 in slept


def test_gives_up_after_repeated_rate_limits_without_crashing():
    transport = FakeTransport([FakeResponse(429, {"retry_after": 0.1})] * 10)
    notifier, _ = make_notifier(transport, max_retries=3)
    assert notifier.send([posting()], "p") == 0


def test_server_error_batch_is_not_counted_as_sent():
    transport = FakeTransport([FakeResponse(500)] * 10)
    notifier, _ = make_notifier(transport, max_retries=2)
    assert notifier.send([posting()], "p") == 0


def test_one_failed_batch_does_not_stop_the_next_batch():
    # max_retries=1 이므로 배치마다 응답을 하나씩 소비한다.
    transport = FakeTransport([FakeResponse(500), FakeResponse(204)])
    notifier, _ = make_notifier(transport, max_retries=1)
    sent = notifier.send([posting(job_id=str(i)) for i in range(15)], "p")
    # 첫 배치(10건)는 실패했지만 두 번째 배치(5건)는 그대로 전송된다
    assert sent == 5
    assert len(transport.calls) == 2


def test_missing_webhook_url_is_rejected_early():
    with pytest.raises(ValueError):
        DiscordNotifier("", transport=FakeTransport())
