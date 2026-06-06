#!/usr/bin/env python3
"""Minimal stdio MCP server for Spec Coding progress tools.

The server intentionally wraps the stdlib-only spec_progress module. It avoids
duplicating task-state rules; CLI, hook, validator, and MCP share one state
machine.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from spec_progress import (  # noqa: E402
    SpecProgressError,
    command_block,
    command_complete,
    command_resume,
    command_skip,
    command_start,
    command_status,
    specs_path,
)


def _base_dir() -> Path:
    """Directory that all specs_dir arguments must stay within.

    Defaults to the server's current working directory (the repository it was
    launched in). Override with SPEC_CODING_BASE_DIR when the server runs from
    a different location than the project root.
    """
    return Path(os.environ.get("SPEC_CODING_BASE_DIR", os.getcwd())).resolve()


def _checked_specs_dir(args: dict[str, Any]) -> str:
    raw = args.get("specs_dir")
    if not isinstance(raw, str) or not raw.strip():
        raise SpecProgressError("specs_dir is required")
    # Raises SpecProgressError on ../ traversal outside the base directory.
    specs_path(raw, base_dir=_base_dir())
    return raw


TOOLS = [
    {
        "name": "spec_status",
        "description": "Return workflow, approval, current task, task counts, and next executable wave.",
        "inputSchema": {
            "type": "object",
            "properties": {"specs_dir": {"type": "string"}},
            "required": ["specs_dir"],
        },
    },
    {
        "name": "spec_resume",
        "description": "Check progress.md/spec.yml/tasks.md and return safe resume state.",
        "inputSchema": {
            "type": "object",
            "properties": {"specs_dir": {"type": "string"}},
            "required": ["specs_dir"],
        },
    },
    {
        "name": "spec_start_task",
        "description": "Mark a task active and write progress/spec.yml checkpoints.",
        "inputSchema": {
            "type": "object",
            "properties": {"specs_dir": {"type": "string"}, "task_id": {"type": "string"}},
            "required": ["specs_dir", "task_id"],
        },
    },
    {
        "name": "spec_complete_task",
        "description": "Complete a task with verification evidence and update tasks.md/progress.md/spec.yml.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "specs_dir": {"type": "string"},
                "task_id": {"type": "string"},
                "evidence": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["specs_dir", "task_id", "evidence"],
        },
    },
    {
        "name": "spec_block_task",
        "description": "Record a blocker for the current task without marking it complete.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "specs_dir": {"type": "string"},
                "task_id": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["specs_dir", "task_id", "reason"],
        },
    },
    {
        "name": "spec_skip_task",
        "description": "Skip a task only when explicit human approval evidence is provided.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "specs_dir": {"type": "string"},
                "task_id": {"type": "string"},
                "approval": {"type": "string"},
            },
            "required": ["specs_dir", "task_id", "approval"],
        },
    },
]


def response(request_id: Any, result: Any = None, error: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    return payload


def text_result(data: Any) -> dict[str, Any]:
    if isinstance(data, str):
        text = data
    else:
        text = json.dumps(data, ensure_ascii=False, indent=2)
    return {"content": [{"type": "text", "text": text}]}


def call_tool(name: str, args: dict[str, Any]) -> Any:
    if name == "spec_status":
        return command_status(_checked_specs_dir(args))
    if name == "spec_resume":
        return command_resume(_checked_specs_dir(args))
    if name == "spec_start_task":
        return command_start(_checked_specs_dir(args), args["task_id"])
    if name == "spec_complete_task":
        return command_complete(_checked_specs_dir(args), args["task_id"], args["evidence"], args.get("notes", ""))
    if name == "spec_block_task":
        return command_block(_checked_specs_dir(args), args["task_id"], args["reason"])
    if name == "spec_skip_task":
        return command_skip(_checked_specs_dir(args), args["task_id"], args["approval"])
    raise SpecProgressError(f"Unknown tool: {name}")


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    if method == "initialize":
        return response(
            request_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "spec-coding-progress", "version": "0.1.0"},
            },
        )
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return response(request_id, {"tools": TOOLS})
    if method == "tools/call":
        params = message.get("params", {})
        try:
            result = call_tool(params.get("name", ""), params.get("arguments", {}) or {})
            return response(request_id, text_result(result))
        except SpecProgressError as exc:
            return response(request_id, error={"code": -32000, "message": str(exc)})
    return response(request_id, error={"code": -32601, "message": f"Unknown method: {method}"})


def main() -> int:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            reply = handle(message)
            if reply is not None:
                print(json.dumps(reply, ensure_ascii=False), flush=True)
        except Exception as exc:  # Keep MCP server alive for debuggable tool errors.
            print(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32099, "message": str(exc)},
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
