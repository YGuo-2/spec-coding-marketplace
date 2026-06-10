#!/usr/bin/env python3
"""Spce workflow progress, resume, and task-state utilities.

This module is intentionally stdlib-only. The CLI, MCP wrapper, validator,
and git-hook template all share this implementation so progress enforcement
does not split into several subtly different rule sets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


TASK_RE = re.compile(
    r"^(?P<indent>\s*)-\s+\[(?P<mark>[ xX~])\]\s+(?:\*\*)?"
    r"(?P<task_id>[TB]-\d+)\s*[:：](?:\*\*)?\s*(?P<title>.+?)\s*$"
)
FIELD_RE = re.compile(r"^\s*-\s+(?P<key>[^:：]+?)\s*[:：]\s*(?P<value>.*)$")
TOP_FIELD_RE = re.compile(r"^>\s+\*\*(?P<key>[^*]+):\*\*\s*(?P<value>.*)$")
TASK_TOP_FIELD_RE = re.compile(
    r"^(?P<indent>\s*)(?P<prefix>>\s+\*\*)(?P<label>[^*：:]+)(?P<colon>[：:])(?P<suffix>\*\*\s*)(?P<value>.*)$"
)
CHECKBOX_RE = re.compile(r"-\s+\[[ xX~]\]")
# English risk terms use word boundaries so "cache" does not match inside
# "caching layer" and "incident" does not match unrelated prose. CJK terms have
# no word boundaries, so they are matched directly.
_HIGH_RISK_EN = (
    r"auth|authorization|authentication|payment|billing|database|migration|"
    r"data[\s-]?repair|concurrency|distributed|cache|secret|encryption|"
    r"sensitive|incident|rollback|hotfix|privacy|security|transaction|"
    r"lock[\s-]?free|deadlock|sla|credential|token|permission|access[\s-]?control"
)
_HIGH_RISK_CJK = (
    r"鉴权|认证|授权|支付|计费|数据库|迁移|数据修复|并发|分布式|缓存|密钥|"
    r"凭证|令牌|加密|敏感|事故|回滚|热修复|隐私|安全|事务|死锁|权限|访问控制"
)
HIGH_RISK_RE = re.compile(
    rf"(?:\b(?:{_HIGH_RISK_EN})\b)|(?:{_HIGH_RISK_CJK})",
    re.IGNORECASE,
)


FIELD_ALIASES = {
    "status": {"status", "状态"},
    "files": {"files", "涉及文件", "file", "path"},
    "verify": {"verify", "verification", "验证命令", "验证标准", "test", "测试"},
    "evidence": {"evidence", "验证证据", "证据"},
    "depends_on": {"depends_on", "dependencies", "依赖", "depends on"},
    "risk": {"risk", "风险", "风险等级"},
    "covers": {"covers", "coverage", "覆盖", "覆盖需求"},
    "parallelizable": {"parallelizable", "并行", "可并行"},
    "blocker": {"blocker", "阻塞原因", "blocked by"},
    "completed_at": {"completed_at", "完成时间"},
    "notes": {"notes", "备注"},
}

FIELD_LABELS = {
    "status": "状态",
    "files": "涉及文件",
    "verify": "验证命令",
    "evidence": "验证证据",
    "depends_on": "依赖",
    "risk": "风险",
    "covers": "覆盖",
    "parallelizable": "可并行",
    "blocker": "阻塞原因",
    "completed_at": "完成时间",
    "notes": "备注",
}

VALID_TASK_STATES = {"pending", "active", "blocked", "done", "skipped", "interrupted"}
VALID_PROGRESS_STATES = {"Draft", "Approved", "In Progress", "Blocked", "Completed", "Accepted"}
VALID_APPROVAL_STATES = {"pending", "approved", "reapproval-required"}
ACCEPTANCE_STATE_FILE = "acceptance_state.json"
ACCEPTANCE_FIXES_FILE = "acceptance-fixes.md"
ACCEPTANCE_AGENT_ROLES = {"first_wave", "adversarial"}
ACCEPTANCE_AGENT_RESULTS = {"PASS", "ACTIONABLE_ISSUES"}
ACCEPTANCE_SEVERITIES = {"P0", "P1", "P2", "P3", "P4"}
ACCEPTANCE_BLOCKING_SEVERITIES = {"P0", "P1", "P2"}
ACCEPTANCE_FULL_FIX_ROUNDS = 3
ACCEPTANCE_MAX_ROUNDS = 6


class SpecProgressError(Exception):
    """Expected user-facing progress error."""


@dataclass
class Task:
    task_id: str
    title: str
    mark: str
    start: int
    end: int
    fields: dict[str, str] = field(default_factory=dict)

    @property
    def checkbox_state(self) -> str:
        if self.mark.lower() == "x":
            return "done"
        if self.mark == "~":
            return "skipped"
        return "pending"

    @property
    def state(self) -> str:
        explicit = self.fields.get("status", "").strip().lower()
        if explicit in VALID_TASK_STATES and self.checkbox_state == "pending":
            return explicit
        return self.checkbox_state

    @property
    def depends_on(self) -> list[str]:
        value = self.fields.get("depends_on", "")
        if not value or value.lower() in {"none", "n/a"} or value in {"无", "暂无"}:
            return []
        return [
            item.strip()
            for item in re.split(r"[,，、\s]+", value)
            if re.match(r"^[TB]-\d+$", item.strip())
        ]

    @property
    def risk(self) -> str:
        value = self.fields.get("risk", "").strip().lower()
        if value:
            return value
        if HIGH_RISK_RE.search(self.title + " " + " ".join(self.fields.values())):
            return "high"
        return "low"

    @property
    def is_high_risk(self) -> bool:
        return self.risk in {"high", "critical", "高", "高风险"} or bool(
            HIGH_RISK_RE.search(self.risk)
        )

    @property
    def parallelizable(self) -> bool:
        value = self.fields.get("parallelizable", "").strip().lower()
        return value in {"true", "yes", "y", "1", "是", "可", "parallel"}


@dataclass
class Progress:
    workflow: str = "unknown"
    mode: str = "strict"
    status: str = "Draft"
    current_task: str = "n/a"
    approval: str = "pending"
    last_checkpoint: str = "n/a"
    branch: str = "n/a"
    last_known_commit: str = "n/a"
    resume_summary: dict[str, str] = field(default_factory=dict)
    active_state: dict[str, str] = field(default_factory=dict)
    completed_rows: list[str] = field(default_factory=list)
    recovery_notes: list[str] = field(default_factory=list)


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SpecProgressError(
            f"{path} is not valid UTF-8 (decode error at byte {exc.start}); "
            "re-save the file as UTF-8 and retry"
        ) from exc


def write_text(path: Path, content: str) -> None:
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, object]:
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        raise SpecProgressError(f"{path.name} is not valid JSON: {exc}") from exc


def write_json(path: Path, data: dict[str, object]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def normalize_field_key(raw: str) -> str | None:
    cleaned = re.sub(r"^[^\w\u4e00-\u9fff]+", "", raw.strip())
    cleaned = cleaned.strip().lower().replace("-", "_")
    for canonical, aliases in FIELD_ALIASES.items():
        if cleaned in {alias.lower().replace("-", "_") for alias in aliases}:
            return canonical
    return None


def specs_path(specs_dir: str | Path, base_dir: str | Path | None = None) -> Path:
    """Resolve specs_dir to an absolute path.

    When base_dir is provided, the resolved path must stay inside it; this
    blocks ``../`` traversal from untrusted callers (e.g. the MCP server) that
    would otherwise read or write files outside the intended repository.
    """
    resolved = Path(specs_dir).resolve()
    if base_dir is not None:
        base = Path(base_dir).resolve()
        if resolved != base and base not in resolved.parents:
            raise SpecProgressError(
                f"specs_dir must stay within {base}; refusing path {resolved}"
            )
    return resolved


def workflow_matches(specs_dir: str | Path) -> list[str]:
    """All workflows whose required artifacts are present.

    Single source of truth for workflow detection. detect_workflow picks one
    (bugfix takes priority because design.md is shared); the validator uses the
    full list to flag the ambiguous multi-match case.
    """
    root = specs_path(specs_dir)
    matches: list[str] = []
    if (root / "bugfix.md").is_file() and (root / "design.md").is_file():
        matches.append("bugfix")
    if (root / "design.md").is_file() and (root / "requirements.md").is_file():
        matches.append("design-first")
    if (root / "product.md").is_file() and (root / "architecture.md").is_file():
        matches.append("requirements-first")
    return matches


def detect_workflow(specs_dir: str | Path) -> str:
    matches = workflow_matches(specs_dir)
    return matches[0] if matches else "unknown"


def primary_artifacts(workflow: str) -> list[str]:
    return {
        "requirements-first": ["product.md", "architecture.md"],
        "design-first": ["design.md", "requirements.md"],
        "bugfix": ["bugfix.md", "design.md"],
    }.get(workflow, [])


def expected_prefix(workflow: str) -> str:
    return "B" if workflow == "bugfix" else "T"


def parse_tasks(specs_dir: str | Path) -> list[Task]:
    path = specs_path(specs_dir) / "tasks.md"
    if not path.is_file():
        raise SpecProgressError("tasks.md is missing")
    lines = read_text(path).splitlines()
    starts: list[tuple[int, re.Match[str]]] = []
    for index, line in enumerate(lines):
        match = TASK_RE.match(line)
        if match:
            starts.append((index, match))

    tasks: list[Task] = []
    for pos, (start, match) in enumerate(starts):
        end = starts[pos + 1][0] if pos + 1 < len(starts) else len(lines)
        fields: dict[str, str] = {}
        for line in lines[start + 1 : end]:
            field_match = FIELD_RE.match(line)
            if not field_match:
                continue
            key = normalize_field_key(field_match.group("key"))
            if key:
                fields[key] = field_match.group("value").strip()
        tasks.append(
            Task(
                task_id=match.group("task_id"),
                title=match.group("title").strip(),
                mark=match.group("mark"),
                start=start,
                end=end,
                fields=fields,
            )
        )
    return tasks


def get_task(specs_dir: str | Path, task_id: str) -> Task:
    for task in parse_tasks(specs_dir):
        if task.task_id == task_id:
            return task
    raise SpecProgressError(f"Task not found: {task_id}")


def task_stats(tasks: list[Task]) -> dict[str, int]:
    stats = {state: 0 for state in VALID_TASK_STATES}
    for task in tasks:
        stats[task.state] = stats.get(task.state, 0) + 1
    return stats


def completed_ids(tasks: list[Task]) -> set[str]:
    return {task.task_id for task in tasks if task.state in {"done", "skipped"}}


def next_executable_tasks(tasks: list[Task]) -> list[Task]:
    done = completed_ids(tasks)
    active = [task for task in tasks if task.state in {"active", "blocked", "interrupted"}]
    if active:
        return active[:1]
    ready = [
        task
        for task in tasks
        if task.state == "pending" and all(dep in done for dep in task.depends_on)
    ]
    if not ready:
        return []
    first_high = next((task for task in ready if task.is_high_risk), None)
    if first_high:
        return [first_high]
    parallel = [task for task in ready if task.parallelizable and not task.is_high_risk]
    return parallel or ready[:1]


def task_sort_key(task_id: str) -> tuple[str, int, str]:
    """Numeric-aware sort key so B-2 precedes B-10 (not lexicographic)."""
    match = re.match(r"^([A-Za-z]+)-(\d+)$", task_id)
    if match:
        return (match.group(1), int(match.group(2)), "")
    return (task_id, 0, task_id)


def execution_waves(tasks: list[Task]) -> list[list[str]]:
    remaining = {task.task_id: task for task in tasks if task.state == "pending"}
    done = completed_ids(tasks)
    waves: list[list[str]] = []
    while remaining:
        ready = [
            task
            for task in remaining.values()
            if all(dep in done or dep not in remaining for dep in task.depends_on)
        ]
        if not ready:
            cycle = sorted(remaining, key=task_sort_key)
            raise SpecProgressError(
                "Circular or unresolvable task dependency detected among: "
                + ", ".join(cycle)
            )
        high = [task for task in ready if task.is_high_risk]
        if high:
            wave = [sorted(high, key=lambda task: task_sort_key(task.task_id))[0].task_id]
        else:
            parallel = [task for task in ready if task.parallelizable]
            chosen = parallel or [sorted(ready, key=lambda task: task_sort_key(task.task_id))[0]]
            wave = sorted((task.task_id for task in chosen), key=task_sort_key)
        waves.append(wave)
        for task_id in wave:
            done.add(task_id)
            remaining.pop(task_id, None)
    return waves


def task_progress_values(tasks: list[Task]) -> tuple[int, int, str]:
    completed = sum(1 for task in tasks if task.state in {"done", "skipped"})
    total = len(tasks)
    return completed, total, f"{completed} / {total} 已完成"


def workflow_status_for_tasks(tasks: list[Task], preferred: str | None = None) -> str:
    if preferred in {"Draft", "Approved", "Accepted"}:
        return preferred
    if any(task.state == "blocked" for task in tasks):
        return "Blocked"
    if any(task.state in {"pending", "active", "interrupted"} for task in tasks):
        return "In Progress" if any(task.state in {"active", "done", "skipped", "interrupted"} for task in tasks) else "Approved"
    return "Completed"


def current_task_for_tasks(tasks: list[Task]) -> str:
    next_task = next_executable_tasks(tasks)
    return next_task[0].task_id if next_task else "n/a"


def update_tasks_metadata(
    specs_dir: str | Path,
    *,
    status: str | None = None,
    current_task: str | None = None,
    log_row: str | None = None,
) -> None:
    """Synchronize the human-readable tasks.md summary with task states."""
    path = specs_path(specs_dir) / "tasks.md"
    if not path.is_file():
        return
    tasks = parse_tasks(specs_dir)
    completed, total, progress = task_progress_values(tasks)
    derived_status = status or workflow_status_for_tasks(tasks)
    derived_current = current_task if current_task is not None else current_task_for_tasks(tasks)
    replacements = {
        "状态": derived_status,
        "status": derived_status,
        "当前任务": derived_current,
        "current task": derived_current,
        "进度": progress,
        "progress": f"{completed}/{total}",
        "最后更新": now(),
        "last updated": now(),
    }
    lines = read_text(path).splitlines()
    updated: list[str] = []
    for line in lines:
        match = TASK_TOP_FIELD_RE.match(line)
        if match:
            key = match.group("label").strip().lower()
            value = replacements.get(key)
            if value is not None:
                line = (
                    f"{match.group('indent')}{match.group('prefix')}{match.group('label')}{match.group('colon')}"
                    f"{match.group('suffix')}{value}"
                )
        updated.append(line)

    if log_row:
        insert_at: int | None = None
        placeholder_at: int | None = None
        in_log = False
        for index, line in enumerate(updated):
            stripped = line.strip()
            if stripped in {"## 完成日志", "## Completed Work Log"}:
                in_log = True
                continue
            if in_log and stripped.startswith("## ") and stripped not in {"## 完成日志", "## Completed Work Log"}:
                insert_at = index
                break
            if in_log and stripped.startswith("|"):
                if "暂无完成任务" in stripped or stripped.startswith("| —") or stripped.startswith("| - | - |"):
                    placeholder_at = index
                elif "---" not in stripped and "Task ID" not in stripped and "任务 ID" not in stripped:
                    insert_at = index + 1
        if in_log:
            if placeholder_at is not None:
                updated[placeholder_at] = log_row
            else:
                updated.insert(insert_at if insert_at is not None else len(updated), log_row)
        else:
            updated.extend(
                [
                    "",
                    "## 完成日志",
                    "",
                    "| 任务 ID | 完成时间 | Commit Hash | 验证证据 | 备注 |",
                    "|:---|:---|:---|:---|:---|",
                    log_row,
                ]
            )
    write_text(path, "\n".join(updated))


def update_task_fields(
    specs_dir: str | Path,
    task_id: str,
    mark: str | None,
    updates: dict[str, str],
) -> None:
    path = specs_path(specs_dir) / "tasks.md"
    lines = read_text(path).splitlines()
    task = get_task(specs_dir, task_id)
    block = lines[task.start : task.end]
    task_line = block[0]
    if mark is not None:
        task_line = CHECKBOX_RE.sub(f"- [{mark}]", task_line, count=1)

    update_keys = set(updates)
    kept_body: list[str] = []
    for line in block[1:]:
        match = FIELD_RE.match(line)
        if match and normalize_field_key(match.group("key")) in update_keys:
            continue
        kept_body.append(line)

    inserted = [f"  - {FIELD_LABELS[key]}: {value}" for key, value in updates.items()]
    new_block = [task_line] + inserted + kept_body
    write_text(path, "\n".join(lines[: task.start] + new_block + lines[task.end :]))


def task_digest(tasks: list[Task]) -> str:
    payload = "\n".join(
        json.dumps(
            {
                "task_id": task.task_id,
                "title": task.title,
                "mark": task.mark,
                "fields": dict(sorted(task.fields.items())),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        for task in tasks
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def task_phase_for_line(lines: list[str], start: int) -> str:
    phase = "Unphased"
    for line in lines[: start + 1]:
        stripped = line.strip()
        if stripped.startswith("## "):
            phase = stripped.lstrip("#").strip()
    return phase


def build_review_units(specs_dir: str | Path, task_ids: list[str] | None = None) -> list[dict[str, object]]:
    root = specs_path(specs_dir)
    tasks = parse_tasks(root)
    include = set(task_ids or [task.task_id for task in tasks])
    lines = read_text(root / "tasks.md").splitlines()
    units: list[dict[str, object]] = []
    group: list[Task] = []
    group_phase = ""
    for task in tasks:
        if task.task_id not in include:
            continue
        phase = task_phase_for_line(lines, task.start)
        force_standalone = task.is_high_risk
        if force_standalone:
            if group:
                units.append(review_unit_payload(len(units) + 1, group, group_phase))
                group = []
                group_phase = ""
            units.append(review_unit_payload(len(units) + 1, [task], phase))
            continue
        if group and (phase != group_phase or len(group) >= 3):
            units.append(review_unit_payload(len(units) + 1, group, group_phase))
            group = []
        group.append(task)
        group_phase = phase
    if group:
        units.append(review_unit_payload(len(units) + 1, group, group_phase))
    return units


def review_unit_payload(index: int, tasks: list[Task], phase: str) -> dict[str, object]:
    return {
        "unit_id": f"U-{index:03d}",
        "task_ids": [task.task_id for task in tasks],
        "phase": phase,
        "status": "pending",
        "review_status": "pending",
        "adversarial_status": "pending",
        "round_started": None,
        "last_result": None,
    }


def acceptance_path(specs_dir: str | Path) -> Path:
    return specs_path(specs_dir) / ACCEPTANCE_STATE_FILE


def acceptance_fixes_path(specs_dir: str | Path) -> Path:
    return specs_path(specs_dir) / ACCEPTANCE_FIXES_FILE


def default_acceptance_state(specs_dir: str | Path) -> dict[str, object]:
    root = specs_path(specs_dir)
    tasks = parse_tasks(root)
    return {
        "schema_version": 1,
        "workflow": detect_workflow(root),
        "status": "initialized",
        "round": 1,
        "max_rounds": ACCEPTANCE_MAX_ROUNDS,
        "full_fix_rounds": ACCEPTANCE_FULL_FIX_ROUNDS,
        "policy": "rounds 1-3 fix all actionable issues; round 4+ auto-fix P0-P2 only",
        "original_task_ids": [task.task_id for task in tasks],
        "original_task_digest": task_digest(tasks),
        "task_count": len(tasks),
        "review_units": build_review_units(root),
        "agents": [],
        "issues": [],
        "fixes": [],
        "deferred_issues": [],
        "affected_units": [],
        "created_at": now(),
        "updated_at": now(),
        "completed_at": None,
        "notes": [],
    }


def load_acceptance_state(specs_dir: str | Path) -> dict[str, object]:
    path = acceptance_path(specs_dir)
    if not path.is_file():
        raise SpecProgressError(f"{ACCEPTANCE_STATE_FILE} is missing; run acceptance-init first")
    data = read_json(path)
    if data.get("schema_version") != 1:
        raise SpecProgressError(f"Unsupported {ACCEPTANCE_STATE_FILE} schema_version: {data.get('schema_version')}")
    return data


def save_acceptance_state(specs_dir: str | Path, state: dict[str, object]) -> None:
    state["updated_at"] = now()
    write_json(acceptance_path(specs_dir), state)


def acceptance_summary(state: dict[str, object]) -> dict[str, object]:
    agents = list(state.get("agents", []))
    units = list(state.get("review_units", []))
    issues = list(state.get("issues", []))
    fixes = list(state.get("fixes", []))
    current_round = int(state.get("round", 1))
    round_agents = [
        agent for agent in agents
        if int(agent.get("round", 0)) == current_round
    ]
    pending_units = [
        unit["unit_id"] for unit in units
        if unit.get("status") != "pass"
    ]
    pending_agents = [
        agent["agent_id"] for agent in round_agents
        if agent.get("status") in {"planned", "running"}
    ]
    return {
        "status": state.get("status"),
        "round": current_round,
        "policy": state.get("policy"),
        "task_count": state.get("task_count"),
        "units": len(units),
        "pending_units": pending_units,
        "agents": {
            "total": len(agents),
            "current_round": len(round_agents),
            "pending_or_running": pending_agents,
            "completed": [
                agent["agent_id"] for agent in round_agents
                if agent.get("status") == "completed"
            ],
        },
        "issues": {
            "total": len(issues),
            "open": [
                issue["issue_id"] for issue in issues
                if issue.get("status") in {"open", "planned"}
            ],
            "deferred": [
                issue.get("issue_id") for issue in state.get("deferred_issues", [])
            ],
        },
        "fixes": {
            "total": len(fixes),
            "pending": [
                fix["fix_id"] for fix in fixes
                if fix.get("status") in {"pending", "active"}
            ],
        },
        "affected_units": state.get("affected_units", []),
    }


def validate_original_tasks_unchanged(specs_dir: str | Path, state: dict[str, object]) -> None:
    tasks = parse_tasks(specs_dir)
    current_ids = [task.task_id for task in tasks]
    original_ids = list(state.get("original_task_ids", []))
    if current_ids != original_ids:
        raise SpecProgressError(
            "Original tasks.md task IDs changed during acceptance; "
            "acceptance fixes must use acceptance-fixes.md instead of appending to tasks.md"
        )
    current_digest = task_digest(tasks)
    if current_digest != state.get("original_task_digest"):
        raise SpecProgressError(
            "Original tasks.md task text changed during acceptance; update specs and reapprove before final acceptance"
        )


def agent_id_for(round_number: int, role: str, unit_id: str) -> str:
    short_role = "R" if role == "first_wave" else "A"
    return f"round-{round_number}-{short_role}-{unit_id}"


def planned_agents_for_units(round_number: int, units: list[dict[str, object]]) -> list[dict[str, object]]:
    agents: list[dict[str, object]] = []
    for unit in units:
        for role in ("first_wave", "adversarial"):
            agents.append(
                {
                    "agent_id": agent_id_for(round_number, role, str(unit["unit_id"])),
                    "round": round_number,
                    "role": role,
                    "unit_id": unit["unit_id"],
                    "task_ids": unit["task_ids"],
                    "status": "planned",
                    "result": None,
                    "started_at": None,
                    "completed_at": None,
                    "report": "",
                }
            )
    return agents


def severity_blocks_round(severity: str, round_number: int) -> bool:
    if round_number <= ACCEPTANCE_FULL_FIX_ROUNDS:
        return severity in ACCEPTANCE_SEVERITIES
    return severity in ACCEPTANCE_BLOCKING_SEVERITIES


def issue_should_fix(issue: dict[str, object], round_number: int) -> bool:
    if issue.get("status") in {"fixed", "deferred"}:
        return False
    return severity_blocks_round(str(issue.get("severity", "")).upper(), round_number)


def find_unit(state: dict[str, object], unit_id: str) -> dict[str, object]:
    for unit in state.get("review_units", []):
        if unit.get("unit_id") == unit_id:
            return unit
    raise SpecProgressError(f"Review unit not found: {unit_id}")


def find_agent(state: dict[str, object], agent_id: str) -> dict[str, object]:
    for agent in state.get("agents", []):
        if agent.get("agent_id") == agent_id:
            return agent
    raise SpecProgressError(f"Acceptance agent not found: {agent_id}")


def find_issue(state: dict[str, object], issue_id: str) -> dict[str, object]:
    for issue in state.get("issues", []):
        if issue.get("issue_id") == issue_id:
            return issue
    raise SpecProgressError(f"Acceptance issue not found: {issue_id}")


def find_fix(state: dict[str, object], fix_id: str) -> dict[str, object]:
    for fix in state.get("fixes", []):
        if fix.get("fix_id") == fix_id:
            return fix
    raise SpecProgressError(f"Acceptance fix not found: {fix_id}")


def create_acceptance_fixes_file(specs_dir: str | Path, state: dict[str, object]) -> None:
    fixes = list(state.get("fixes", []))
    rows: list[str] = []
    if fixes:
        for fix in fixes:
            rows.append(
                "| {fix_id} | {issue_ids} | {severity} | {unit_ids} | {status} | {evidence} |".format(
                    fix_id=fix.get("fix_id", ""),
                    issue_ids=", ".join(fix.get("issue_ids", [])),
                    severity=fix.get("severity", ""),
                    unit_ids=", ".join(fix.get("unit_ids", [])),
                    status=fix.get("status", ""),
                    evidence=str(fix.get("evidence", "pending")).replace("|", "\\|"),
                )
            )
    else:
        rows.append("| - | - | - | - | - | - |")
    deferred = list(state.get("deferred_issues", []))
    deferred_rows = []
    if deferred:
        for issue in deferred:
            deferred_rows.append(
                f"- {issue.get('issue_id')} ({issue.get('severity')}): {issue.get('title')} - {issue.get('reason')}"
            )
    else:
        deferred_rows.append("- n/a")
    content = f"""# Acceptance Fixes

