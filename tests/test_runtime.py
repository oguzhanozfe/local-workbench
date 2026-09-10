import asyncio
import json

import httpx
import pytest
from pydantic import ValidationError

from local_workbench.app import create_app
from local_workbench.config import ModelProfile, Settings
from local_workbench.contracts import ChatRequest, TaskRequest, digest
from local_workbench.runtime import AdmissionQueue, Runtime, WorkbenchError


def settings(tmp_path, **overrides):
    return Settings(
        state_dir=tmp_path / "state",
        models={"local-workbench": ModelProfile(model="fake:explicit")},
        **overrides,
    )


def ollama(text):
    # A transport fixture, not benchmark data. No fabricated usage measurements.
    return {
        "message": {"role": "assistant", "content": text},
        "done": True,
        "done_reason": "stop",
    }


def task(evidence=None):
    return TaskRequest(
        kind="evidence_match",
        task="Find SQL evidence.",
        evidence=evidence
        if evidence is not None
        else [{"id": "claim.sql", "text": "Built a SQL report.", "approved": True}],
    )


def valid_match():
    return {
        "answerable": True,
        "matches": [
            {
                "requirement": "SQL",
                "evidence_id": "claim.sql",
                "quote": "Built a SQL report.",
            }
        ],
        "gaps": [],
    }


async def service(tmp_path, handler, **overrides):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return Runtime(settings(tmp_path, **overrides), client), client


@pytest.mark.asyncio
async def test_gateway_preserves_messages_and_native_budgets(tmp_path):
    captured = []

    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=ollama('{"ok":true}'))

    runtime, client = await service(tmp_path, handler)
    original = [
        {"role": "system", "content": "Keep exact: å\n."},
        {"role": "user", "content": "Private text unchanged."},
    ]
    request = ChatRequest(
        model="local-workbench",
        messages=original,
        response_format={"type": "json_object"},
    )
    result = await runtime.chat(request)
    assert captured[0]["messages"] == original
    assert captured[0]["think"] is False and captured[0]["format"] == "json"
    assert captured[0]["options"]["num_ctx"] == 8192
    assert result["workbench"]["input_sha256"] == digest(original)
    assert result["usage"]["prompt_tokens"] is None
    logged = (runtime.settings.state_dir / "requests.jsonl").read_text()
    assert "Private text" not in logged and str(tmp_path) not in logged
    await client.aclose()


@pytest.mark.asyncio
async def test_context_rejected_before_provider(tmp_path):
    runtime, client = await service(tmp_path, lambda _: pytest.fail("must not call provider"))
    with pytest.raises(WorkbenchError, match="not truncated") as caught:
        await runtime.chat(
            ChatRequest(
                model="local-workbench",
                messages=[{"role": "user", "content": "x" * 8000}],
            )
        )
    assert caught.value.code == "context_budget_exceeded"
    assert (
        json.loads((runtime.settings.state_dir / "requests.jsonl").read_text())["provider_attempts"]
        == 0
    )
    await client.aclose()


@pytest.mark.asyncio
async def test_one_repair_and_original_packet_immutable(tmp_path):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=ollama("not json" if len(calls) == 1 else json.dumps(valid_match())),
        )

    runtime, client = await service(tmp_path, handler)
    result = await runtime.task(task())
    assert result["provider_attempts"] == 2
    assert calls[0]["messages"] == calls[1]["messages"][:2]
    assert result["packet_sha256"] == digest(result["packet"])
    assert result["status"] == "unreviewed_draft"
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    [
        {
            "answerable": True,
            "matches": [
                {
                    "requirement": "SQL",
                    "evidence_id": "invented",
                    "quote": "Built a SQL report.",
                }
            ],
            "gaps": [],
        },
        {
            "answerable": True,
            "matches": [
                {
                    "requirement": "SQL",
                    "evidence_id": "claim.sql",
                    "quote": "Led 40 people.",
                }
            ],
            "gaps": [],
        },
        {"answerable": True, "matches": [], "gaps": []},
    ],
)
async def test_invalid_evidence_never_accepted(tmp_path, bad):
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        return httpx.Response(200, json=ollama(json.dumps(bad)))

    runtime, client = await service(tmp_path, handler)
    with pytest.raises(WorkbenchError) as caught:
        await runtime.task(task())
    assert caught.value.code == "task_output_rejected" and count == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_unapproved_and_superseded_evidence_is_excluded(tmp_path):
    runtime, client = await service(
        tmp_path, lambda _: pytest.fail("no inference for empty evidence")
    )
    result = await runtime.task(
        task(
            [
                {"id": "private.unapproved", "text": "SECRET", "approved": False},
                {
                    "id": "private.old",
                    "text": "OLD SECRET",
                    "approved": True,
                    "status": "superseded",
                },
            ]
        )
    )
    assert result["result"]["answerable"] is False
    assert result["validation"]["excluded_evidence"] == 2
    assert result["provider_attempts"] == 0
    assert "SECRET" not in json.dumps(result)
    await client.aclose()


