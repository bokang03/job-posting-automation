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
        include_companies=(),
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


def test_java_does_not_match_javascript_in_tech_stack():
    """영어 기술명은 단어 단위로 봐야 한다. 이걸 놓치면 JavaScript 공고가 Java 공고로 잡힌다."""
    p = posting(title="Vision Field Application Engineer", category="",
                tech_stacks=("C++", "JavaScript", "Qt", "OpenCV"))
    assert not matches_profile(p, profile(keywords=KeywordSpec(any=("Java",), all=(), none=())))


def test_java_matches_an_exact_java_tech_stack_entry():
    p = posting(title="서버 개발자", category="", tech_stacks=("Java", "Spring"))
    assert matches_profile(p, profile(keywords=KeywordSpec(any=("Java",), all=(), none=())))


def test_java_matches_when_the_title_says_java():
    p = posting(title="JAVA 주니어 경력 개발부문 채용", category="", tech_stacks=())
    assert matches_profile(p, profile(keywords=KeywordSpec(any=("Java",), all=(), none=())))


def test_partial_word_prefix_still_matches_a_longer_tech_name():
    """'Spring' 으로 'Spring Boot' 는 잡혀야 한다. 공백이 단어 경계이기 때문이다."""
    p = posting(title="서버 개발자", category="", tech_stacks=("Spring Boot",))
    assert matches_profile(p, profile(keywords=KeywordSpec(any=("Spring",), all=(), none=())))


def test_korean_keyword_still_matches_inside_a_compound_word():
    """한국어는 띄어쓰기가 없어도 매칭돼야 한다."""
    p = posting(title="백엔드개발자 채용", category="", tech_stacks=())
    assert matches_profile(p, profile(keywords=KeywordSpec(any=("백엔드",), all=(), none=())))


def test_none_keyword_also_respects_word_boundaries():
    p = posting(title="백엔드 개발자", category="", tech_stacks=("JavaScript",))
    assert matches_profile(p, profile(keywords=KeywordSpec(any=("백엔드",), all=(), none=("Java",))))


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
    spec = KeywordSpec(any=(), all=(("백엔드",), ("Spring",)), none=())
    assert matches_profile(posting(title="백엔드 개발자", tech_stacks=("Spring",)), profile(keywords=spec))
    assert not matches_profile(
        posting(title="백엔드 개발자", tech_stacks=("Django",), category=""), profile(keywords=spec)
    )


def test_all_group_passes_when_any_member_of_the_group_is_present():
    """'Java 또는 Kotlin 중 하나는 반드시' 를 표현한다."""
    spec = KeywordSpec(any=(), all=(("Java", "Kotlin"),), none=())
    assert matches_profile(posting(title="서버 개발자", tech_stacks=("Kotlin",)), profile(keywords=spec))
    assert matches_profile(posting(title="서버 개발자", tech_stacks=("Java",)), profile(keywords=spec))


def test_all_group_rejects_when_no_member_of_the_group_is_present():
    spec = KeywordSpec(any=(), all=(("Java", "Kotlin"),), none=())
    assert not matches_profile(
        posting(title="서버 개발자", category="", tech_stacks=("Python", "Django")), profile(keywords=spec)
    )


def test_every_all_group_must_be_satisfied():
    """직무 조건 AND 언어 조건 — 둘 다 만족해야 통과."""
    spec = KeywordSpec(any=(), all=(("백엔드", "서버"), ("Java", "Kotlin")), none=())
    assert matches_profile(posting(title="백엔드 개발자", tech_stacks=("Java",)), profile(keywords=spec))
    # 언어는 맞지만 직무가 아님
    assert not matches_profile(
        posting(title="안드로이드 개발자", category="", tech_stacks=("Kotlin",)), profile(keywords=spec)
    )
    # 직무는 맞지만 언어가 아님
    assert not matches_profile(
        posting(title="백엔드 개발자", category="", tech_stacks=("Python",)), profile(keywords=spec)
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


# --- 회사 화이트리스트 -----------------------------------------------------


def test_empty_company_whitelist_allows_every_company():
    assert matches_profile(posting(company="아무회사"), profile(include_companies=()))


def test_whitelisted_company_passes():
    p = posting(company="KB국민은행")
    assert matches_profile(p, profile(include_companies=("국민은행", "하나은행")))


def test_company_not_on_the_whitelist_is_rejected():
    p = posting(company="이름없는스타트업")
    assert not matches_profile(p, profile(include_companies=("국민은행", "하나은행")))


def test_whitelist_matches_company_name_with_prefix_and_suffix():
    p = posting(company="㈜하나금융티아이")
    assert matches_profile(p, profile(include_companies=("하나금융티아이",)))


def test_short_english_whitelist_entry_respects_word_boundaries():
    """'KB' 가 'KBS미디어' 같은 무관한 회사에 걸리면 안 된다."""
    assert matches_profile(posting(company="KB증권"), profile(include_companies=("KB",)))
    assert not matches_profile(posting(company="KBS미디어"), profile(include_companies=("KB",)))


def test_exclusion_wins_over_whitelist():
    p = posting(company="국민은행")
    assert not matches_profile(
        p, profile(include_companies=("국민은행",), exclude_companies=("국민은행",))
    )


def test_whitelist_is_checked_independently_of_keywords():
    """회사가 명단에 있어도 직무 키워드 조건은 그대로 적용된다."""
    p = posting(company="국민은행", title="경비원 모집", category="", tech_stacks=())
    prof = profile(include_companies=("국민은행",), keywords=KeywordSpec(any=("개발",), all=(), none=()))
    assert not matches_profile(p, prof)