> **Source:** docs/specs/{ACCEPTANCE_STATE_FILE}
> **Round:** {state.get('round')}
> **Policy:** {state.get('policy')}
> **Original tasks:** {state.get('task_count')} frozen tasks; do not append acceptance fixes to tasks.md

## Fix Queue

| Fix ID | Issue IDs | Severity | Units | Status | Evidence |
|:---|:---|:---|:---|:---|:---|
{chr(10).join(rows)}

## Deferred Issues

{chr(10).join(deferred_rows)}
"""
    write_text(acceptance_fixes_path(specs_dir), content)


def git_output(args: list[str], cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return "n/a"
    if result.returncode != 0:
        return "n/a"
    return result.stdout.strip() or "n/a"


def git_available(specs_dir: str | Path) -> bool:
    """True when git is installed and specs_dir sits inside a work tree.

    dirty_paths returns [] both when nothing changed and when git is
    unavailable; callers that enforce safety (guard-commit, resume) use this to
    avoid treating "cannot tell" as "clean".
    """
    return git_output(["rev-parse", "--is-inside-work-tree"], specs_path(specs_dir)) == "true"


def repo_root_for(specs_dir: str | Path) -> Path:
    specs = specs_path(specs_dir)
    root = git_output(["rev-parse", "--show-toplevel"], specs)
    if root != "n/a":
        return Path(root)
    return specs


def current_branch(specs_dir: str | Path) -> str:
    return git_output(["rev-parse", "--abbrev-ref", "HEAD"], repo_root_for(specs_dir))


def current_commit(specs_dir: str | Path) -> str:
    return git_output(["rev-parse", "--short", "HEAD"], repo_root_for(specs_dir))


def dirty_paths(specs_dir: str | Path, staged: bool = False) -> list[str]:
    root = repo_root_for(specs_dir)
    args = ["diff", "--cached", "--name-only"] if staged else ["status", "--porcelain"]
    output = git_output(args, root)
    if output == "n/a":
        return []
    paths: list[str] = []
    for line in output.splitlines():
        value = line.strip()
        if not value:
            continue
        if not staged:
            value = value[3:] if len(value) > 3 else value
        paths.append(value.replace("\\", "/"))
    return paths


def business_paths(paths: list[str]) -> list[str]:
    ignored_prefixes = {
        "docs/specs/",
        "docs/",
        "README",
        "plugins/spce-workflow/assets/templates/",
        "plugins/spce-workflow/skills/",
    }
    result = []
    for path in paths:
        if any(path.startswith(prefix) for prefix in ignored_prefixes):
            continue
        result.append(path)
    return result


def _parse_bullet(line: str) -> tuple[str, str] | None:
    match = re.match(r"^-\s+(?P<key>[^:：]+?)\s*[:：]\s*(?P<value>.*)$", line)
    if not match:
        return None
    return match.group("key").strip(), match.group("value").strip()


def parse_progress(specs_dir: str | Path) -> Progress:
    path = specs_path(specs_dir) / "progress.md"
    if not path.is_file():
        return Progress()
    lines = read_text(path).splitlines()
    progress = Progress()
    section = ""
    for line in lines:
        top = TOP_FIELD_RE.match(line)
        if top:
            key = top.group("key").strip().lower().replace(" ", "_")
            value = top.group("value").strip()
            if key == "workflow":
                progress.workflow = value
            elif key == "mode":
                progress.mode = value
            elif key == "status":
                progress.status = value
            elif key == "current_task":
                progress.current_task = value
            elif key == "approval":
                progress.approval = value
            elif key == "last_checkpoint":
                progress.last_checkpoint = value
            elif key == "branch":
                progress.branch = value
            elif key == "last_known_commit":
                progress.last_known_commit = value
            continue
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if section == "Resume Summary" and line.startswith("- "):
            parsed = _parse_bullet(line)
            if parsed:
                progress.resume_summary[parsed[0]] = parsed[1]
        elif section == "Active Task State" and line.startswith("- "):
            parsed = _parse_bullet(line)
            if parsed:
                progress.active_state[parsed[0]] = parsed[1]
        elif section == "Completed Work Log" and line.startswith("|"):
            if "---" not in line and "Task ID" not in line:
                progress.completed_rows.append(line)
        elif section == "Recovery Notes" and line.startswith("- "):
            progress.recovery_notes.append(line)
    return progress


def render_progress(
    specs_dir: str | Path,
    workflow: str,
    status: str,
    current_task: str,
    approval: str,
    active_status: str,
    verification: str,
    blockers: str,
    note: str,
    append_log: str | None = None,
    goal: str | None = None,
    files_expected: str | None = None,
) -> str:
    previous = parse_progress(specs_dir)
    rows = list(previous.completed_rows)
    if append_log:
        rows.append(append_log)
    if not rows:
        rows = ["| - | - | - | - | - |"]
    checkpoint = now()
    branch = current_branch(specs_dir)
    commit = current_commit(specs_dir)
    next_action = "Run spec_status, then continue the current task."
    if status == "Completed":
        next_action = "Run pre-acceptance, then final acceptance."
    elif status == "Blocked":
        next_action = "Resolve blocker or revise specs before coding."
    elif active_status == "interrupted":
        next_action = "Inspect diff and verification evidence before continuing."

    # Preserve carried-over state across writes; explicit args win, otherwise
    # reuse what the previous progress.md recorded so resume context survives.
    if goal is None:
        goal = previous.resume_summary.get("Goal", "n/a")
    if files_expected is None:
        files_expected = previous.active_state.get("Files expected to change", "n/a")
    verification_text = verification or previous.active_state.get("Verification needed", "") or "n/a"

    return f"""# Spce workflow Progress

