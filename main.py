"""Thin AgentRun server entry point for single-mentor extraction."""

from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv
from pydantic import ValidationError

from agentrun.integration.langchain import model
from agentrun.server import AgentRequest, AgentRunServer
from agentrun.utils.log import logger

from mentor_agent.extractor import ExtractionError, extract_single_mentor
from mentor_agent.schemas import MentorInput


class Stage4RequestError(ValueError):
    """Safe request error whose message contains no source record content."""


load_dotenv()
MODEL_NAME = os.getenv("MODEL_NAME")
MODEL_SERVICE_NAME = os.getenv("MODEL_SERVICE_NAME")
SANDBOX_NAME = os.getenv("SANDBOX_NAME")

if not MODEL_SERVICE_NAME:
    raise ValueError("MODEL_SERVICE_NAME is required")

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


def _parse_mentor_input(content: str) -> MentorInput:
    try:
        payload: Any = json.loads(content)
    except json.JSONDecodeError:
        raise Stage4RequestError(
            "last user message content must be valid JSON"
        ) from None

    try:
        return MentorInput.model_validate(payload)
    except ValidationError as exc:
        raise Stage4RequestError(
            f"invalid MentorInput ({exc.error_count()} validation error(s))"
        ) from None


def invoke_agent(request: AgentRequest) -> str:
    """Parse one MentorInput and return one MentorResult JSON string."""

    try:
        mentor_input = _parse_mentor_input(_last_user_content(request))
        if request.stream:
            raise Stage4RequestError(
                "stream=true is not supported for mentor extraction; use stream=false"
            )

        result = extract_single_mentor(
            mentor_input,
            model_client,
            model_service_name=MODEL_SERVICE_NAME,
            model_name=MODEL_NAME,
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
