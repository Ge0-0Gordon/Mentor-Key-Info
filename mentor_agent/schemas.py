"""Pydantic data contracts for mentor key-information extraction V1."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Base model that rejects undeclared fields."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class MappingStatus(str, Enum):
    MAPPED = "mapped"
    UNMAPPED = "unmapped"
    AMBIGUOUS = "ambiguous"


class OrganizationRelationship(str, Enum):
    EMPLOYER = "employer"
    CLIENT = "client"
    PROJECT = "project"
    PARTNER = "partner"
    UNKNOWN = "unknown"


class EmploymentStatus(str, Enum):
    CURRENT = "current"
    FORMER = "former"
    UNKNOWN = "unknown"


class CredentialCategory(str, Enum):
    PROFESSIONAL_CERTIFICATION = "professional_certification"
    TRAINING_CERTIFICATE = "training_certificate"
    COACH_CERTIFICATE = "coach_certificate"
    TEACHING_CERTIFICATE = "teaching_certificate"
    AWARD = "award"
    OTHER = "other"


class CredentialStatus(str, Enum):
    HELD = "held"
    IN_PROGRESS = "in_progress"
    CANDIDATE = "candidate"
    UNKNOWN = "unknown"


class SkillCategory(str, Enum):
    DOMAIN_EXPERTISE = "domain_expertise"
    FUNCTIONAL_SKILL = "functional_skill"
    MANAGEMENT_LEADERSHIP = "management_leadership"
    COACHING_MENTORING = "coaching_mentoring"
    JOB_SEARCH_GUIDANCE = "job_search_guidance"
    TECHNICAL_TOOL = "technical_tool"
    LANGUAGE_COMMUNICATION = "language_communication"
    OTHER = "other"


class EvidenceSourceField(str, Enum):
    MENTOR_NAME = "导师姓名"
    GENDER = "性别"
    CITY = "城市"
    CAREER_YEARS = "职业年限"
    COACHABLE_LEVELS = "可辅导学员职级"
    INDUSTRY_TAGS = "行业标签"
    CAREER_HISTORY = "从业经历"
    BACKGROUND_EXPERIENCE = "背景经验"


class EvidenceMatchType(str, Enum):
    STRICT = "strict"
    LOOSE = "loose"
    INVALID = "invalid"


class QualityIssueSeverity(str, Enum):
    WARNING = "warning"
    ERROR = "error"


class EducationType(str, Enum):
    DEGREE = "degree"
    EXECUTIVE_EDUCATION = "executive_education"
    NON_DEGREE = "non_degree"
    UNKNOWN = "unknown"


class TargetMenteeDimension(str, Enum):
    CAREER_STAGE = "career_stage"
    SENIORITY = "seniority"
    INDUSTRY = "industry"
    JOB_FUNCTION = "job_function"
    SPECIAL_GROUP = "special_group"
    OTHER = "other"


class OriginalFields(StrictModel):
    """The nine source columns, preserved without semantic rewriting."""

    sequence_no: int | float | str | None = Field(alias="序号")
    mentor_name: str | None = Field(alias="导师姓名")
    gender: str | None = Field(alias="性别")
    city: str | None = Field(alias="城市")
    career_years: int | float | str | None = Field(alias="职业年限")
    coachable_levels: str | None = Field(alias="可辅导学员职级")
    industry_tags: str | None = Field(alias="行业标签")
    career_history: str | None = Field(alias="从业经历")
    background_experience: str | None = Field(alias="背景经验")


class MentorInput(StrictModel):
    task: Literal["extract_mentor_key_info"]
    input_schema_version: Literal["1.0"]
    mentor_id: str = Field(min_length=1)
    record_hash: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    source_file: str = Field(min_length=1)
    source_sheet: str = Field(min_length=1)
    source_row: int = Field(ge=1)
    original_fields: OriginalFields


class Evidence(StrictModel):
    source_field: EvidenceSourceField
    quote: str = Field(min_length=1)
    match_type: EvidenceMatchType | None = None


class StandardizedValue(StrictModel):
    raw_value: str = Field(min_length=1)
    normalized_value: str | None
    mapping_status: MappingStatus


class IndustryTag(StrictModel):
    raw_industry: str = Field(min_length=1)
    normalized_industry: str | None
    industry_category: str | None = None
    mapping_status: MappingStatus
    industry_derivation: str | None = None
    evidence: list[Evidence] = Field(min_length=1)
    confidence: Confidence


class CareerExperience(StrictModel):
    raw_name: str = Field(min_length=1)
    normalized_name: str | None
    mapping_status: MappingStatus
    relationship: OrganizationRelationship
    raw_title: str | None = None
    normalized_title: str | None = None
    title_mapping_status: MappingStatus | None = None
    employment_status: EmploymentStatus
    time_period_raw: str | None = None
    context_raw: str | None = None
    evidence: list[Evidence] = Field(min_length=1)
    confidence: Confidence


class Skill(StrictModel):
    raw_skill: str = Field(min_length=1)
    normalized_skill: str | None
    skill_category: SkillCategory | None = None
    mapping_status: MappingStatus
    evidence: list[Evidence] = Field(min_length=1)
    confidence: Confidence


class CredentialAndAward(StrictModel):
    raw_name: str = Field(min_length=1)
    normalized_name: str | None
    mapping_status: MappingStatus
    category: CredentialCategory
    issuer_raw: str | None = None
    issuer_normalized: str | None = None
    issuer_mapping_status: MappingStatus | None = None
    credential_status: CredentialStatus
    evidence: list[Evidence] = Field(min_length=1)
    confidence: Confidence


class Education(StrictModel):
    institution_raw: str = Field(min_length=1)
    institution_normalized: str | None
    institution_mapping_status: MappingStatus
    degree_raw: str | None = None
    degree_normalized: str | None = None
    degree_mapping_status: MappingStatus | None = None
    major_raw: str | None = None
    major_normalized: str | None = None
    major_mapping_status: MappingStatus | None = None
    education_type: EducationType | None = None
    evidence: list[Evidence] = Field(min_length=1)
    confidence: Confidence


class TargetMentee(StrictModel):
    raw_audience: str = Field(min_length=1)
    normalized_audience: str | None
    mapping_status: MappingStatus
    dimension: TargetMenteeDimension | None = None
    evidence: list[Evidence] = Field(min_length=1)
    confidence: Confidence


class Metric(StrictModel):
    name: str | None = None
    value: int | float | str | None = None
    unit: str | None = None
    qualifier: str | None = None


class CareerHighlight(StrictModel):
    type: str | None = None
    statement: str = Field(min_length=1)
    metrics: list[Metric] = Field(default_factory=list)
    evidence: list[Evidence] = Field(min_length=1)
    confidence: Confidence


class MentorSummary(StrictModel):
    value: str = Field(min_length=1)
    evidence: list[Evidence] = Field(min_length=1)
    confidence: Confidence


class QualityIssue(StrictModel):
    code: str = Field(min_length=1)
    severity: QualityIssueSeverity
    path: str | None = None
    source_field: EvidenceSourceField | None = None
    message: str = Field(min_length=1)


class NormalizedProfile(StrictModel):
    name: StandardizedValue | None = None
    gender: StandardizedValue | None = None
    locations: list[StandardizedValue] = Field(default_factory=list)
    career_years: int | None = Field(default=None, ge=0)


class SourceMetadata(StrictModel):
    file: str = Field(min_length=1)
    sheet: str = Field(min_length=1)
    row: int = Field(ge=1)


class ProcessingMetadata(StrictModel):
    status: Literal["success"]
    attempt_count: int = Field(ge=1)
    processed_at: datetime
    model_service_name: str = Field(min_length=1)
    model_name: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)


class MentorExtraction(StrictModel):
    industry_tags: list[IndustryTag] = Field(default_factory=list)
    career_experiences: list[CareerExperience] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    credentials_and_awards: list[CredentialAndAward] = Field(
        default_factory=list
    )
    education: list[Education] = Field(default_factory=list)
    target_mentees: list[TargetMentee] = Field(default_factory=list)
    career_highlights: list[CareerHighlight] = Field(default_factory=list)
    summary: MentorSummary | None = None


class MentorResult(MentorExtraction):
    schema_version: Literal["1.0"]
    prompt_version: str = Field(min_length=1)
    industry_taxonomy_version: str = Field(min_length=1)
    mentor_id: str = Field(min_length=1)
    record_hash: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    source: SourceMetadata
    original_fields: OriginalFields
    normalized_profile: NormalizedProfile = Field(
        default_factory=NormalizedProfile
    )
    quality_issues: list[QualityIssue] = Field(default_factory=list)
    processing: ProcessingMetadata


__all__ = [
    "CareerExperience",
    "CareerHighlight",
    "Confidence",
    "CredentialAndAward",
    "CredentialCategory",
    "CredentialStatus",
    "Education",
    "EducationType",
    "EmploymentStatus",
    "Evidence",
    "EvidenceMatchType",
    "EvidenceSourceField",
    "IndustryTag",
    "MappingStatus",
    "MentorExtraction",
    "MentorInput",
    "MentorResult",
    "MentorSummary",
    "Metric",
    "NormalizedProfile",
    "OrganizationRelationship",
    "OriginalFields",
    "ProcessingMetadata",
    "QualityIssue",
    "QualityIssueSeverity",
    "Skill",
    "SkillCategory",
    "SourceMetadata",
    "StandardizedValue",
    "TargetMentee",
    "TargetMenteeDimension",
]
