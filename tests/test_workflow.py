import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from local_workbench.config import Settings
from local_workbench.contracts import canonical, digest
from local_workbench.runtime import Runtime, WorkbenchError
from local_workbench.workflow import Recipe, load_checkpoint, run_workflow


def recipe(tmp_path, stages=2, repairs=0):
    value = {
        "version": 1,
        "title": "Synthetic application",
        "model": "local-workbench",
        "repairs": repairs,
        "evidence": [
            {
                "id": "claim.sql",
                "text": "The fictional candidate built SQL reports.",
                "approved": True,
            }
        ],
        "stages": [
            {
                "id": f"stage_{i}",
                "title": f"Stage {i}",
                "instructions": "Draft a short evidence-based section.",
                "depends_on": [f"stage_{i - 1}"] if i else [],
                "evidence_ids": ["claim.sql"],
                "min_words": 5,
                "required_headings": ["Experience"],
                "output_tokens": 256,
            }
            for i in range(stages)
        ],
    }
    path = tmp_path / "recipe.json"
    path.write_text(json.dumps(value))
    return path


def result(**updates):
    value = {
        "text": "### Experience\nThe fictional candidate built SQL reports.",
        "used_evidence_ids": ["claim.sql"],
        "quotes": [{"evidence_id": "claim.sql", "quote": "built SQL reports."}],
        "assumptions": [],
        "unknowns": [],
    }
    value.update(updates)
    return value


class Backend:
    def __init__(self, values):
        self.values = list(values)
        self.calls = []
        self.revision = "a" * 64

    def __call__(self, request):
        if request.url.path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": "test:model", "digest": self.revision}]}
            )
        self.calls.append(json.loads(request.content))
        value = self.values.pop(0)
        if isinstance(value, BaseException):
            raise value
        if value == "truncated":
            return httpx.Response(
                200,
                json={
                    "done": True,
                    "done_reason": "length",
                    "message": {"content": json.dumps(result())},
                },
            )
        return httpx.Response(
            200,
            json={"done": True, "done_reason": "stop", "message": {"content": json.dumps(value)}},
        )


def runtime(tmp_path, backend):
    client = httpx.AsyncClient(transport=httpx.MockTransport(backend))
    settings = Settings(
        state_dir=tmp_path / "metrics",
        models={"local-workbench": {"model": "test:model", "num_ctx": 8192, "output_tokens": 768}},
    )
    return Runtime(settings, client), client


