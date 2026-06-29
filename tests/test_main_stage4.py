"""Offline request-handler tests for the Stage 4 local interface."""

from __future__ import annotations

import importlib
import json
import sys
from dataclasses import dataclass, field
from typing import Any

import pytest

from agentrun.server import AgentRequest

from mentor_agent.extractor import ExtractionError
from mentor_agent.schemas import MentorInput, MentorResult
from mentor_agent.simple_schemas import SimpleMentorBatchResult, SimpleMentorResult


@dataclass
class FakeChatModel:
    response: Any = field(default_factory=dict)
    calls: list[Any] = field(default_factory=list)

    def invoke(self, messages: Any) -> Any:
        self.calls.append(messages)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.fixture
def stage4_main(monkeypatch: pytest.MonkeyPatch):
    fake_model = FakeChatModel()
    factory_calls: list[tuple[str, dict[str, Any]]] = []

    def fake_model_factory(name: str, **kwargs: Any) -> FakeChatModel:
        factory_calls.append((name, kwargs))
        return fake_model

    monkeypatch.setenv("MODEL_SERVICE_NAME", "stage4-test-service")
    monkeypatch.setenv("MODEL_NAME", "stage4-test-model")
    monkeypatch.delenv("EXTRACTION_MODE", raising=False)
    monkeypatch.delenv("ENABLE_STANDARD_TAGS", raising=False)
    monkeypatch.delenv("TAG_TAXONOMY_PATH", raising=False)

    import agentrun.integration.langchain as langchain_integration

    monkeypatch.setattr(langchain_integration, "model", fake_model_factory)
    sys.modules.pop("main", None)
    module = importlib.import_module("main")
    yield module, fake_model, factory_calls
    sys.modules.pop("main", None)


def _mentor_input() -> MentorInput:
    return MentorInput.model_validate(
        {
            "task": "extract_mentor_key_info",
            "input_schema_version": "1.0",
            "mentor_id": "service_mentor:stage4-test",
            "record_hash": "b" * 64,
            "source_file": "synthetic-stage4.xlsx",
            "source_sheet": "服务导师",
            "source_row": 2,
            "original_fields": {
                "序号": "stage4-test",
                "导师姓名": "匿名测试导师",
                "性别": None,
                "城市": "测试城市",
                "职业年限": 8,
                "可辅导学员职级": "P5-P7",
                "行业标签": "软件与信息技术",
                "从业经历": "曾任匿名软件公司产品负责人。",
                "背景经验": "擅长产品规划与职业辅导。",
            },
        }
    )


def _request(
    content: str,
    *,
    stream: bool = False,
    include_earlier_user: bool = False,
) -> AgentRequest:
    messages: list[dict[str, str]] = [
        {"role": "system", "content": "system message"}
    ]
    if include_earlier_user:
        messages.append({"role": "user", "content": "not-json"})
    messages.append({"role": "user", "content": content})
    return AgentRequest(messages=messages, stream=stream)


def test_model_client_is_created_from_configured_service(stage4_main) -> None:
    module, fake_model, factory_calls = stage4_main

    assert module.model_client is fake_model
    assert factory_calls == [
        ("stage4-test-service", {"model": "stage4-test-model"})
    ]
    assert module.EXTRACTION_MODE == "simple"


def test_valid_mentor_input_returns_simple_result_json_by_default(stage4_main) -> None:
    module, fake_model, _ = stage4_main
    request = _request(
        _mentor_input().model_dump_json(by_alias=True),
        include_earlier_user=True,
    )

    content = module.invoke_agent(request)
    result = SimpleMentorResult.model_validate_json(content)

    assert result.mentor_id == "service_mentor:stage4-test"
    assert result.source.file == "synthetic-stage4.xlsx"
    assert result.processing.model_service_name == "stage4-test-service"
    assert result.processing.model_name == "stage4-test-model"
    assert len(fake_model.calls) == 1
    assert result.schema_version == "simple-v1"