@pytest.mark.asyncio
async def test_provider_timeout_is_categorized(tmp_path):
    def handler(request):
        raise httpx.ReadTimeout("secret URL or packet must not be echoed")

    runtime, client = await service(tmp_path, handler)
    with pytest.raises(WorkbenchError) as caught:
        await runtime.task(task())
    assert caught.value.code == "provider_timeout"
    assert "secret" not in caught.value.message
    await client.aclose()


@pytest.mark.asyncio
async def test_queue_limit_and_wait_timeout():
    queue = AdmissionQueue(limit=1, timeout=0.03)
    async with queue.acquire():

        async def wait():
            async with queue.acquire():
                pytest.fail("slot remains occupied")

        waiting = asyncio.create_task(wait())
        await asyncio.sleep(0)
        with pytest.raises(WorkbenchError) as caught:
            async with queue.acquire():
                pass
        assert caught.value.code == "queue_full"
        with pytest.raises(WorkbenchError) as caught:
            await waiting
        assert caught.value.code == "queue_timeout"
    assert queue.active == 0 and queue.waiting == 0


@pytest.mark.asyncio
async def test_queue_cancel_releases_count():
    queue = AdmissionQueue(limit=1, timeout=10)
    async with queue.acquire():

        async def wait():
            async with queue.acquire():
                pass

        waiter = asyncio.create_task(wait())
        await asyncio.sleep(0)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
    assert queue.active == queue.waiting == 0


@pytest.mark.asyncio
async def test_schema_references_rejected_before_network(tmp_path):
    runtime, client = await service(tmp_path, lambda _: pytest.fail("no schema network access"))
    request = ChatRequest(
        model="local-workbench",
        messages=[{"role": "user", "content": "JSON"}],
        response_format={
            "type": "json_schema",
            "json_schema": {"schema": {"type": "object", "$ref": "http://169.254.169.254/private"}},
        },
    )
    with pytest.raises(WorkbenchError) as caught:
        await runtime.chat(request)
    assert caught.value.code == "invalid_schema"
    await client.aclose()


@pytest.mark.parametrize("wrapper", [None, [], "schema"])
def test_malformed_response_format_is_validation_error(wrapper):
    with pytest.raises(ValidationError):
        ChatRequest(
            model="local-workbench",
            messages=[{"role": "user", "content": "JSON"}],
            response_format={"type": "json_schema", "json_schema": wrapper},
        )


@pytest.mark.asyncio
async def test_gateway_schema_and_opt_in_fence_strip(tmp_path):
    runtime, client = await service(
        tmp_path,
        lambda _: httpx.Response(200, json=ollama('```json\n{"ok":true}\n```')),
        gateway_strip_json_fence=True,
    )
    schema = {
        "type": "object",
        "required": ["ok"],
        "properties": {"ok": {"type": "boolean"}},
        "additionalProperties": False,
    }
    result = await runtime.chat(
        ChatRequest(
            model="local-workbench",
            messages=[{"role": "user", "content": "JSON"}],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "check", "schema": schema},
            },
        )
    )
    assert result["workbench"]["json_fence_removed"] is True
    assert json.loads(result["choices"][0]["message"]["content"]) == {"ok": True}
    await client.aclose()


