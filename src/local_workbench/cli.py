from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import uvicorn

from .app import create_app
from .config import load_settings
from .contracts import TaskRequest
from .evaluation import evaluate
from .runtime import Runtime, WorkbenchError
from .workflow import run_workflow


def parser():
    root = argparse.ArgumentParser(description="Local inference gateway and evidence-bounded tasks")
    root.add_argument(
        "--config",
        default=os.environ.get("LOCAL_WORKBENCH_CONFIG"),
        help="JSON config; LOCAL_WORKBENCH_CONFIG is also supported",
    )
    sub = root.add_subparsers(dest="command", required=True)
    server = sub.add_parser("serve", help="Run one gateway process")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8090)
    sub.add_parser("doctor", help="Inspect provider reachability and installed models")
    run = sub.add_parser("run", help="Run a structured task from JSON")
    run.add_argument("--input", type=Path, required=True)
    run.add_argument("--output", type=Path)
    evaluation = sub.add_parser("evaluate", help="Run synthetic task cases against real Ollama")
    evaluation.add_argument("--cases", type=Path, required=True)
    evaluation.add_argument("--output", type=Path)
    evaluation.add_argument(
        "--hardware", help="Operator-supplied hardware description, labeled as such"
    )
    workflow = sub.add_parser("workflow", help="Run or resume a bounded document recipe")
    workflow.add_argument("--recipe", type=Path, required=True)
    workflow.add_argument("--output-dir", type=Path, required=True)
    workflow.add_argument("--resume", action="store_true")
    sub.add_parser("mcp", help="Optional stdio MCP tools (install the mcp extra)")
    return root


def write_result(value, target=None):
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if target:
        if target.exists():
            raise ValueError("output already exists; select a new output path")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as handle:
            handle.write(text)
    else:
        print(text, end="")


async def execute(args, settings):
    runtime = Runtime(settings)
    try:
        if args.command == "doctor":
            report = await runtime.health()
        elif args.command == "workflow":
            report = await run_workflow(runtime, args.recipe, args.output_dir, args.resume)
        elif args.command == "evaluate":
            report = await evaluate(runtime, args.cases, args.hardware)
        else:
            if args.input.stat().st_size > settings.max_request_bytes:
                raise ValueError("input exceeds configured request limit")
            task = TaskRequest.model_validate(json.loads(args.input.read_text(encoding="utf-8")))
            report = await runtime.task(task)
        write_result(report, getattr(args, "output", None))
        if args.command == "doctor":
            return 0 if report["status"] == "ok" else 1
        if args.command == "evaluate":
            return 0 if report["passed"] == report["total"] else 1
        if args.command == "workflow":
            return 0 if report["status"] == "completed" else 1
        return 0
    finally:
        await runtime.close()


def main(argv=None):
    args = parser().parse_args(argv)
    if not args.config:
        parser().error("--config or LOCAL_WORKBENCH_CONFIG is required")
    try:
        settings = load_settings(args.config)
        if args.command == "serve":
            if args.host not in {"127.0.0.1", "localhost", "::1"} and not settings.api_token_env:
                raise ValueError("non-loopback binding requires configured api_token_env")
            uvicorn.run(
                create_app(settings),
                host=args.host,
                port=args.port,
                access_log=False,
                log_level="warning",
            )
            return 0
        if args.command == "mcp":
            from .mcp_server import run

            run(settings)
            return 0
        return asyncio.run(execute(args, settings))
    except WorkbenchError as exc:
        print(
            json.dumps(
                {
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                        "status": "unreviewed_draft",
                    }
                }
            ),
            file=sys.stderr,
        )
    except (ValueError, OSError, ImportError):
        # Never echo a rejected packet, private path or environment value.
        print(
            json.dumps(
                {
                    "error": {
                        "code": "configuration_or_input_error",
                        "message": "Check configuration, input shape, output availability and optional dependencies.",
                    }
                }
            ),
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
