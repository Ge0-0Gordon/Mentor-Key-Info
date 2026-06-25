"""Short prompt for fast keyword-only mentor extraction."""

from __future__ import annotations

import json

from .schemas import MentorInput
from .simple_schemas import SIMPLE_PROMPT_VERSION


SIMPLE_EXTRACTION_SYSTEM_PROMPT = """
你负责从单条导师资料中快速提取关键词。只输出一个合法 JSON 对象。
不要 Markdown，不要代码块，不要解释过程。不要编造；没有信息就返回 [] 或 null。
数组去重，每类最多 20 个。summary 只基于原文事实，不超过 100 个中文字符。
""".strip()

SIMPLE_BATCH_EXTRACTION_SYSTEM_PROMPT = """
你是导师关键词批量抽取器。每条记录独立处理，不要混淆不同 mentor_id。
只输出合法 JSON，不要 Markdown，不要代码块，不要解释过程。不要编造。
没有信息返回 [] 或 null。数组去重，每类最多 20 个。summary 不超过 100 个中文字符。
""".strip()

SIMPLE_OUTPUT_TEMPLATE = {
    "industries": [],
    "companies": [],
    "roles": [],
    "skills": [],
    "credentials": [],
    "education": [],
    "target_mentees": [],
    "highlights": [],
    "keywords": [],
    "summary": None,
}


def build_simple_extraction_messages(
    mentor_input: MentorInput,
) -> list[dict[str, str]]:
    """Build a compact request for simple keyword extraction."""

    payload = {
        "task": "extract_mentor_keywords_simple",
        "prompt_version": SIMPLE_PROMPT_VERSION,
        "original_fields": mentor_input.original_fields.model_dump(
            by_alias=True,
            mode="json",
        ),
        "output_template": SIMPLE_OUTPUT_TEMPLATE,
    }
    return [
        {"role": "system", "content": SIMPLE_EXTRACTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        },
    ]


def build_simple_batch_extraction_messages(
    mentor_inputs: list[MentorInput],
) -> list[dict[str, str]]:
    """Build a compact batch request for simple keyword extraction."""

    payload = {
        "task": "extract_mentor_keywords_batch_simple",
        "records": [
            {
                "mentor_id": mentor_input.mentor_id,
                "original_fields": mentor_input.original_fields.model_dump(
                    by_alias=True,
                    mode="json",
                ),
            }
            for mentor_input in mentor_inputs
        ],
        "output_format": {
            "results": [
                {
                    "mentor_id": "service_mentor:1",
                    "extraction": SIMPLE_OUTPUT_TEMPLATE,
                }
            ]
        },
    }
    return [
        {"role": "system", "content": SIMPLE_BATCH_EXTRACTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        },
    ]


__all__ = [
    "SIMPLE_BATCH_EXTRACTION_SYSTEM_PROMPT",
    "SIMPLE_EXTRACTION_SYSTEM_PROMPT",
    "SIMPLE_OUTPUT_TEMPLATE",
    "build_simple_batch_extraction_messages",
    "build_simple_extraction_messages",
]