@pytest.mark.asyncio
async def test_interrupt_resume_skips_completed_stages_and_preserves_dependencies(tmp_path):
    path = recipe(tmp_path)
    backend = Backend([result(), asyncio.CancelledError(), result()])
    service, client = runtime(tmp_path, backend)
    out = tmp_path / "out"
    with pytest.raises(asyncio.CancelledError):
        await run_workflow(service, path, out)
    checkpoint = load_checkpoint(out)
    assert [r["status"] for r in checkpoint["stages"]] == ["completed", "running"]
    report = await run_workflow(service, path, out, resume=True)
    assert report["status"] == "completed"
    assert len(backend.calls) == 3
    packet = json.loads(backend.calls[-1]["messages"][1]["content"])
    assert packet["previous_unreviewed_stages"] == {"stage_0": result()}
    assert report["review_status"] == "unreviewed_draft"
    assert report["stages"][0]["checks"]["semantic_entailment"] == "not_tested"
    assert (out / "document.md").is_file() and (out / "report.json").is_file()
    again = await run_workflow(service, path, out, resume=True)
    assert again == report and len(backend.calls) == 3
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["recipe", "model", "profile", "checkpoint", "artifact", "missing"]
)
async def test_resume_rejects_changed_input_identity_or_artifacts(tmp_path, change):
    path = recipe(tmp_path, stages=1)
    backend = Backend([result()])
    service, client = runtime(tmp_path, backend)
    out = tmp_path / "out"
    await run_workflow(service, path, out)
    if change == "recipe":
        path.write_text(path.read_text() + "\n")
    elif change == "model":
        backend.revision = "b" * 64
    elif change == "profile":
        service.settings.models["local-workbench"].temperature = 0.5
    elif change == "checkpoint":
        envelope = json.loads((out / "checkpoint.json").read_text())
        envelope["payload"]["stages"][0]["result"]["text"] += " tampered"
        (out / "checkpoint.json").write_text(json.dumps(envelope))
    elif change == "artifact":
        (out / "document.md").write_text("changed")
    else:
        (out / "document.md").unlink()
    with pytest.raises(WorkbenchError) as error:
        await run_workflow(service, path, out, resume=True)
    assert error.value.code in {"resume_inputs_changed", "checkpoint_corrupt", "artifact_changed"}
    assert len(backend.calls) == 1
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad,code",
    [
        (result(used_evidence_ids=["unknown"]), "invalid_citation"),
        (
            result(quotes=[{"evidence_id": "claim.sql", "quote": "invented quote"}]),
            "unsupported_quote",
        ),
        (result(text="Too short"), "stage_too_short"),
        (result(text="This is long enough but omits required headings."), "missing_headings"),
        ("truncated", "output_limit_reached"),
    ],
)
async def test_failed_stage_is_saved_and_resume_runs_only_unfinished(tmp_path, bad, code):
    path = recipe(tmp_path)
    backend = Backend([result(), bad, result()])
    service, client = runtime(tmp_path, backend)
    out = tmp_path / "out"
    report = await run_workflow(service, path, out)
    assert report["status"] == "failed" and report["stages"][1]["error_code"] == code
    assert not (out / "document.md").exists()
    report = await run_workflow(service, path, out, resume=True)
    assert report["status"] == "completed" and len(backend.calls) == 3
    assert len(report["stages"][1]["attempts"]) == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_repair_is_bounded_to_one_and_keeps_failed_attempt(tmp_path):
    path = recipe(tmp_path, stages=1, repairs=1)
    backend = Backend([result(used_evidence_ids=["missing"]), result()])
    service, client = runtime(tmp_path, backend)
    report = await run_workflow(service, path, tmp_path / "out")
    assert report["status"] == "completed" and len(backend.calls) == 2
    assert report["stages"][0]["attempts"][0]["error_code"] == "invalid_citation"
    assert backend.calls[0]["messages"][0:2] == backend.calls[1]["messages"][0:2]
    assert backend.calls[1]["options"]["num_predict"] == 256
    await client.aclose()


@pytest.mark.asyncio
async def test_unrelated_files_and_symlink_outputs_are_rejected(tmp_path):
    path = recipe(tmp_path, stages=1)
    backend = Backend([result()])
    service, client = runtime(tmp_path, backend)
    out = tmp_path / "out"
    out.mkdir()
    (out / "personal.txt").write_text("keep")
    with pytest.raises(WorkbenchError, match="unrelated"):
        await run_workflow(service, path, out)
    assert (out / "personal.txt").read_text() == "keep" and not backend.calls
    link = tmp_path / "link"
    link.symlink_to(out, target_is_directory=True)
    with pytest.raises(WorkbenchError, match="symlinks"):
        await run_workflow(service, path, link)
    await client.aclose()


def test_recipe_rejects_tools_forward_dependencies_and_unapproved_evidence(tmp_path):
    path = recipe(tmp_path)
    base = json.loads(path.read_text())
    for change in ["tools", "dependency", "evidence"]:
        value = json.loads(json.dumps(base))
        if change == "tools":
            value["command"] = "run arbitrary shell"
        if change == "dependency":
            value["stages"][0]["depends_on"] = ["stage_1"]
        if change == "evidence":
            value["evidence"][0]["approved"] = False
        with pytest.raises(ValidationError):
            Recipe.model_validate(value)