def test_tagged_simple_mode_loads_taxonomy_and_returns_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_model = FakeChatModel(
        response={
            "position_tags": [
                {
                    "tag": "产品经理",
                    "relation_type": "firsthand_role",
                    "confidence": 0.9,
                    "raw_keywords": ["产品负责人"],
                    "evidence": "产品负责人",
                }
            ]
        }
    )

    def fake_model_factory(name: str, **kwargs: Any) -> FakeChatModel:
        return fake_model

    monkeypatch.setenv("MODEL_SERVICE_NAME", "stage4-test-service")
    monkeypatch.setenv("EXTRACTION_MODE", "simple")
    monkeypatch.setenv("ENABLE_STANDARD_TAGS", "true")
    monkeypatch.setenv("TAG_TAXONOMY_PATH", "configs/职位类型_2.txt")
    import agentrun.integration.langchain as langchain_integration

    monkeypatch.setattr(langchain_integration, "model", fake_model_factory)
    sys.modules.pop("main", None)
    module = importlib.import_module("main")
    try:
        content = module.invoke_agent(
            _request(_mentor_input().model_dump_json(by_alias=True))
        )
        result = SimpleMentorResult.model_validate_json(content)
    finally:
        sys.modules.pop("main", None)

    assert result.standard_tags_enabled is True
    assert result.taxonomy_hash == module.tag_taxonomy.taxonomy_hash
    assert result.prompt_version == "mentor-simple-tagged-v1"


def test_invalid_standard_tags_boolean_fails_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_SERVICE_NAME", "stage4-test-service")
    monkeypatch.setenv("ENABLE_STANDARD_TAGS", "yes")
    sys.modules.pop("main", None)
    with pytest.raises(ValueError, match="ENABLE_STANDARD_TAGS"):
        importlib.import_module("main")
    sys.modules.pop("main", None)


def test_full_mode_does_not_load_taxonomy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_model = FakeChatModel()

    def fake_model_factory(name: str, **kwargs: Any) -> FakeChatModel:
        return fake_model

    monkeypatch.setenv("MODEL_SERVICE_NAME", "stage4-test-service")
    monkeypatch.setenv("EXTRACTION_MODE", "full")
    monkeypatch.setenv("ENABLE_STANDARD_TAGS", "true")
    monkeypatch.setenv("TAG_TAXONOMY_PATH", "missing-taxonomy.txt")
    import agentrun.integration.langchain as langchain_integration

    monkeypatch.setattr(langchain_integration, "model", fake_model_factory)
    sys.modules.pop("main", None)
    module = importlib.import_module("main")
    try:
        assert module.tag_taxonomy is None
    finally:
        sys.modules.pop("main", None)


def test_full_mode_returns_mentor_result_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_model = FakeChatModel()

    def fake_model_factory(name: str, **kwargs: Any) -> FakeChatModel:
        return fake_model

    monkeypatch.setenv("MODEL_SERVICE_NAME", "stage4-test-service")
    monkeypatch.setenv("MODEL_NAME", "stage4-test-model")
    monkeypatch.setenv("EXTRACTION_MODE", "full")

    import agentrun.integration.langchain as langchain_integration

    monkeypatch.setattr(langchain_integration, "model", fake_model_factory)
    sys.modules.pop("main", None)
    module = importlib.import_module("main")
    try:
        content = module.invoke_agent(
            _request(_mentor_input().model_dump_json(by_alias=True))
        )
        result = MentorResult.model_validate_json(content)
    finally:
        sys.modules.pop("main", None)

    assert module.EXTRACTION_MODE == "full"
    assert result.mentor_id == "service_mentor:stage4-test"


def test_simple_mode_accepts_batch_request(stage4_main) -> None:
    module, fake_model, _ = stage4_main
    mentor_input = _mentor_input()
    payload = {
        "task": "extract_mentor_keywords_batch_simple",
        "records": [
            mentor_input.model_dump(by_alias=True, mode="json"),
            mentor_input.model_copy(
                update={
                    "mentor_id": "service_mentor:stage4-test-2",
                    "record_hash": "c" * 64,
                }
            ).model_dump(by_alias=True, mode="json"),
        ],
    }
    fake_model.response = {
        "results": [
            {
                "mentor_id": "service_mentor:stage4-test",
                "extraction": {"skills": ["skill-a"]},
            },
            {
                "mentor_id": "service_mentor:stage4-test-2",
                "extraction": {"skills": ["skill-b"]},
            },
        ]
    }

    content = module.invoke_agent(
        _request(json.dumps(payload, ensure_ascii=False))
    )
    result = SimpleMentorBatchResult.model_validate_json(content)

    assert result.schema_version == "simple-batch-v1"
    assert [item.mentor_id for item in result.results] == [
        "service_mentor:stage4-test",
        "service_mentor:stage4-test-2",
    ]
    assert len(fake_model.calls) == 1


