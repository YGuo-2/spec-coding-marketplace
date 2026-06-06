#!/usr/bin/env python3
"""Spec Coding progress, resume, and task-state utilities.

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
        "plugins/spec-coding/assets/templates/",
        "plugins/spec-coding/skills/",
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

    return f"""# Spec Coding Progress

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
    for name in ("tasks.md", "progress.md", "spec.yml"):
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
    parser = argparse.ArgumentParser(description="Spec Coding progress and resume utilities")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "resume", "waves", "sync-check", "guard-commit", "pre-acceptance", "init"):
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
    except SpecProgressError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