@pytest.mark.asyncio
async def test_publication_interruption_resumes_without_regeneration(tmp_path, monkeypatch):
    from local_workbench import workflow

    path = recipe(tmp_path, stages=1)
    backend = Backend([result()])
    service, client = runtime(tmp_path, backend)
    out = tmp_path / "out"
    atomic = workflow.atomic_bytes

    def interrupted(target, value):
        if target.name == "report.json":
            raise OSError("synthetic disk interruption")
        return atomic(target, value)

    monkeypatch.setattr(workflow, "atomic_bytes", interrupted)
    with pytest.raises(OSError):
        await run_workflow(service, path, out)
    assert load_checkpoint(out)["publication"] == "pending"
    assert (out / "document.md").is_file()
    monkeypatch.setattr(workflow, "atomic_bytes", atomic)
    report = await run_workflow(service, path, out, resume=True)
    assert report["status"] == "completed" and len(backend.calls) == 1
    assert load_checkpoint(out)["publication"] == "complete"
    await client.aclose()


@pytest.mark.asyncio
async def test_model_digest_change_after_generation_rejects_stage(tmp_path):
    path = recipe(tmp_path, stages=1)
    backend = Backend([result()])

    def changing(request):
        response = backend(request)
        if request.url.path == "/api/chat":
            backend.revision = "c" * 64
        return response

    service, client = runtime(tmp_path, changing)
    report = await run_workflow(service, path, tmp_path / "out")
    assert report["status"] == "failed"
    assert report["stages"][0]["error_code"] == "model_changed"
    assert not (tmp_path / "out" / "document.md").exists()
    await client.aclose()


@pytest.mark.asyncio
async def test_same_output_cannot_be_run_concurrently(tmp_path):
    path = recipe(tmp_path, stages=1)
    backend = Backend([result()])
    entered, release = asyncio.Event(), asyncio.Event()

    async def waiting(request):
        if request.url.path == "/api/chat":
            entered.set()
            await release.wait()
        return backend(request)

    service, client = runtime(tmp_path, waiting)
    out = tmp_path / "out"
    first = asyncio.create_task(run_workflow(service, path, out))
    await entered.wait()
    try:
        with pytest.raises(WorkbenchError) as error:
            await run_workflow(service, path, out, resume=True)
        assert error.value.code == "workflow_locked"
    finally:
        release.set()
        await first
    await client.aclose()


@pytest.mark.asyncio
async def test_failed_repair_does_not_create_a_third_attempt(tmp_path):
    path = recipe(tmp_path, stages=1, repairs=1)
    invalid = result(used_evidence_ids=["missing"])
    backend = Backend([invalid, invalid, result()])
    service, client = runtime(tmp_path, backend)
    report = await run_workflow(service, path, tmp_path / "out")
    assert report["status"] == "failed" and len(backend.calls) == 2
    assert len(report["stages"][0]["attempts"]) == 2
    await client.aclose()


def test_atomic_save_never_truncates_an_existing_hardlinked_temp(tmp_path):
    from local_workbench.workflow import atomic_bytes

    external = tmp_path / "personal.txt"
    external.write_text("Preserve this unrelated file.")
    output = tmp_path / "out"
    output.mkdir()
    fixed_temp = output / "checkpoint.json.tmp"
    fixed_temp.hardlink_to(external)
    target = output / "checkpoint.json"
    atomic_bytes(target, b"new checkpoint")
    assert external.read_text() == "Preserve this unrelated file."
    assert fixed_temp.read_text() == external.read_text()
    assert target.read_bytes() == b"new checkpoint"
    assert not list(output.glob(".workflow-*.tmp"))
    if os.name != "nt":
        assert target.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("name", [".workflow.lock", "checkpoint.json.tmp", "checkpoint.json"])
def test_output_lock_rejects_hardlinks_before_writing_any_lock_byte(tmp_path, name):
    from local_workbench.workflow import output_lock

    external = tmp_path / "empty-personal.txt"
    external.write_bytes(b"")
    output = tmp_path / "out"
    output.mkdir()
    (output / name).hardlink_to(external)
    with pytest.raises(WorkbenchError) as error:
        with output_lock(output, resume=True):
            pytest.fail("A hardlinked workflow file was accepted")
    assert error.value.code == "output_not_owned"
    assert external.read_bytes() == b""


