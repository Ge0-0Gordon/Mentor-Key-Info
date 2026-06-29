"""Short prompt for fast keyword-only mentor extraction."""

from __future__ import annotations

import json

from .schemas import MentorInput
from .simple_schemas import SIMPLE_PROMPT_VERSION, TAGGED_SIMPLE_PROMPT_VERSION
from .tag_taxonomy import TagTaxonomy


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

TAGGED_SIMPLE_EXTRACTION_SYSTEM_PROMPT = """
你负责从导师原始资料中抽取旧版关键词和标准标签。只输出合法 JSON 对象，不要解释。
industry_tags.tag 和 company_tags.industry_tag 只能逐字选择 industry_tag_candidates。
position_tags.tag 只能逐字选择 position_tag_candidates；职位分组标题不是标签。
行业和职位必须分开。不能因职位常见于某行业就自动添加行业标签。
不要因职业规划、培训、教练或咨询自动添加教育或咨询行业。
标准标签 evidence 必须直接摘自行业标签、从业经历、背景经验或可辅导学员职级。
relation_type 只能是 firsthand_role、managed_team、recruited_or_evaluated、related。
导师招聘或评估过某岗位不等于本人做过该岗位，例如 HR 招聘算法岗应使用 recruited_or_evaluated。
不要生成 review_required 或 review_reasons；它们由程序计算。没有信息就返回空数组或 null。
""".strip()

TAGGED_SIMPLE_BATCH_EXTRACTION_SYSTEM_PROMPT = """
你是导师关键词和标准标签批量抽取器。每条记录独立处理，不要混淆 mentor_id。
标准行业和职位只能逐字选择候选池，职位分组不是标签，行业与职位必须分开。
不能从职位自动推导行业。标准标签 evidence 只能摘自行业标签、从业经历、背景经验或可辅导学员职级。
relation_type 只能是 firsthand_role、managed_team、recruited_or_evaluated、related。
HR 招聘或评估某岗位应使用 recruited_or_evaluated，不能使用 firsthand_role。
不要生成 review_required 或 review_reasons；它们由程序计算。只输出合法 JSON。
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

TAGGED_SIMPLE_OUTPUT_TEMPLATE = {
    **SIMPLE_OUTPUT_TEMPLATE,
    "industry_tags": [
        {
            "tag": "候选池中的行业标签",
            "confidence": 0.0,
            "evidence": "允许字段中的原文片段",
        }
    ],
    "position_tags": [
        {
            "tag": "候选池中的职位标签",
            "relation_type": "firsthand_role",
            "confidence": 0.0,
            "raw_keywords": [],
            "evidence": "允许字段中的原文片段",
        }
    ],
    "company_tags": [
        {
            "company_name": "原文公司名",
            "company_type": None,
            "industry_tag": None,
            "evidence": "允许字段中的原文片段",
            "confidence": 0.0,
        }
    ],
    "raw_keywords": [],
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


def build_tagged_simple_extraction_messages(
    mentor_input: MentorInput,
    taxonomy: TagTaxonomy,
) -> list[dict[str, str]]:
    """Build one standard-tag request with closed candidate pools."""

    payload = {
        "task": "extract_mentor_keywords_tagged_simple",
        "prompt_version": TAGGED_SIMPLE_PROMPT_VERSION,
        "industry_tag_candidates": list(taxonomy.industry_tags),
        "position_tag_candidates": list(taxonomy.position_tags),
        "original_fields": mentor_input.original_fields.model_dump(
            by_alias=True,
            mode="json",
        ),
        "output_template": TAGGED_SIMPLE_OUTPUT_TEMPLATE,
    }
    return [
        {"role": "system", "content": TAGGED_SIMPLE_EXTRACTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        },
    ]


def build_tagged_simple_batch_extraction_messages(
    mentor_inputs: list[MentorInput],
    taxonomy: TagTaxonomy,
) -> list[dict[str, str]]:
    """Build one tagged batch request with shared candidate pools."""

    payload = {
        "task": "extract_mentor_keywords_batch_tagged_simple",
        "prompt_version": TAGGED_SIMPLE_PROMPT_VERSION,
        "industry_tag_candidates": list(taxonomy.industry_tags),
        "position_tag_candidates": list(taxonomy.position_tags),
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
                    "extraction": TAGGED_SIMPLE_OUTPUT_TEMPLATE,
                }
            ]
        },
    }
    return [
        {
            "role": "system",
            "content": TAGGED_SIMPLE_BATCH_EXTRACTION_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        },
    ]


__all__ = [
    "SIMPLE_BATCH_EXTRACTION_SYSTEM_PROMPT",
    "SIMPLE_EXTRACTION_SYSTEM_PROMPT",
    "SIMPLE_OUTPUT_TEMPLATE",
    "TAGGED_SIMPLE_BATCH_EXTRACTION_SYSTEM_PROMPT",
    "TAGGED_SIMPLE_EXTRACTION_SYSTEM_PROMPT",
    "TAGGED_SIMPLE_OUTPUT_TEMPLATE",
    "build_simple_batch_extraction_messages",
    "build_simple_extraction_messages",
    "build_tagged_simple_batch_extraction_messages",
    "build_tagged_simple_extraction_messages",
]
