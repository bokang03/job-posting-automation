from src.config import CareerSpec, KeywordSpec, Profile
from src.filters import matches_profile
from src.models import JobPosting


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
        deadline="",
    )
    base.update(overrides)
    return JobPosting(**base)


def profile(**overrides) -> Profile:
    base = dict(
        name="백엔드 신입",
        enabled=True,
        sources=("jumpit",),
        keywords=KeywordSpec(any=("백엔드",), all=(), none=()),
        career=CareerSpec(min_years=0, max_years=0, include_irrelevant=True),
        locations=(),
        exclude_companies=(),
        search_queries=(),
        webhook_env="DISCORD_WEBHOOK_URL",
    )
    base.update(overrides)
    return Profile(**base)


# --- 키워드 ---------------------------------------------------------------


def test_any_keyword_matching_title_passes():
    assert matches_profile(posting(title="백엔드 개발자"), profile())


def test_posting_without_any_keyword_is_rejected():
    assert not matches_profile(posting(title="iOS 개발자", category="모바일", tech_stacks=("Swift",)), profile())


def test_any_keyword_matches_tech_stack_even_if_title_lacks_it():
    p = posting(title="주니어 개발자 채용", category="", tech_stacks=("Spring", "MySQL"))
    assert matches_profile(p, profile(keywords=KeywordSpec(any=("Spring",), all=(), none=())))


def test_keyword_matching_is_case_insensitive():
    p = posting(title="Backend Engineer", category="", tech_stacks=())
    assert matches_profile(p, profile(keywords=KeywordSpec(any=("backend",), all=(), none=())))


def test_empty_any_list_means_no_keyword_restriction():
    p = posting(title="완전히 무관한 공고", category="", tech_stacks=())
    assert matches_profile(p, profile(keywords=KeywordSpec(any=(), all=(), none=())))


def test_none_keyword_in_title_rejects_even_when_any_matches():
    p = posting(title="백엔드 개발 인턴")
    assert not matches_profile(p, profile(keywords=KeywordSpec(any=("백엔드",), all=(), none=("인턴",))))


def test_none_keyword_in_tech_stack_rejects():
    p = posting(title="백엔드 개발자", tech_stacks=("PHP", "MySQL"))
    assert not matches_profile(p, profile(keywords=KeywordSpec(any=("백엔드",), all=(), none=("PHP",))))


def test_none_keyword_in_employment_tag_rejects():
    p = posting(title="백엔드 개발자", tags=("인턴",))
    assert not matches_profile(p, profile(keywords=KeywordSpec(any=("백엔드",), all=(), none=("인턴",))))


def test_none_keyword_in_broad_category_list_does_not_reject():
    """잡코리아 직무분류는 한 공고에 여러 직무를 나열한다.

    '백엔드개발자, 프론트엔드개발자'처럼 둘 다 뽑는 공고를
    '프론트엔드' 제외 키워드 때문에 버리면 안 된다.
    """
    p = posting(
        title="[안랩] 2026년 연구소 상시채용",
        category="정보보안, 백엔드개발자, 프론트엔드개발자, 웹개발자",
        tech_stacks=(),
    )
    spec = KeywordSpec(any=("백엔드",), all=(), none=("프론트엔드",))
    assert matches_profile(p, profile(keywords=spec))


def test_any_keyword_still_matches_against_broad_category():
    p = posting(title="2026년 연구소 상시채용", category="정보보안, 백엔드개발자", tech_stacks=())
    assert matches_profile(p, profile(keywords=KeywordSpec(any=("백엔드",), all=(), none=())))


def test_all_keywords_must_be_present():
    spec = KeywordSpec(any=(), all=("백엔드", "Spring"), none=())
    assert matches_profile(posting(title="백엔드 개발자", tech_stacks=("Spring",)), profile(keywords=spec))
    assert not matches_profile(
        posting(title="백엔드 개발자", tech_stacks=("Django",), category=""), profile(keywords=spec)
    )


# --- 경력 -----------------------------------------------------------------


def test_newgrad_profile_accepts_newgrad_posting():
    p = posting(career_min=0, career_max=0)
    assert matches_profile(p, profile(career=CareerSpec(0, 0, True)))


def test_newgrad_profile_accepts_posting_open_to_zero_through_three_years():
    p = posting(career_min=0, career_max=3)
    assert matches_profile(p, profile(career=CareerSpec(0, 0, True)))


def test_newgrad_profile_rejects_five_year_minimum_posting():
    p = posting(career_min=5, career_max=12)
    assert not matches_profile(p, profile(career=CareerSpec(0, 0, True)))


def test_widening_max_years_to_five_lets_five_year_posting_through():
    p = posting(career_min=5, career_max=12)
    assert matches_profile(p, profile(career=CareerSpec(0, 5, True)))


def test_posting_with_no_upper_bound_matches_when_minimum_is_reachable():
    p = posting(career_min=3, career_max=None)
    assert matches_profile(p, profile(career=CareerSpec(0, 3, True)))


def test_career_irrelevant_posting_included_when_flag_true():
    p = posting(career_min=None, career_max=None)
    assert matches_profile(p, profile(career=CareerSpec(0, 0, True)))


def test_career_irrelevant_posting_excluded_when_flag_false():
    p = posting(career_min=None, career_max=None)
    assert not matches_profile(p, profile(career=CareerSpec(0, 0, False)))


def test_experienced_only_profile_rejects_newgrad_posting():
    p = posting(career_min=0, career_max=0)
    assert not matches_profile(p, profile(career=CareerSpec(3, 7, False)))


# --- 지역 -----------------------------------------------------------------


def test_location_filter_matches_by_prefix():
    assert matches_profile(posting(location="서울 강남구"), profile(locations=("서울",)))


def test_location_filter_rejects_other_regions():
    assert not matches_profile(posting(location="부산 해운대구"), profile(locations=("서울", "경기")))


def test_empty_location_list_allows_everywhere():
    assert matches_profile(posting(location="제주 서귀포시"), profile(locations=()))


def test_posting_without_location_is_kept_when_filter_set():
    """지역 정보를 안 주는 공고까지 버리면 놓치는 게 많아 통과시킨다."""
    assert matches_profile(posting(location=""), profile(locations=("서울",)))


# --- 회사 제외 -------------------------------------------------------------


def test_excluded_company_is_rejected():
    p = posting(company="싫은회사")
    assert not matches_profile(p, profile(exclude_companies=("싫은회사",)))


def test_excluded_company_matches_partially():
    p = posting(company="(주)싫은회사코리아")
    assert not matches_profile(p, profile(exclude_companies=("싫은회사",)))
