"""Fast rule-based student query parsing."""

from __future__ import annotations

import re

from .aliases import AliasIndex, unique_keep_order
from .schemas import StudentProfile


_KEYWORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9+#.-]{1,}|[\u4e00-\u9fff]{2,}")


def _keywords(query: str, alias_terms: list[str]) -> list[str]:
    tokens = _KEYWORD_PATTERN.findall(query)
    return unique_keep_order([*alias_terms, *tokens])[:30]


def extract_student_profile(query: str, aliases: AliasIndex) -> StudentProfile:
    """Parse a student query without an online model call."""

    target_industries = aliases.find_in_text("industries", query)
    target_companies = aliases.find_in_text("companies", query)
    target_roles = aliases.find_in_text("roles", query)
    current_stage = aliases.find_in_text("stages", query)
    needed_help = aliases.find_in_text("skills", query)
    preferred_background = unique_keep_order(
        [
            *target_industries,
            *target_companies,
            *target_roles,
        ]
    )
    alias_terms = unique_keep_order(
        [
            *target_industries,
            *target_companies,
            *target_roles,
            *current_stage,
            *needed_help,
        ]
    )
    missing_fields = []
    if not target_companies and not target_industries:
        missing_fields.append("target_companies_or_industries")
    if not target_roles:
        missing_fields.append("target_roles")
    if not needed_help:
        missing_fields.append("needed_help")
    if not current_stage:
        missing_fields.append("current_stage")

    filled = 4 - len(missing_fields)
    confidence = "high" if filled >= 3 else "medium" if filled >= 2 else "low"
    return StudentProfile(
        raw_query=query,
        target_industries=target_industries,
        target_companies=target_companies,
        target_roles=target_roles,
        current_stage=current_stage,
        needed_help=needed_help,
        preferred_background=preferred_background,
        keywords=_keywords(query, alias_terms),
        confidence=confidence,
        missing_fields=missing_fields,
    )


def clarification_questions(profile: StudentProfile) -> list[str]:
    questions = []
    if "target_companies_or_industries" in profile.missing_fields:
        questions.append("你目标行业或目标公司是什么？")
    if "target_roles" in profile.missing_fields:
        questions.append("你想申请的岗位方向是什么？")
    if "needed_help" in profile.missing_fields:
        questions.append("你主要需要简历、面试、职业规划还是转行辅导？")
    if "current_stage" in profile.missing_fields:
        questions.append("你现在是应届生、留学生、在职跳槽还是管理层？")
    return questions


__all__ = ["clarification_questions", "extract_student_profile"]