def test_failed_atomic_replace_preserves_target_and_cleans_only_its_own_temp(tmp_path, monkeypatch):
    from local_workbench import workflow

    target = tmp_path / "checkpoint.json"
    target.write_bytes(b"previous checkpoint")
    unrelated = tmp_path / "checkpoint.json.tmp"
    unrelated.write_bytes(b"existing file")

    def fail_replace(*args):
        raise OSError("synthetic replace failure")

    monkeypatch.setattr(workflow.os, "replace", fail_replace)
    with pytest.raises(OSError, match="synthetic replace"):
        workflow.atomic_bytes(target, b"new checkpoint")
    assert target.read_bytes() == b"previous checkpoint"
    assert unrelated.read_bytes() == b"existing file"
    assert not list(tmp_path.glob(".workflow-*.tmp"))


@pytest.mark.asyncio
async def test_actual_process_crash_leaves_temp_but_resume_preserves_it_and_skips_generation(
    tmp_path,
):
    path = recipe(tmp_path, stages=1)
    backend = Backend([result()])
    service, client = runtime(tmp_path, backend)
    output = tmp_path / "out"
    report = await run_workflow(service, path, output)
    checkpoint_before = (output / "checkpoint.json").read_bytes()
    script = (
        "import os, sys\n"
        "from pathlib import Path\n"
        "from local_workbench import workflow\n"
        "workflow.os.replace = lambda *args: os._exit(23)\n"
        "workflow.atomic_bytes(Path(sys.argv[1]), b'interrupted replacement')\n"
    )
    crashed = subprocess.run(
        [sys.executable, "-c", script, str(output / "checkpoint.json")],
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert crashed.returncode == 23
    assert (output / "checkpoint.json").read_bytes() == checkpoint_before
    orphaned = list(output.glob(".workflow-*.tmp"))
    assert len(orphaned) == 1 and orphaned[0].read_bytes() == b"interrupted replacement"
    resumed = await run_workflow(service, path, output, resume=True)
    assert resumed == report and len(backend.calls) == 1
    assert orphaned[0].read_bytes() == b"interrupted replacement"
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        "payload_list",
        "payload_null",
        "missing_stages",
        "stages_null",
        "row_null",
        "attempts_object",
        "attempt_null",
        "attempt_number",
        "attempt_usage",
        "attempt_latency",
        "missing_attempt_status",
        "result_type",
        "checks_type",
        "checks_wrong_count",
        "unknown_payload",
        "unknown_row",
        "unknown_attempt",
        "artifact_path",
        "orphan_publication",
    ],
)
async def test_rehashed_malformed_checkpoint_fails_cleanly_before_any_resume_generation(
    tmp_path, change
):
    path = recipe(tmp_path, stages=1)
    backend = Backend([result()])
    service, client = runtime(tmp_path, backend)
    output = tmp_path / "out"
    await run_workflow(service, path, output)
    payload = load_checkpoint(output)
    row = payload["stages"][0]
    if change == "payload_list":
        payload = []
    elif change == "payload_null":
        payload = None
    elif change == "missing_stages":
        payload.pop("stages")
    elif change == "stages_null":
        payload["stages"] = None
    elif change == "row_null":
        payload["stages"][0] = None
    elif change == "attempts_object":
        row["attempts"] = {}
    elif change == "attempt_null":
        row["attempts"][0] = None
    elif change == "attempt_number":
        row["attempts"][0]["number"] = True
    elif change == "attempt_usage":
        row["attempts"][0]["usage"] = {"prompt_tokens": "1"}
    elif change == "attempt_latency":
        row["attempts"][0]["latency_seconds"] = "slow"
    elif change == "missing_attempt_status":
        row["attempts"][0].pop("status")
    elif change == "result_type":
        row["result"] = []
    elif change == "checks_type":
        row["checks"] = []
    elif change == "checks_wrong_count":
        row["checks"]["word_count"] += 100
    elif change == "unknown_payload":
        payload["private_path"] = "/private/not-for-output"
    elif change == "unknown_row":
        row["private_path"] = "/private/not-for-output"
    elif change == "unknown_attempt":
        row["attempts"][0]["private_path"] = "/private/not-for-output"
    elif change == "artifact_path":
        payload["artifacts"]["../personal.txt"] = "a" * 64
    elif change == "orphan_publication":
        payload.pop("artifacts")
    (output / "checkpoint.json").write_bytes(
        canonical({"payload": payload, "sha256": digest(payload)})
    )
    with pytest.raises(WorkbenchError) as error:
        await run_workflow(service, path, output, resume=True)
    assert error.value.code == "checkpoint_corrupt"
    assert "not-for-output" not in error.value.message
    assert len(backend.calls) == 1
    await client.aclose()


