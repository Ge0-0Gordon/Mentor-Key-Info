"""Thin AgentRun server entry point for single-mentor extraction.

Set EXTRACTION_MODE=simple or EXTRACTION_MODE=full before starting this
service. The value is read at startup, so restart python main.py after changing
it. The default is simple.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import ValidationError

from agentrun.integration.langchain import model
from agentrun.server import AgentRequest, AgentRunServer
from agentrun.utils.log import logger

from mentor_agent.extractor import ExtractionError, extract_single_mentor
from mentor_agent.schemas import MentorInput
from mentor_agent.simple_extractor import (
    extract_simple_mentor,
    extract_simple_mentor_batch,
    make_simple_batch_result,
)
from mentor_agent.tag_taxonomy import TagTaxonomy, load_tag_taxonomy


class Stage4RequestError(ValueError):
    """Safe request error whose message contains no source record content."""


def _boolean_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"{name} must be 'true' or 'false'")


load_dotenv()
MODEL_NAME = os.getenv("MODEL_NAME")
MODEL_SERVICE_NAME = os.getenv("MODEL_SERVICE_NAME")
SANDBOX_NAME = os.getenv("SANDBOX_NAME")
EXTRACTION_MODE = os.getenv("EXTRACTION_MODE", "simple").strip().lower()
ENABLE_STANDARD_TAGS = _boolean_env("ENABLE_STANDARD_TAGS", False)
TAG_TAXONOMY_PATH = Path(
    os.getenv("TAG_TAXONOMY_PATH", "configs/职位类型_2.txt")
)

if not MODEL_SERVICE_NAME:
    raise ValueError("MODEL_SERVICE_NAME is required")
if EXTRACTION_MODE not in {"simple", "full"}:
    raise ValueError("EXTRACTION_MODE must be 'simple' or 'full'")

tag_taxonomy: TagTaxonomy | None = None
if EXTRACTION_MODE == "simple" and ENABLE_STANDARD_TAGS:
    tag_taxonomy = load_tag_taxonomy(TAG_TAXONOMY_PATH)

model_client = model(MODEL_SERVICE_NAME, model=MODEL_NAME)


def _last_user_content(request: AgentRequest) -> str:
    for message in reversed(request.messages):
        if message.role == "user":
            if not isinstance(message.content, str):
                raise Stage4RequestError(
                    "last user message content must be a JSON string"
                )
            return message.content
    raise Stage4RequestError("request must contain a user message")


def _parse_json_content(content: str) -> Any:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        raise Stage4RequestError(
            "last user message content must be valid JSON"
        ) from None


def _parse_mentor_input_payload(payload: Any) -> MentorInput:
    try:
        return MentorInput.model_validate(payload)
    except ValidationError as exc:
        raise Stage4RequestError(
            f"invalid MentorInput ({exc.error_count()} validation error(s))"
        ) from None


def _is_simple_batch_payload(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and payload.get("task") == "extract_mentor_keywords_batch_simple"
    )


def _parse_simple_batch_payload(payload: Any) -> list[MentorInput]:
    if not isinstance(payload, dict):
        raise Stage4RequestError("invalid simple batch request")
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise Stage4RequestError("simple batch request must contain records")

    mentor_inputs = []
    for record in records:
        try:
            mentor_inputs.append(MentorInput.model_validate(record))
        except ValidationError as exc:
            raise Stage4RequestError(
                f"invalid MentorInput in batch ({exc.error_count()} validation error(s))"
            ) from None
    mentor_ids = [mentor_input.mentor_id for mentor_input in mentor_inputs]
    if len(mentor_ids) != len(set(mentor_ids)):
        raise Stage4RequestError("simple batch request contains duplicate mentor_id")
    return mentor_inputs


def invoke_agent(request: AgentRequest) -> str:
    """Parse one MentorInput and return one result JSON string."""

    try:
        if request.stream:
            raise Stage4RequestError(
                "stream=true is not supported for mentor extraction; use stream=false"
            )
        payload = _parse_json_content(_last_user_content(request))

        if _is_simple_batch_payload(payload):
            if EXTRACTION_MODE != "simple":
                raise Stage4RequestError(
                    "simple batch requests are only supported in EXTRACTION_MODE=simple"
                )
            results = extract_simple_mentor_batch(
                _parse_simple_batch_payload(payload),
                model_client,
                model_service_name=MODEL_SERVICE_NAME,
                model_name=MODEL_NAME,
                taxonomy=tag_taxonomy,
            )
            return make_simple_batch_result(results).model_dump_json(by_alias=True)

        if EXTRACTION_MODE == "full":
            mentor_input = _parse_mentor_input_payload(payload)
            result = extract_single_mentor(
                mentor_input,
                model_client,
                model_service_name=MODEL_SERVICE_NAME,
                model_name=MODEL_NAME,
            )
        else:
            mentor_input = _parse_mentor_input_payload(payload)
            result = extract_simple_mentor(
                mentor_input,
                model_client,
                model_service_name=MODEL_SERVICE_NAME,
                model_name=MODEL_NAME,
                taxonomy=tag_taxonomy,
            )
        return result.model_dump_json(by_alias=True)
    except Stage4RequestError:
        logger.warning("Stage 4 mentor request rejected")
        raise
    except ExtractionError:
        logger.error("Stage 4 mentor extraction failed")
        raise Stage4RequestError("mentor extraction failed") from None
    except Exception:
        logger.error("Stage 4 model service call failed")
        raise Stage4RequestError("model service call failed") from None


if __name__ == "__main__":
    AgentRunServer(invoke_agent=invoke_agent).start()