> **Workflow:** {workflow}
> **Mode:** {previous.mode if previous.mode != 'unknown' else 'strict'}
> **Status:** {status}
> **Current Task:** {current_task}
> **Approval:** {approval}
> **Last Checkpoint:** {checkpoint}
> **Branch:** {branch}
> **Last Known Commit:** {commit}

## Resume Summary
- Goal: {goal or 'n/a'}
- Approved specs: {', '.join(primary_artifacts(workflow) + ['tasks.md'])}
- Current task: {current_task}
- Next safe action: {next_action}
- Blockers: {blockers or 'n/a'}

## Active Task State
- Task ID: {current_task}
- Status: {active_status}
- Started at: {checkpoint if active_status == 'active' else 'n/a'}
- Verification needed: {verification_text}
- Files expected to change: {files_expected or 'n/a'}

## Completed Work Log
| Task ID | Time | Commit/State | Verification | Notes |
|:---|:---|:---|:---|:---|
{chr(10).join(rows)}

## Recovery Notes
- {note or 'n/a'}
"""


def write_progress(
    specs_dir: str | Path,
    workflow: str,
    status: str,
    current_task: str,
    approval: str,
    active_status: str,
    verification: str = "",
    blockers: str = "",
    note: str = "",
    append_log: str | None = None,
    goal: str | None = None,
    files_expected: str | None = None,
) -> None:
    path = specs_path(specs_dir) / "progress.md"
    write_text(
        path,
        render_progress(
            specs_dir,
            workflow,
            status,
            current_task,
            approval,
            active_status,
            verification,
            blockers,
            note,
            append_log,
            goal=goal,
            files_expected=files_expected,
        ),
    )


def parse_flat_yml(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    data: dict[str, str] = {}
    for line in read_text(path).splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if not key:
            continue
        data[key] = value.strip()
    return data


def sha256_file(path: Path) -> str:
    if not path.is_file():
        return "missing"
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def extract_requirement_ids(specs_dir: str | Path, workflow: str) -> list[str]:
    root = specs_path(specs_dir)
    ids: set[str] = set()
    pattern = re.compile(r"\b(?:US|REQ|AC|NFR|BUG|FIX|SAFE)-\d+(?:\.\d+)?\b")
    for name in primary_artifacts(workflow):
        path = root / name
        if path.is_file():
            ids.update(pattern.findall(read_text(path)))
    return sorted(ids)


def task_graph_value(tasks: list[Task]) -> str:
    edges: list[str] = []
    for task in tasks:
        if not task.depends_on:
            edges.append(task.task_id)
        for dep in task.depends_on:
            edges.append(f"{dep}->{task.task_id}")
    return ", ".join(edges) if edges else "n/a"


def write_spec_index(
    specs_dir: str | Path,
    workflow: str,
    current_task: str,
    approval: str,
    mode: str = "strict",
    risk_level: str | None = None,
    preserve_hashes: bool = False,
) -> None:
    root = specs_path(specs_dir)
    tasks = parse_tasks(root)
    existing = parse_flat_yml(root / "spec.yml")
    if risk_level is None:
        risk_level = "high" if any(task.is_high_risk for task in tasks) else "low"
    artifact_names = primary_artifacts(workflow) + ["tasks.md", "progress.md", "spec.yml"]
    if preserve_hashes and existing.get("artifact_hashes"):
        hashes = existing["artifact_hashes"]
    else:
        hashes = ", ".join(
            f"{name}={sha256_file(root / name)}" for name in primary_artifacts(workflow)
        )
    content = "\n".join(
        [
            "schema_version: 1",
            f"workflow: {workflow}",
            f"mode: {mode}",
            f"approval: {approval}",
            f"risk_level: {risk_level}",
            f"current_task: {current_task}",
            f"last_checkpoint: {now()}",
            f"artifacts: {', '.join(artifact_names)}",
            f"requirements: {', '.join(extract_requirement_ids(root, workflow)) or 'n/a'}",
            f"task_ids: {', '.join(task.task_id for task in tasks) or 'n/a'}",
            f"task_graph: {task_graph_value(tasks)}",
            f"artifact_hashes: {hashes or 'n/a'}",
        ]
    )
    write_text(root / "spec.yml", content)


def ensure_progress_files(specs_dir: str | Path, workflow: str) -> None:
    root = specs_path(specs_dir)
    tasks = parse_tasks(root)
    current = next_executable_tasks(tasks)
    current_task = current[0].task_id if current else "n/a"
    if not (root / "progress.md").is_file():
        write_progress(root, workflow, "Draft", current_task, "pending", "pending")
    if not (root / "spec.yml").is_file():
        write_spec_index(root, workflow, current_task, "pending")
    update_tasks_metadata(root, status="Draft", current_task=current_task)


def command_status(specs_dir: str | Path) -> dict[str, object]:
    workflow = detect_workflow(specs_dir)
    tasks = parse_tasks(specs_dir)
    stats = task_stats(tasks)
    ready = [task.task_id for task in next_executable_tasks(tasks)]
    progress = parse_progress(specs_dir)
    waves = execution_waves(tasks)
    return {
        "workflow": workflow,
        "progress_status": progress.status,
        "approval": progress.approval,
        "current_task": progress.current_task,
        "tasks": stats,
        "next_executable": ready,
        "execution_waves": waves,
    }


def command_acceptance_init(specs_dir: str | Path) -> dict[str, object]:
    pre = command_pre_acceptance(specs_dir)
    if not pre["ok"]:
        raise SpecProgressError("Pre-acceptance must pass before final acceptance: " + "; ".join(pre["issues"]))
    path = acceptance_path(specs_dir)
    if path.is_file():
        state = load_acceptance_state(specs_dir)
        validate_original_tasks_unchanged(specs_dir, state)
        return acceptance_summary(state)
    state = default_acceptance_state(specs_dir)
    state["status"] = "agents-planned"
    state["agents"] = planned_agents_for_units(int(state["round"]), list(state["review_units"]))
    save_acceptance_state(specs_dir, state)
    return acceptance_summary(state)


def command_acceptance_status(specs_dir: str | Path) -> dict[str, object]:
    state = load_acceptance_state(specs_dir)
    validate_original_tasks_unchanged(specs_dir, state)
    return acceptance_summary(state)


def command_acceptance_start_agent(specs_dir: str | Path, agent_id: str) -> dict[str, object]:
    state = load_acceptance_state(specs_dir)
    validate_original_tasks_unchanged(specs_dir, state)
    agent = find_agent(state, agent_id)
    if agent.get("status") == "completed":
        raise SpecProgressError(f"Acceptance agent is already completed: {agent_id}")
    agent["status"] = "running"
    agent["started_at"] = now()
    state["status"] = "agents-running"
    save_acceptance_state(specs_dir, state)
    return acceptance_summary(state)


def command_acceptance_complete_agent(
    specs_dir: str | Path,
    agent_id: str,
    result: str,
    report: str,
) -> dict[str, object]:
    normalized = result.upper()
    if normalized not in ACCEPTANCE_AGENT_RESULTS:
        raise SpecProgressError(
            f"result must be one of {', '.join(sorted(ACCEPTANCE_AGENT_RESULTS))}"
        )
    state = load_acceptance_state(specs_dir)
    validate_original_tasks_unchanged(specs_dir, state)
    agent = find_agent(state, agent_id)
    agent["status"] = "completed"
    agent["result"] = normalized
    agent["completed_at"] = now()
    agent["report"] = report or "n/a"
    unit = find_unit(state, str(agent["unit_id"]))
    if agent["role"] == "first_wave":
        unit["review_status"] = "pass" if normalized == "PASS" else "issues"
    else:
        unit["adversarial_status"] = "pass" if normalized == "PASS" else "issues"
    if unit.get("review_status") == "pass" and unit.get("adversarial_status") == "pass":
        unit["status"] = "pass"
        unit["last_result"] = "PASS"
    elif "issues" in {unit.get("review_status"), unit.get("adversarial_status")}:
        unit["status"] = "issues"
        unit["last_result"] = "ACTIONABLE_ISSUES"

    round_number = int(state.get("round", 1))
    current_agents = [
        item for item in state.get("agents", [])
        if int(item.get("round", 0)) == round_number
    ]
    if current_agents and all(item.get("status") == "completed" for item in current_agents):
        state["status"] = "review-complete"
    save_acceptance_state(specs_dir, state)
    return acceptance_summary(state)


def command_acceptance_record_issue(
    specs_dir: str | Path,
    unit_id: str,
    severity: str,
    title: str,
    evidence: str,
    task_ids: str = "",
    agent_id: str = "",
) -> dict[str, object]:
    normalized = severity.upper()
    if normalized not in ACCEPTANCE_SEVERITIES:
        raise SpecProgressError(f"severity must be one of {', '.join(sorted(ACCEPTANCE_SEVERITIES))}")
    if not title.strip() or not evidence.strip():
        raise SpecProgressError("Acceptance issue requires title and evidence")
    state = load_acceptance_state(specs_dir)
    validate_original_tasks_unchanged(specs_dir, state)
    unit = find_unit(state, unit_id)
    issue_number = len(state.get("issues", [])) + 1
    issue_id = f"I-{issue_number:03d}"
    if task_ids.strip():
        selected_tasks = [item.strip() for item in re.split(r"[,，、\s]+", task_ids) if item.strip()]
    else:
        selected_tasks = list(unit.get("task_ids", []))
    unknown = sorted(set(selected_tasks) - set(unit.get("task_ids", [])), key=task_sort_key)
    if unknown:
        raise SpecProgressError(
            f"Issue task IDs must belong to {unit_id}; unexpected: {', '.join(unknown)}"
        )
    issue = {
        "issue_id": issue_id,
        "round": int(state.get("round", 1)),
        "unit_id": unit_id,
        "task_ids": selected_tasks,
        "severity": normalized,
        "title": title.strip(),
        "evidence": evidence.strip(),
        "agent_id": agent_id or "n/a",
        "status": "open",
        "created_at": now(),
        "fix_id": None,
    }
    state.setdefault("issues", []).append(issue)
    unit["status"] = "issues"
    unit["last_result"] = "ACTIONABLE_ISSUES"
    affected = set(state.get("affected_units", []))
    affected.add(unit_id)
    state["affected_units"] = sorted(affected)
    save_acceptance_state(specs_dir, state)
    return acceptance_summary(state)


def command_acceptance_plan_fixes(specs_dir: str | Path) -> dict[str, object]:
    state = load_acceptance_state(specs_dir)
    validate_original_tasks_unchanged(specs_dir, state)
    round_number = int(state.get("round", 1))
    existing_issue_ids = {
        issue_id
        for fix in state.get("fixes", [])
        for issue_id in fix.get("issue_ids", [])
    }
    deferred_ids = {issue.get("issue_id") for issue in state.get("deferred_issues", [])}
    for issue in state.get("issues", []):
        issue_id = str(issue["issue_id"])
        if issue_id in existing_issue_ids or issue_id in deferred_ids:
            continue
        if issue_should_fix(issue, round_number):
            fix_id = f"F-{len(state.get('fixes', [])) + 1:03d}"
            fix = {
                "fix_id": fix_id,
                "round": round_number,
                "issue_ids": [issue_id],
                "unit_ids": [issue["unit_id"]],
                "task_ids": list(issue.get("task_ids", [])),
                "severity": issue["severity"],
                "title": issue["title"],
                "status": "pending",
                "evidence": "pending",
                "created_at": now(),
                "completed_at": None,
            }
            issue["status"] = "planned"
            issue["fix_id"] = fix_id
            state.setdefault("fixes", []).append(fix)
        else:
            deferred = dict(issue)
            deferred["reason"] = f"round {round_number} only auto-fixes P0-P2"
            issue["status"] = "deferred"
            state.setdefault("deferred_issues", []).append(deferred)
    if int(state.get("round", 1)) >= ACCEPTANCE_MAX_ROUNDS:
        blocking = [
            issue for issue in state.get("issues", [])
            if issue.get("status") in {"open", "planned"} and str(issue.get("severity")) in ACCEPTANCE_BLOCKING_SEVERITIES
        ]
        if blocking:
            state["status"] = "blocked"
            state.setdefault("notes", []).append(
                f"Reached max acceptance rounds ({ACCEPTANCE_MAX_ROUNDS}) with blocking P0-P2 issues"
            )
    elif any(fix.get("status") in {"pending", "active"} for fix in state.get("fixes", [])):
        state["status"] = "fixes-planned"
    create_acceptance_fixes_file(specs_dir, state)
    save_acceptance_state(specs_dir, state)
    return acceptance_summary(state)


def command_acceptance_fix_start(specs_dir: str | Path, fix_id: str) -> dict[str, object]:
    state = load_acceptance_state(specs_dir)
    validate_original_tasks_unchanged(specs_dir, state)
    fix = find_fix(state, fix_id)
    if fix.get("status") == "done":
        raise SpecProgressError(f"Acceptance fix is already done: {fix_id}")
    fix["status"] = "active"
    fix["started_at"] = now()
    state["status"] = "fixes-running"
    create_acceptance_fixes_file(specs_dir, state)
    save_acceptance_state(specs_dir, state)
    return acceptance_summary(state)


def command_acceptance_fix_complete(
    specs_dir: str | Path,
    fix_id: str,
    evidence: str,
) -> dict[str, object]:
    if not evidence.strip():
        raise SpecProgressError("Completing an acceptance fix requires evidence")
    state = load_acceptance_state(specs_dir)
    validate_original_tasks_unchanged(specs_dir, state)
    fix = find_fix(state, fix_id)
    fix["status"] = "done"
    fix["evidence"] = evidence.strip()
    fix["completed_at"] = now()
    for issue_id in fix.get("issue_ids", []):
        issue = find_issue(state, issue_id)
        issue["status"] = "fixed"
    affected = set(state.get("affected_units", []))
    affected.update(fix.get("unit_ids", []))
    state["affected_units"] = sorted(affected)
    if not any(item.get("status") in {"pending", "active"} for item in state.get("fixes", [])):
        state["status"] = "fixes-complete"
    create_acceptance_fixes_file(specs_dir, state)
    save_acceptance_state(specs_dir, state)
    return acceptance_summary(state)


def command_acceptance_next_round(specs_dir: str | Path) -> dict[str, object]:
    state = load_acceptance_state(specs_dir)
    validate_original_tasks_unchanged(specs_dir, state)
    round_number = int(state.get("round", 1))
    if round_number >= ACCEPTANCE_MAX_ROUNDS:
        state["status"] = "blocked"
        state.setdefault("notes", []).append(
            f"Cannot start round {round_number + 1}; max rounds is {ACCEPTANCE_MAX_ROUNDS}"
        )
        save_acceptance_state(specs_dir, state)
        return acceptance_summary(state)
    if any(fix.get("status") in {"pending", "active"} for fix in state.get("fixes", [])):
        raise SpecProgressError("Pending acceptance fixes remain; complete or defer them before next round")
    affected = list(state.get("affected_units", []))
    if not affected:
        affected = [
            str(unit["unit_id"]) for unit in state.get("review_units", [])
            if unit.get("status") != "pass"
        ]
    if not affected:
        state["status"] = "ready-to-finish"
        save_acceptance_state(specs_dir, state)
        return acceptance_summary(state)
    state["round"] = round_number + 1
    for unit in state.get("review_units", []):
        if unit.get("unit_id") in affected:
            unit["status"] = "pending"
            unit["review_status"] = "pending"
            unit["adversarial_status"] = "pending"
            unit["round_started"] = state["round"]
    review_units = [
        unit for unit in state.get("review_units", [])
        if unit.get("unit_id") in affected
    ]
    state.setdefault("agents", []).extend(planned_agents_for_units(int(state["round"]), review_units))
    state["affected_units"] = []
    state["status"] = "agents-planned"
    save_acceptance_state(specs_dir, state)
    return acceptance_summary(state)


def command_acceptance_finish(specs_dir: str | Path) -> dict[str, object]:
    state = load_acceptance_state(specs_dir)
    validate_original_tasks_unchanged(specs_dir, state)
    unresolved = [
        issue for issue in state.get("issues", [])
        if issue.get("status") not in {"fixed", "deferred"}
    ]
    pending_agents = [
        agent for agent in state.get("agents", [])
        if agent.get("status") in {"planned", "running"}
    ]
    pending_fixes = [
        fix for fix in state.get("fixes", [])
        if fix.get("status") in {"pending", "active"}
    ]
    if pending_agents or pending_fixes or unresolved:
        details = []
        if pending_agents:
            details.append("pending agents: " + ", ".join(agent["agent_id"] for agent in pending_agents))
        if pending_fixes:
            details.append("pending fixes: " + ", ".join(fix["fix_id"] for fix in pending_fixes))
        if unresolved:
            details.append("unresolved issues: " + ", ".join(issue["issue_id"] for issue in unresolved))
        raise SpecProgressError("Acceptance cannot finish; " + "; ".join(details))
    state["status"] = "accepted"
    state["completed_at"] = now()
    save_acceptance_state(specs_dir, state)
    workflow = detect_workflow(specs_dir)
    write_progress(
        specs_dir,
        workflow,
        "Accepted",
        "n/a",
        "approved",
        "done",
        verification=f"Final acceptance passed through {ACCEPTANCE_STATE_FILE}",
        note="Final acceptance accepted",
    )
    update_tasks_metadata(specs_dir, status="Accepted", current_task="n/a")
    write_spec_index(specs_dir, workflow, "n/a", "approved")
    return acceptance_summary(state)


def assert_can_start(specs_dir: str | Path, task_id: str) -> Task:
    tasks = parse_tasks(specs_dir)
    task = next((candidate for candidate in tasks if candidate.task_id == task_id), None)
    if not task:
        raise SpecProgressError(f"Task not found: {task_id}")
    if task.state != "pending":
        raise SpecProgressError(f"Task {task_id} is not pending (state: {task.state})")
    done = completed_ids(tasks)
    missing = [dep for dep in task.depends_on if dep not in done]
    if missing:
        raise SpecProgressError(f"Task {task_id} has unmet dependencies: {', '.join(missing)}")
    ready = [candidate.task_id for candidate in next_executable_tasks(tasks)]
    if ready and task_id not in ready:
        raise SpecProgressError(
            f"Task {task_id} is not in the next executable wave: {', '.join(ready)}"
        )
    return task


def command_start(specs_dir: str | Path, task_id: str) -> str:
    workflow = detect_workflow(specs_dir)
    task = assert_can_start(specs_dir, task_id)
    update_task_fields(specs_dir, task_id, None, {"status": "active"})
    update_tasks_metadata(specs_dir, status="In Progress", current_task=task_id)
    write_progress(
        specs_dir,
        workflow,
        "In Progress",
        task_id,
        "approved",
        "active",
        verification=task.fields.get("verify", ""),
        note=f"Started {task_id}",
        goal=task.title,
        files_expected=task.fields.get("files", "") or "n/a",
    )
    write_spec_index(specs_dir, workflow, task_id, "approved")
    return f"Started {task_id}"


def command_complete(specs_dir: str | Path, task_id: str, evidence: str, notes: str = "") -> str:
    if not evidence.strip():
        raise SpecProgressError("Completion requires verification evidence")
    workflow = detect_workflow(specs_dir)
    task = get_task(specs_dir, task_id)
    if task.state not in {"pending", "active", "interrupted"}:
        raise SpecProgressError(f"Task {task_id} cannot be completed from state {task.state}")
    update_task_fields(
        specs_dir,
        task_id,
        "x",
        {
            "status": "done",
            "evidence": evidence,
            "completed_at": now(),
            "notes": notes or "n/a",
        },
    )
    tasks = parse_tasks(specs_dir)
    remaining = [candidate for candidate in tasks if candidate.state in {"pending", "active", "blocked", "interrupted"}]
    status = "Completed" if not remaining else "In Progress"
    next_task = next_executable_tasks(tasks)
    current = "n/a" if status == "Completed" else (next_task[0].task_id if next_task else "n/a")
    commit = current_commit(specs_dir)
    log_row = f"| {task_id} | {now()} | {commit} | {evidence} | {notes or 'n/a'} |"
    update_tasks_metadata(specs_dir, status=status, current_task=current, log_row=log_row)
    write_progress(
        specs_dir,
        workflow,
        status,
        current,
        "approved",
        "done" if status == "Completed" else "pending",
        verification=evidence,
        note=f"Completed {task_id}",
        append_log=log_row,
    )
    write_spec_index(specs_dir, workflow, current, "approved")
    return f"Completed {task_id}; workflow status: {status}"


def command_block(specs_dir: str | Path, task_id: str, reason: str) -> str:
    if not reason.strip():
        raise SpecProgressError("Blocking a task requires a reason")
    workflow = detect_workflow(specs_dir)
    update_task_fields(specs_dir, task_id, None, {"status": "blocked", "blocker": reason})
    update_tasks_metadata(specs_dir, status="Blocked", current_task=task_id)
    write_progress(
        specs_dir,
        workflow,
        "Blocked",
        task_id,
        "approved",
        "blocked",
        blockers=reason,
        note=f"Blocked {task_id}",
    )
    write_spec_index(specs_dir, workflow, task_id, "approved")
    return f"Blocked {task_id}"


def command_skip(specs_dir: str | Path, task_id: str, approval: str) -> str:
    if not approval.strip():
        raise SpecProgressError("Skipping a task requires explicit human approval evidence")
    workflow = detect_workflow(specs_dir)
    update_task_fields(
        specs_dir,
        task_id,
        "~",
        {"status": "skipped", "evidence": approval, "completed_at": now()},
    )
    tasks = parse_tasks(specs_dir)
    remaining = [task for task in tasks if task.state in {"pending", "active", "blocked", "interrupted"}]
    status = "Completed" if not remaining else "In Progress"
    next_task = next_executable_tasks(tasks)
    current = "n/a" if status == "Completed" else (next_task[0].task_id if next_task else "n/a")
    log_row = f"| {task_id} | {now()} | skipped | {approval} | human-approved skip |"
    update_tasks_metadata(specs_dir, status=status, current_task=current, log_row=log_row)
    write_progress(
        specs_dir,
        workflow,
        status,
        current,
        "approved",
        "skipped",
        verification=approval,
        note=f"Skipped {task_id}",
        append_log=log_row,
    )
    write_spec_index(specs_dir, workflow, current, "approved")
    return f"Skipped {task_id}; workflow status: {status}"


def command_resume(specs_dir: str | Path) -> dict[str, object]:
    workflow = detect_workflow(specs_dir)
    root = specs_path(specs_dir)
    issues: list[str] = []
    warnings: list[str] = []
    try:
        tasks = parse_tasks(root)
    except SpecProgressError as exc:
        # tasks.md missing or unreadable: report instead of crashing so the
        # caller still gets a structured, actionable resume payload.
        return {
            "workflow": workflow,
            "status": "blocked",
            "issues": [str(exc)],
            "warnings": [],
            "current_task": "n/a",
            "next_executable": [],
        }
    progress = parse_progress(root)
    index = parse_flat_yml(root / "spec.yml")
    if not (root / "progress.md").is_file():
        issues.append("progress.md is missing")
    if not (root / "spec.yml").is_file():
        issues.append("spec.yml is missing")
    if progress.workflow not in {"unknown", workflow}:
        issues.append(f"progress.md workflow {progress.workflow} does not match {workflow}")
    if index.get("workflow") and index.get("workflow") != workflow:
        issues.append(f"spec.yml workflow {index.get('workflow')} does not match {workflow}")
    task_ids = {task.task_id for task in tasks}
    if progress.current_task not in task_ids and progress.current_task != "n/a":
        issues.append(f"progress.md current task does not exist: {progress.current_task}")
    if index.get("current_task") not in task_ids and index.get("current_task") not in {None, "n/a"}:
        issues.append(f"spec.yml current task does not exist: {index.get('current_task')}")
    active = [task for task in tasks if task.state == "active"]
    interrupted = False
    git_ok = git_available(root)
    if not git_ok:
        warnings.append("git is unavailable; cannot detect dirty business-code changes")
    if active and git_ok and business_paths(dirty_paths(root)):
        interrupted = True
        warnings.append(
            f"active task {active[0].task_id} has dirty business-code changes; treat as interrupted"
        )
    status = "interrupted" if interrupted else ("blocked" if any(task.state == "blocked" for task in tasks) else "ready")
    return {
        "workflow": workflow,
        "status": status,
        "issues": issues,
        "warnings": warnings,
        "current_task": progress.current_task,
        "next_executable": [task.task_id for task in next_executable_tasks(tasks)],
    }


def parse_hashes(value: str) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for item in value.split(","):
        if "=" not in item:
            continue
        key, digest = item.split("=", 1)
        hashes[key.strip()] = digest.strip()
    return hashes


def command_sync_check(specs_dir: str | Path, write: bool = False) -> dict[str, object]:
    root = specs_path(specs_dir)
    workflow = detect_workflow(root)
    index = parse_flat_yml(root / "spec.yml")
    issues: list[str] = []
    suggestions: list[str] = []
    task_ids = ", ".join(task.task_id for task in parse_tasks(root)) or "n/a"
    if index.get("task_ids") and index.get("task_ids") != task_ids:
        issues.append("spec.yml task_ids drift from tasks.md")
    old_hashes = parse_hashes(index.get("artifact_hashes", ""))
    have_baseline = bool(old_hashes)
    for artifact in primary_artifacts(workflow):
        old = old_hashes.get(artifact)
        new = sha256_file(root / artifact)
        if new == "missing":
            issues.append(f"{artifact} is missing but referenced by the spec index")
        elif old is not None and old != new:
            issues.append(f"{artifact} changed since last approved index")
        elif old is None and have_baseline:
            # Baseline exists but this artifact was never hashed: a newly added
            # spec file that bypassed reapproval.
            issues.append(f"{artifact} is new and missing from the approved index")
    if issues:
        suggestions.append("Review spec changes, rebuild tasks if needed, then request reapproval.")
        if write:
            write_spec_index(
                root,
                workflow,
                index.get("current_task", "n/a"),
                "reapproval-required",
                mode=index.get("mode", "strict"),
                risk_level=index.get("risk_level", "medium"),
                preserve_hashes=True,
            )
    return {"issues": issues, "suggestions": suggestions}


def progress_file_paths(specs_dir: str | Path) -> set[str]:
    """Progress files as paths relative to the repo root (forward slashes).

    Derived from the supplied specs_dir so the guard works regardless of where
    the specs live, instead of assuming docs/specs/.
    """
    root = repo_root_for(specs_dir)
    specs = specs_path(specs_dir)
    paths: set[str] = set()
    for name in ("tasks.md", "progress.md", "spec.yml", ACCEPTANCE_STATE_FILE, ACCEPTANCE_FIXES_FILE):
        target = specs / name
        try:
            relative = target.relative_to(root)
        except ValueError:
            relative = Path(name)
        paths.add(relative.as_posix())
    return paths


def command_guard_commit(specs_dir: str | Path) -> dict[str, object]:
    paths = dirty_paths(specs_dir, staged=True)
    business = business_paths(paths)
    progress_paths = progress_file_paths(specs_dir)
    progress_changed = any(path.replace("\\", "/") in progress_paths for path in paths)
    hint = ", ".join(sorted(progress_paths))
    if business and not progress_changed:
        return {
            "ok": False,
            "message": (
                "Business-code changes are staged while spec progress files are unchanged. "
                f"Update {hint} before committing."
            ),
            "business_paths": business,
        }
    return {"ok": True, "message": "Spec progress guard passed", "business_paths": business}


def command_pre_acceptance(specs_dir: str | Path) -> dict[str, object]:
    tasks = parse_tasks(specs_dir)
    resume = command_resume(specs_dir)
    issues = list(resume["issues"])
    unchecked = [task.task_id for task in tasks if task.state in {"pending", "active", "blocked", "interrupted"}]
    missing_evidence = [
        task.task_id
        for task in tasks
        if task.state in {"done", "skipped"} and not task.fields.get("evidence")
    ]
    if unchecked:
        issues.append(f"Unchecked or unresolved tasks remain: {', '.join(unchecked)}")
    if missing_evidence:
        issues.append(f"Completed/skipped tasks missing evidence: {', '.join(missing_evidence)}")
    if business_paths(dirty_paths(specs_dir)):
        issues.append("Dirty business-code changes remain in the worktree")
    return {
        "ok": not issues,
        "issues": issues,
        "message": (
            "Pre-acceptance passed; strict multi-agent final acceptance is still required."
            if not issues
            else "Pre-acceptance found issues; strict final acceptance must not start yet."
        ),
    }


def format_json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Spce workflow progress and resume utilities")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in (
        "status",
        "resume",
        "waves",
        "sync-check",
        "guard-commit",
        "pre-acceptance",
        "init",
        "acceptance-init",
        "acceptance-status",
        "acceptance-plan-fixes",
        "acceptance-next-round",
        "acceptance-finish",
    ):
        cmd = sub.add_parser(name)
        cmd.add_argument("specs_dir")
    start = sub.add_parser("start")
    start.add_argument("specs_dir")
    start.add_argument("task_id")
    complete = sub.add_parser("complete")
    complete.add_argument("specs_dir")
    complete.add_argument("task_id")
    complete.add_argument("--evidence", required=True)
    complete.add_argument("--notes", default="")
    block = sub.add_parser("block")
    block.add_argument("specs_dir")
    block.add_argument("task_id")
    block.add_argument("--reason", required=True)
    skip = sub.add_parser("skip")
    skip.add_argument("specs_dir")
    skip.add_argument("task_id")
    skip.add_argument("--approval", required=True)
    sync = sub.choices["sync-check"]
    sync.add_argument("--write", action="store_true")
    acceptance_start = sub.add_parser("acceptance-start-agent")
    acceptance_start.add_argument("specs_dir")
    acceptance_start.add_argument("agent_id")
    acceptance_complete = sub.add_parser("acceptance-complete-agent")
    acceptance_complete.add_argument("specs_dir")
    acceptance_complete.add_argument("agent_id")
    acceptance_complete.add_argument("--result", required=True)
    acceptance_complete.add_argument("--report", default="")
    acceptance_issue = sub.add_parser("acceptance-record-issue")
    acceptance_issue.add_argument("specs_dir")
    acceptance_issue.add_argument("--unit", required=True)
    acceptance_issue.add_argument("--severity", required=True)
    acceptance_issue.add_argument("--title", required=True)
    acceptance_issue.add_argument("--evidence", required=True)
    acceptance_issue.add_argument("--tasks", default="")
    acceptance_issue.add_argument("--agent", default="")
    acceptance_fix_start = sub.add_parser("acceptance-fix-start")
    acceptance_fix_start.add_argument("specs_dir")
    acceptance_fix_start.add_argument("fix_id")
    acceptance_fix_complete = sub.add_parser("acceptance-fix-complete")
    acceptance_fix_complete.add_argument("specs_dir")
    acceptance_fix_complete.add_argument("fix_id")
    acceptance_fix_complete.add_argument("--evidence", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            workflow = detect_workflow(args.specs_dir)
            ensure_progress_files(args.specs_dir, workflow)
            print(f"Initialized progress files for {workflow}")
            return 0
        if args.command == "status":
            print(format_json(command_status(args.specs_dir)))
            return 0
        if args.command == "resume":
            result = command_resume(args.specs_dir)
            print(format_json(result))
            return 1 if result["issues"] else 0
        if args.command == "waves":
            print(format_json({"execution_waves": execution_waves(parse_tasks(args.specs_dir))}))
            return 0
        if args.command == "start":
            print(command_start(args.specs_dir, args.task_id))
            return 0
        if args.command == "complete":
            print(command_complete(args.specs_dir, args.task_id, args.evidence, args.notes))
            return 0
        if args.command == "block":
            print(command_block(args.specs_dir, args.task_id, args.reason))
            return 0
        if args.command == "skip":
            print(command_skip(args.specs_dir, args.task_id, args.approval))
            return 0
        if args.command == "sync-check":
            result = command_sync_check(args.specs_dir, write=args.write)
            print(format_json(result))
            return 1 if result["issues"] else 0
        if args.command == "guard-commit":
            result = command_guard_commit(args.specs_dir)
            print(format_json(result))
            return 0 if result["ok"] else 1
        if args.command == "pre-acceptance":
            result = command_pre_acceptance(args.specs_dir)
            print(format_json(result))
            return 0 if result["ok"] else 1
        if args.command == "acceptance-init":
            print(format_json(command_acceptance_init(args.specs_dir)))
            return 0
        if args.command == "acceptance-status":
            print(format_json(command_acceptance_status(args.specs_dir)))
            return 0
        if args.command == "acceptance-start-agent":
            print(format_json(command_acceptance_start_agent(args.specs_dir, args.agent_id)))
            return 0
        if args.command == "acceptance-complete-agent":
            print(format_json(command_acceptance_complete_agent(args.specs_dir, args.agent_id, args.result, args.report)))
            return 0
        if args.command == "acceptance-record-issue":
            print(format_json(command_acceptance_record_issue(
                args.specs_dir,
                args.unit,
                args.severity,
                args.title,
                args.evidence,
                args.tasks,
                args.agent,
            )))
            return 0
        if args.command == "acceptance-plan-fixes":
            print(format_json(command_acceptance_plan_fixes(args.specs_dir)))
            return 0
        if args.command == "acceptance-fix-start":
            print(format_json(command_acceptance_fix_start(args.specs_dir, args.fix_id)))
            return 0
        if args.command == "acceptance-fix-complete":
            print(format_json(command_acceptance_fix_complete(args.specs_dir, args.fix_id, args.evidence)))
            return 0
        if args.command == "acceptance-next-round":
            print(format_json(command_acceptance_next_round(args.specs_dir)))
            return 0
        if args.command == "acceptance-finish":
            print(format_json(command_acceptance_finish(args.specs_dir)))
            return 0
    except SpecProgressError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