def test_full_mode_rejects_batch_request(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_model = FakeChatModel()

    def fake_model_factory(name: str, **kwargs: Any) -> FakeChatModel:
        return fake_model

    monkeypatch.setenv("MODEL_SERVICE_NAME", "stage4-test-service")
    monkeypatch.setenv("MODEL_NAME", "stage4-test-model")
    monkeypatch.setenv("EXTRACTION_MODE", "full")

    import agentrun.integration.langchain as langchain_integration

    monkeypatch.setattr(langchain_integration, "model", fake_model_factory)
    sys.modules.pop("main", None)
    module = importlib.import_module("main")
    try:
        payload = {
            "task": "extract_mentor_keywords_batch_simple",
            "records": [_mentor_input().model_dump(by_alias=True, mode="json")],
        }
        with pytest.raises(module.Stage4RequestError, match="simple batch"):
            module.invoke_agent(_request(json.dumps(payload, ensure_ascii=False)))
    finally:
        sys.modules.pop("main", None)

    assert fake_model.calls == []


def test_missing_user_message_returns_explicit_error(stage4_main) -> None:
    module, fake_model, _ = stage4_main
    request = AgentRequest(
        messages=[{"role": "system", "content": "system only"}],
        stream=False,
    )

    with pytest.raises(module.Stage4RequestError, match="contain a user message"):
        module.invoke_agent(request)

    assert fake_model.calls == []


def test_non_json_content_returns_error_without_fallback(stage4_main) -> None:
    module, fake_model, _ = stage4_main

    with pytest.raises(module.Stage4RequestError, match="valid JSON"):
        module.invoke_agent(_request("ordinary chat text"))

    assert fake_model.calls == []


def test_invalid_mentor_input_returns_validation_count_only(stage4_main) -> None:
    module, fake_model, _ = stage4_main

    with pytest.raises(module.Stage4RequestError, match=r"invalid MentorInput \(.*validation error"):
        module.invoke_agent(_request("{}"))

    assert fake_model.calls == []


def test_stream_true_mentor_input_is_explicitly_rejected(stage4_main) -> None:
    module, fake_model, _ = stage4_main
    request = _request(
        _mentor_input().model_dump_json(by_alias=True),
        stream=True,
    )

    with pytest.raises(module.Stage4RequestError, match="stream=false"):
        module.invoke_agent(request)

    assert fake_model.calls == []


def test_extraction_error_does_not_leak_sensitive_details(
    stage4_main,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, _, _ = stage4_main
    logged: list[tuple[Any, ...]] = []

    def fail_extraction(*args: Any, **kwargs: Any) -> None:
        raise ExtractionError(
            "Authorization: Bearer secret-token; API Key=secret; .env content"
        )

    monkeypatch.setattr(module, "extract_simple_mentor", fail_extraction)
    monkeypatch.setattr(
        module.logger,
        "error",
        lambda *args, **kwargs: logged.append(args),
    )

    with pytest.raises(module.Stage4RequestError) as exc_info:
        module.invoke_agent(
            _request(_mentor_input().model_dump_json(by_alias=True))
        )

    combined = f"{exc_info.value!s} {logged!r}"
    assert "secret-token" not in combined
    assert "API Key" not in combined
    assert "Authorization" not in combined
    assert ".env" not in combined
    assert str(exc_info.value) == "mentor extraction failed"


def test_unexpected_model_error_is_sanitized(
    stage4_main,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, _, _ = stage4_main
    logged: list[tuple[Any, ...]] = []

    def fail_model(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("AccessKey=secret-access-key")

    monkeypatch.setattr(module, "extract_simple_mentor", fail_model)
    monkeypatch.setattr(
        module.logger,
        "error",
        lambda *args, **kwargs: logged.append(args),
    )

    with pytest.raises(module.Stage4RequestError) as exc_info:
        module.invoke_agent(
            _request(_mentor_input().model_dump_json(by_alias=True))
        )

    combined = f"{exc_info.value!s} {logged!r}"
    assert "secret-access-key" not in combined
    assert "AccessKey" not in combined
    assert str(exc_info.value) == "model service call failed"
