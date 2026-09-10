from __future__ import annotations

import json
import platform
import time
from pathlib import Path

from .contracts import TaskRequest, digest
from .runtime import WorkbenchError


async def evaluate(runtime, cases_path: Path, hardware: str | None = None):
    if cases_path.stat().st_size > 1048576:
        raise ValueError("evaluation cases exceed 1 MiB")
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not 1 <= len(cases) <= 100:
        raise ValueError("provide one to one hundred evaluation cases")
    inventory = await runtime.health()
    if inventory["status"] != "ok":
        raise WorkbenchError(
            "evaluation_provider_unavailable",
            "All configured models must be installed before live evaluation.",
            503,
        )
    outcomes = []
    for case in cases:
        request = TaskRequest.model_validate(case["request"])
        started = time.monotonic()
        try:
            result = await runtime.task(request)
            expected = case.get("expected", {})
            checks = {
                "schema": result["validation"]["schema"] == "passed",
                "citations": result["validation"]["citations"] == "passed",
                "quotes": result["validation"]["quotes"] == "passed",
            }
            if "answerable" in expected:
                checks["answerable"] = result["result"]["answerable"] == expected["answerable"]
            if "required_evidence_ids" in expected:
                field = {
                    "product_brief": "facts",
                    "evidence_match": "matches",
                    "decision_review": "findings",
                }[request.kind]
                cited = {row["evidence_id"] for row in result["result"][field]}
                checks["required_evidence_ids"] = set(expected["required_evidence_ids"]).issubset(
                    cited
                )
            usage = result["usage"]
            outcome = {
                "id": case["id"],
                "passed": all(checks.values()),
                "checks": checks,
                "packet_sha256": result["packet_sha256"],
                "provider_attempts": result["provider_attempts"],
                "usage": usage,
                "generation_tokens_per_second": (
                    usage["eval_count"] / (usage["eval_duration"] / 1e9)
                )
                if usage.get("eval_duration", 0) > 0 and "eval_count" in usage
                else None,
            }
        except WorkbenchError as exc:
            outcome = {"id": case["id"], "passed": False, "error_code": exc.code}
        outcome["latency_seconds"] = round(time.monotonic() - started, 6)
        outcomes.append(outcome)
    return {
        "schema_version": 1,
        "mode": "live_ollama",
        "cases_sha256": digest(cases),
        "hardware": {
            "operator_description": hardware or "not supplied",
            "client_os": platform.system(),
            "client_arch": platform.machine(),
            "gpu_measurement": "not collected by this runner",
        },
        "models": inventory["models"],
        "results": outcomes,
        "passed": sum(row["passed"] for row in outcomes),
        "total": len(outcomes),
        "scope": "Measured transport, schema, citation, quote and fixture expectations; not a general intelligence or production-readiness benchmark.",
    }
