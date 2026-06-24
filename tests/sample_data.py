"""Anonymous synthetic records used by schema tests."""

VALID_ORIGINAL_FIELDS = {
    "序号": 1,
    "导师姓名": "林清（化名）",
    "性别": "女",
    "城市": "杭州",
    "职业年限": 12,
    "可辅导学员职级": "应届生, P5-P6专员级",
    "行业标签": "互联网、海洋科技",
    "从业经历": (
        "曾任星河网络有限公司人才发展经理。"
        "为云帆零售有限公司提供招聘咨询服务。"
        "参与海岸研究院人才盘点项目。"
        "与远山公益基金会合作开展职业课程。"
        "个人介绍中另提及启明协会，未说明具体关系。"
    ),
    "背景经验": (
        "擅长简历优化、结构化面试辅导和跨学科职业路径设计。"
        "持有星光生涯教练认证。累计辅导200人次。"
    ),
}


VALID_MENTOR_INPUT = {
    "task": "extract_mentor_key_info",
    "input_schema_version": "1.0",
    "mentor_id": "service_mentor:1",
    "record_hash": "a" * 64,
    "source_file": "synthetic_mentors.xlsx",
    "source_sheet": "服务导师",
    "source_row": 2,
    "original_fields": VALID_ORIGINAL_FIELDS,
}


VALID_MENTOR_RESULT = {
    "schema_version": "1.0",
    "prompt_version": "mentor-extraction-v1",
    "industry_taxonomy_version": "industry-soft-v1",
    "mentor_id": "service_mentor:1",
    "record_hash": "a" * 64,
    "source": {
        "file": "synthetic_mentors.xlsx",
        "sheet": "服务导师",
        "row": 2,
    },
    "original_fields": VALID_ORIGINAL_FIELDS,
    "normalized_profile": {
        "name": {
            "raw_value": "林清（化名）",
            "normalized_value": "林清",
            "mapping_status": "mapped",
        },
        "gender": {
            "raw_value": "女",
            "normalized_value": "女",
            "mapping_status": "mapped",
        },
        "locations": [
            {
                "raw_value": "杭州",
                "normalized_value": "杭州",
                "mapping_status": "mapped",
            }
        ],
        "career_years": 12,
    },
    "industry_tags": [
        {
            "raw_industry": "互联网",
            "normalized_industry": "互联网与平台经济",
            "industry_category": "互联网与平台经济",
            "mapping_status": "mapped",
            "industry_derivation": "original_industry_field",
            "evidence": [
                {"source_field": "行业标签", "quote": "互联网"}
            ],
            "confidence": "high",
        },
        {
            "raw_industry": "海洋科技",
            "normalized_industry": "海洋科技",
            "industry_category": "other",
            "mapping_status": "unmapped",
            "evidence": [
                {"source_field": "行业标签", "quote": "海洋科技"}
            ],
            "confidence": "high",
        },
    ],
    "career_experiences": [
        {
            "raw_name": "星河网络有限公司",
            "normalized_name": "星河网络",
            "mapping_status": "mapped",
            "relationship": "employer",
            "raw_title": "人才发展经理",
            "normalized_title": "人才发展经理",
            "title_mapping_status": "mapped",
            "employment_status": "former",
            "evidence": [
                {
                    "source_field": "从业经历",
                    "quote": "曾任星河网络有限公司人才发展经理",
                }
            ],
            "confidence": "high",
        },
        {
            "raw_name": "云帆零售有限公司",
            "normalized_name": "云帆零售",
            "mapping_status": "mapped",
            "relationship": "client",
            "employment_status": "unknown",
            "evidence": [
                {
                    "source_field": "从业经历",
                    "quote": "为云帆零售有限公司提供招聘咨询服务",
                }
            ],
            "confidence": "high",
        },
        {
            "raw_name": "海岸研究院",
            "normalized_name": "海岸研究院",
            "mapping_status": "unmapped",
            "relationship": "project",
            "employment_status": "unknown",
            "context_raw": "人才盘点项目",
            "evidence": [
                {
                    "source_field": "从业经历",
                    "quote": "参与海岸研究院人才盘点项目",
                }
            ],
            "confidence": "high",
        },
        {
            "raw_name": "远山公益基金会",
            "normalized_name": "远山公益基金会",
            "mapping_status": "unmapped",
            "relationship": "partner",
            "employment_status": "unknown",
            "evidence": [
                {
                    "source_field": "从业经历",
                    "quote": "与远山公益基金会合作开展职业课程",
                }
            ],
            "confidence": "high",
        },
        {
            "raw_name": "启明协会",
            "normalized_name": None,
            "mapping_status": "ambiguous",
            "relationship": "unknown",
            "employment_status": "unknown",
            "evidence": [
                {
                    "source_field": "从业经历",
                    "quote": "提及启明协会，未说明具体关系",
                }
            ],
            "confidence": "medium",
        },
    ],
    "skills": [
        {
            "raw_skill": "跨学科职业路径设计",
            "normalized_skill": "跨学科职业路径设计",
            "skill_category": "coaching_mentoring",
            "mapping_status": "unmapped",
            "evidence": [
                {
                    "source_field": "背景经验",
                    "quote": "跨学科职业路径设计",
                }
            ],
            "confidence": "high",
        }
    ],
    "credentials_and_awards": [
        {
            "raw_name": "星光生涯教练认证",
            "normalized_name": "星光生涯教练认证",
            "mapping_status": "unmapped",
            "category": "coach_certificate",
            "credential_status": "held",
            "evidence": [
                {
                    "source_field": "背景经验",
                    "quote": "持有星光生涯教练认证",
                }
            ],
            "confidence": "high",
        }
    ],
    "target_mentees": [
        {
            "raw_audience": "应届生",
            "normalized_audience": "应届生",
            "mapping_status": "mapped",
            "dimension": "career_stage",
            "evidence": [
                {
                    "source_field": "可辅导学员职级",
                    "quote": "应届生",
                }
            ],
            "confidence": "high",
        }
    ],
    "career_highlights": [
        {
            "statement": "累计辅导200人次",
            "evidence": [
                {"source_field": "背景经验", "quote": "累计辅导200人次"}
            ],
            "confidence": "high",
        }
    ],
    "summary": {
        "value": "具有人才发展、求职辅导和跨学科职业路径设计经验。",
        "evidence": [
            {"source_field": "背景经验", "quote": "跨学科职业路径设计"}
        ],
        "confidence": "medium",
    },
    "quality_issues": [
        {
            "code": "unmapped_industry",
            "severity": "warning",
            "path": "industry_tags[1]",
            "source_field": "行业标签",
            "message": "海洋科技未映射到 soft taxonomy，已保留原值。",
        }
    ],
    "processing": {
        "status": "success",
        "attempt_count": 1,
        "processed_at": "2026-06-24T10:00:00+08:00",
        "model_service_name": "synthetic-test-service",
        "model_name": "synthetic-test-model",
        "latency_ms": 120,
    },
}


MINIMAL_VALID_RESULT = {
    "schema_version": "1.0",
    "prompt_version": "mentor-extraction-v1",
    "industry_taxonomy_version": "industry-soft-v1",
    "mentor_id": "service_mentor:1",
    "record_hash": "a" * 64,
    "source": {
        "file": "synthetic_mentors.xlsx",
        "sheet": "服务导师",
        "row": 2,
    },
    "original_fields": VALID_ORIGINAL_FIELDS,
    "processing": {
        "status": "success",
        "attempt_count": 1,
        "processed_at": "2026-06-24T10:00:00+08:00",
        "model_service_name": "synthetic-test-service",
    },
}