@pytest.mark.asyncio
async def test_http_error_does_not_echo_private_input(tmp_path):
    runtime, upstream = await service(
        tmp_path, lambda _: pytest.fail("invalid input never forwarded")
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runtime.settings, runtime)),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "local-workbench",
                "messages": [{"role": "tool", "content": "PRIVATE RAW INPUT"}],
            },
        )
        assert response.status_code == 422 and "PRIVATE RAW INPUT" not in response.text
        response = await client.post(
            "/v1/chat/completions",
            content=b"x" * (runtime.settings.max_request_bytes + 1),
        )
        assert response.status_code == 413
    await upstream.aclose()


@pytest.mark.asyncio
async def test_retrieval_approved_only_before_packet(tmp_path):
    seen = []

    def handler(request):
        seen.append((request.url.path, json.loads(request.content)))
        if request.url.path == "/v1/search":
            return httpx.Response(
                200,
                json={
                    "spans": [
                        {
                            "chunk_id": "claim.sql",
                            "text": "Built a SQL report.",
                            "approved": True,
                            "status": "current",
                            "source": "synthetic.md",
                            "source_sha256": "a" * 64,
                            "start_line": 1,
                            "end_line": 1,
                            "start_char": 0,
                            "end_char": 19,
                        }
                    ]
                },
            )
        return httpx.Response(200, json=ollama(json.dumps(valid_match())))

    runtime, client = await service(
        tmp_path, handler, retrieval={"search_url": "http://127.0.0.1:8091/v1/search"}
    )
    result = await runtime.task(
        TaskRequest(kind="evidence_match", task="Find SQL evidence", retrieval={"query": "SQL"})
    )
    assert seen[0][0] == "/v1/search" and seen[0][1]["approved_only"] is True
    assert seen[0][1]["statuses"] == ["current"]
    assert result["packet"]["evidence"][0]["source_sha256"] == "a" * 64
    assert result["packet_sha256"] == digest(result["packet"])
    await client.aclose()


@pytest.mark.asyncio
async def test_local_defs_schema_supported(tmp_path):
    runtime, client = await service(
        tmp_path, lambda _: httpx.Response(200, json=ollama('{"ok":true}'))
    )
    schema = {
        "$defs": {"flag": {"type": "boolean"}},
        "type": "object",
        "properties": {"ok": {"$ref": "#/$defs/flag"}},
        "required": ["ok"],
    }
    result = await runtime.chat(
        ChatRequest(
            model="local-workbench",
            messages=[{"role": "user", "content": "JSON"}],
            response_format={"type": "json_schema", "json_schema": {"schema": schema}},
        )
    )
    assert json.loads(result["choices"][0]["message"]["content"])["ok"] is True
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "schema",
    [
        {"$defs": {"cycle": {"$ref": "#/$defs/cycle"}}, "$ref": "#/$defs/cycle"},
        {"$ref": "#/$defs/missing"},
        {"type": "string", "pattern": "(a+)+$"},
    ],
)
async def test_unsafe_local_schemas_rejected_before_provider(tmp_path, schema):
    runtime, client = await service(tmp_path, lambda _: pytest.fail("no provider call"))
    with pytest.raises(WorkbenchError) as caught:
        await runtime.chat(
            ChatRequest(
                model="local-workbench",
                messages=[{"role": "user", "content": "JSON"}],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"schema": schema},
                },
            )
        )
    assert caught.value.code == "invalid_schema"
    await client.aclose()


@pytest.mark.asyncio
async def test_total_provider_timeout(tmp_path):
    async def handler(request):
        await asyncio.sleep(0.2)
        return httpx.Response(200, json=ollama('{"ok":true}'))

    runtime, client = await service(tmp_path, handler, provider_timeout_seconds=0.02)
    with pytest.raises(WorkbenchError) as caught:
        await runtime.chat(
            ChatRequest(model="local-workbench", messages=[{"role": "user", "content": "JSON"}])
        )
    assert caught.value.code == "provider_timeout"
    assert runtime.queue.active == 0
    await client.aclose()