@pytest.mark.parametrize("payload", [[], None, "bad", 42, {"stages": None}])
def test_checkpoint_shape_is_checked_even_when_called_without_file_loader(payload):
    from local_workbench.workflow import verify_checkpoint

    with pytest.raises(WorkbenchError) as error:
        verify_checkpoint(payload, {}, None)
    assert error.value.code == "checkpoint_corrupt"


def test_checkpoint_size_limit_applies_to_the_read_request(tmp_path, monkeypatch):
    from local_workbench.workflow import MAX_CHECKPOINT_BYTES

    target = tmp_path / "checkpoint.json"
    with target.open("wb") as handle:
        handle.truncate(MAX_CHECKPOINT_BYTES + 1)
    original = Path.open
    reads = []

    class GuardedReader:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.handle.close()

        def read(self, size=-1):
            assert size == MAX_CHECKPOINT_BYTES + 1, "Unbounded checkpoint read"
            reads.append(size)
            return self.handle.read(size)

    def guarded(path, *args, **kwargs):
        handle = original(path, *args, **kwargs)
        return GuardedReader(handle) if path == target else handle

    monkeypatch.setattr(Path, "open", guarded)
    with pytest.raises(WorkbenchError) as error:
        load_checkpoint(tmp_path)
    assert error.value.code == "checkpoint_corrupt"
    assert reads == [MAX_CHECKPOINT_BYTES + 1]


def test_checkpoint_duplicate_json_keys_are_rejected(tmp_path):
    (tmp_path / "checkpoint.json").write_text('{"payload":{},"payload":[],"sha256":"x"}')
    with pytest.raises(WorkbenchError) as error:
        load_checkpoint(tmp_path)
    assert error.value.code == "checkpoint_corrupt"


def test_checkpoint_writer_refuses_oversize_without_replacing_existing_file(tmp_path, monkeypatch):
    from local_workbench import workflow

    target = tmp_path / "checkpoint.json"
    target.write_bytes(b"previous checkpoint")
    monkeypatch.setattr(workflow, "MAX_CHECKPOINT_BYTES", 100)
    with pytest.raises(WorkbenchError) as error:
        workflow.save_checkpoint(tmp_path, {"large": "x" * 200})
    assert error.value.code == "checkpoint_too_large"
    assert target.read_bytes() == b"previous checkpoint"


@pytest.mark.parametrize("ticks", ["", "```", "````````"])
def test_hostile_source_markup_stays_inside_a_literal_evidence_block(ticks):
    from local_workbench.workflow import check_stage, render_markdown

    source = (
        "An exact source quote.\n" + ticks + "\n\n# Approved final answer\n\n"
        "![remote](https://example.com/track.png)\n"
        '<script>alert("not executed")</script>\n~~~\n'
    )
    definition = Recipe.model_validate(
        {
            "title": "Synthetic document",
            "evidence": [{"id": "source.one", "text": source, "approved": True}],
            "stages": [
                {
                    "id": "one",
                    "title": "Stage",
                    "instructions": "Draft",
                    "evidence_ids": ["source.one"],
                    "min_words": 1,
                }
            ],
        }
    )
    value = result(
        used_evidence_ids=["source.one"],
        quotes=[{"evidence_id": "source.one", "quote": source}],
    )
    check_stage(value, definition.stages[0], definition.evidence)
    document = render_markdown(definition, {"stages": [{"result": value}]}).decode()
    block = document.split("[source.one]\n\n", 1)[1].rstrip("\n")
    lines = block.splitlines()
    assert lines[0].endswith("text")
    fence = lines[0][:-4]
    assert set(fence) == {"`"} and len(fence) >= 3 and len(fence) > len(ticks)
    assert lines[-1] == fence
    assert block[len(lines[0]) + 1 : -(len(fence) + 1)] == source
