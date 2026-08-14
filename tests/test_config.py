"""config.yaml 파싱 규칙 테스트."""

import pytest

from src.config import ConfigError, load_config


def write(tmp_path, body: str):
    p = tmp_path / "config.yaml"
    p.write_text(body, encoding="utf-8")
    return p


BASE = """
profiles:
  - name: 테스트
    sources: [jumpit]
    keywords:
{keywords}
"""


def load_keywords(tmp_path, keywords_block: str):
    path = write(tmp_path, BASE.format(keywords=keywords_block))
    return load_config(path).profiles[0].keywords


def test_plain_all_word_becomes_a_single_member_group(tmp_path):
    kw = load_keywords(tmp_path, '      all: ["Java"]')
    assert kw.all == (("Java",),)


def test_all_entry_written_as_a_list_becomes_an_or_group(tmp_path):
    kw = load_keywords(tmp_path, '      all: [["Java", "Kotlin"]]')
    assert kw.all == (("Java", "Kotlin"),)


def test_all_can_mix_plain_words_and_or_groups(tmp_path):
    kw = load_keywords(tmp_path, '      all: ["백엔드", ["Java", "Kotlin"]]')
    assert kw.all == (("백엔드",), ("Java", "Kotlin"))


def test_empty_all_is_allowed(tmp_path):
    assert load_keywords(tmp_path, "      all: []").all == ()


def test_empty_group_inside_all_is_dropped(tmp_path):
    kw = load_keywords(tmp_path, '      all: [[], ["Java"]]')
    assert kw.all == (("Java",),)


def test_any_and_none_stay_flat_lists(tmp_path):
    kw = load_keywords(tmp_path, '      any: ["백엔드"]\n      none: ["인턴"]')
    assert kw.any == ("백엔드",)
    assert kw.none == ("인턴",)


def test_nested_list_in_any_is_rejected_with_a_helpful_message(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_keywords(tmp_path, '      any: [["Java", "Kotlin"]]')
    assert "any" in str(e.value)