@pytest.mark.asyncio
async def test_nonfinite_provider_json_rejected(tmp_path):
    runtime, client = await service(
        tmp_path, lambda _: httpx.Response(200, json=ollama('{"score":NaN}'))
    )
    with pytest.raises(WorkbenchError) as caught:
        await runtime.chat(
            ChatRequest(
                model="local-workbench",
                messages=[{"role": "user", "content": "JSON"}],
                response_format={"type": "json_object"},
            )
        )
    assert caught.value.code == "invalid_json"
    await client.aclose()


@pytest.mark.asyncio
async def test_malformed_inventory_is_unavailable(tmp_path):
    runtime, client = await service(
        tmp_path, lambda _: httpx.Response(200, json={"models": [None]})
    )
    report = await runtime.health()
    assert report["status"] == "unavailable" and report["error"] == "provider_invalid_response"
    await client.aclose()


@pytest.mark.asyncio
async def test_missing_approval_is_excluded(tmp_path):
    runtime, client = await service(tmp_path, lambda _: pytest.fail("approval is not implied"))
    result = await runtime.task(task([{"id": "claim.sql", "text": "Built a SQL report."}]))
    assert result["result"]["answerable"] is False
    assert result["validation"]["excluded_evidence"] == 1
    await client.aclose()


def test_approval_requires_a_boolean():
    with pytest.raises(ValidationError):
        task([{"id": "claim.sql", "text": "Built a SQL report.", "approved": "true"}])


@pytest.mark.asyncio
async def test_model_tool_call_rejected(tmp_path):
    raw = ollama("I will run a command.")
    raw["message"]["tool_calls"] = [
        {"function": {"name": "shell", "arguments": {"command": "private command"}}}
    ]
    runtime, client = await service(tmp_path, lambda _: httpx.Response(200, json=raw))
    with pytest.raises(WorkbenchError) as caught:
        await runtime.task(task())
    assert caught.value.code == "provider_invalid_response"
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["pattern", "$id", "$ref", "patternProperties", "$dynamicRef"])
async def test_schema_keyword_as_property_name_is_valid(tmp_path, field):
    result_json = {field: "ordinary field value"}
    runtime, client = await service(
        tmp_path, lambda _: httpx.Response(200, json=ollama(json.dumps(result_json)))
    )
    schema = {
        "type": "object",
        "properties": {field: {"type": "string"}},
        "required": [field],
        "additionalProperties": False,
    }
    response = await runtime.chat(
        ChatRequest(
            model="local-workbench",
            messages=[{"role": "user", "content": "JSON"}],
            response_format={"type": "json_schema", "json_schema": {"schema": schema}},
        )
    )
    assert json.loads(response["choices"][0]["message"]["content"]) == result_json
    await client.aclose()


@pytest.mark.asyncio
async def test_definition_name_and_const_keywords_are_literal_data(tmp_path):
    result_json = {"pattern": {"$ref": "literal text", "pattern": "a+"}}
    runtime, client = await service(
        tmp_path, lambda _: httpx.Response(200, json=ollama(json.dumps(result_json)))
    )
    schema = {
        "$defs": {"pattern": {"const": result_json["pattern"]}},
        "type": "object",
        "properties": {"pattern": {"$ref": "#/$defs/pattern"}},
        "required": ["pattern"],
    }
    response = await runtime.chat(
        ChatRequest(
            model="local-workbench",
            messages=[{"role": "user", "content": "JSON"}],
            response_format={"type": "json_schema", "json_schema": {"schema": schema}},
        )
    )
    assert json.loads(response["choices"][0]["message"]["content"]) == result_json
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("keyword", ["pattern", "$id", "$ref"])
async def test_actual_keyword_inside_property_schema_is_blocked(tmp_path, keyword):
    runtime, client = await service(tmp_path, lambda _: pytest.fail("rejected before provider"))
    schema = {
        "type": "object",
        "properties": {"field": {"type": "string", keyword: "https://invalid.example/schema"}},
    }
    with pytest.raises(WorkbenchError) as caught:
        await runtime.chat(
            ChatRequest(
                model="local-workbench",
                messages=[{"role": "user", "content": "JSON"}],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"schema": schema},
                },
            )
        )
    assert caught.value.code == "invalid_schema"
    await client.aclose()
