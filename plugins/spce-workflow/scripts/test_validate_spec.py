#!/usr/bin/env python3
"""Regression tests for the Spce workflow validator."""

from __future__ import annotations

import os
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPT_DIR.parent
TEMPLATES = PLUGIN_ROOT / "assets" / "templates"
VALIDATOR = SCRIPT_DIR / "validate_spec.py"
PROGRESS = SCRIPT_DIR / "spec_progress.py"


def run_validator(specs_dir: Path, workflow: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        [sys.executable, str(VALIDATOR), str(specs_dir), "--workflow", workflow],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=merged_env,
    )


def run_progress(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PROGRESS), *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def write(path: Path, content: str) -> None:
    path.write_text(content.strip() + "\n", encoding="utf-8")


def valid_product() -> str:
    return """
    # 产品规范

    ## 用户故事与验收标准

    ## Analyze Requirements / 需求分析结论

    - 歧义检查：术语和验收对象已定义。
    - 冲突检查：未发现互斥约束。
    - 失败路径：Security and validation failures are covered.
    - 并发 / 权限 / 数据风险：Authorization is required and no data migration is needed.

    ### US-001: Publish comments

    #### 验收标准

    - **GIVEN** a signed-in reader is viewing a post
    - **WHEN** the reader submits a non-empty comment
    - **THEN** the comment is saved and shown in the comment list

    ## 非功能性需求

    | ID | 类别 | 描述 | 标准 |
    |:---|:---|:---|:---|
    | NFR-001 | 安全 | Comments require authentication | Auth is enforced |
    """


def valid_architecture() -> str:
    return """
    # 技术架构

    ## 数据模型

    The Comment entity stores post id, author id, body, and timestamps.

    ## API / 接口

    POST /comments creates a comment for an authenticated user.

    ## Dependencies

    No new dependency is required.

    ## Error Handling

    Invalid input returns a validation error.

    ## Security

    Authorization requires a signed-in user.

    ```mermaid
    flowchart TD
        Request --> Service
        Service --> Store
    ```
    """


def valid_requirements() -> str:
    return """
    # 需求规范

    > **来源设计：** docs/specs/design.md

    ## 功能需求与验收标准

    ## Analyze Requirements / 需求分析结论

    - 歧义检查：设计来源和行为边界已定义。
    - 冲突检查：requirements.md 与 design.md 未冲突。
    - 失败路径：Retry failures and idempotency risks are covered.
    - 并发 / 权限 / 数据风险：No new authorization surface is introduced.

    ### REQ-001: Publish outbox event

    #### 验收标准

    - **GIVEN** an order has been created
    - **WHEN** the outbox worker processes pending records
    - **THEN** an order-created event is published

    ## 非功能性需求

    | ID | 类别 | 描述 | 来源设计约束 |
    |:---|:---|:---|:---|
    | NFR-001 | 可靠性 | Events are retried | Derived from design.md |

    ## 设计映射

    REQ-001 is derived from design.md section 4.
    """


def valid_design(level: str = "High Level Design", include_lld: bool = True) -> str:
    lld = ""
    if include_lld:
        lld = """
        ## Low Level Design 细节

        - **模块 / 类职责：** Worker coordinates event publishing.
        - **函数签名与契约：** publish_event(order_id) returns a publish result.
        - **算法流程：** Load pending event, publish it, then mark it complete.
        - **状态转换：** Pending moves to Published after successful delivery.
        - **详细数据结构：** Outbox record contains id, payload, status, and retry count.
        """

    return f"""
    # 技术设计规范

    > **设计粒度：** {level}

    ## 设计起点与约束

    Existing order creation must keep its interface stable.

    ## 目标系统边界

    The changed 组件 are the order service and outbox worker.

    ## 方案设计

    The API writes an outbox row and the worker publishes it through the message bus.

    ```mermaid
    flowchart TD
        API --> Store
        Store --> Worker
        Worker --> Broker
    ```

    ## 备选方案与取舍

    Alternative direct publish was rejected because transaction consistency is weaker.

    ## 风险与验证策略

    Risk is duplicate delivery; Validation covers retry and idempotency behavior.

    {lld}
    """


def valid_design_tasks() -> str:
    return """
    # Design-First Tasks

    ## 执行规则

    1. Inline examples like `- [ ]`, `- [x]`, and `- [~]` are not tasks.

    ## 阶段 1

    - [ ] **T-001:** Implement the design.md persistence boundary
      - 状态: pending
      - 涉及文件: `src/outbox.py`
      - 验证命令: pytest tests/test_outbox.py
      - 验证证据: pending
      - 依赖: 无
      - 风险: low
      - 覆盖: REQ-001
      - 可并行: 否
      - 验证标准: Design constraints are covered by tests
    """


def valid_feature_tasks() -> str:
    return """
    # Tasks

    > **状态：** Draft
    > **当前任务：** T-001
    > **进度：** 2 / 3 已完成
    > **最后更新：** 2026-01-01

    ## 执行规则

    1. Inline examples like `- [ ]`, `- [x]`, and `- [~]` are not tasks.

    ## 阶段 1

    - [ ] **T-001:** Implement comment storage
      - 状态: pending
      - 涉及文件: `src/comments.py`
      - 验证命令: pytest tests/test_comments.py
      - 验证证据: pending
      - 依赖: 无
      - 风险: low
      - 覆盖: US-001, AC-001.1
      - 可并行: 否
      - 验证标准: Unit tests pass

    - [x] **T-002:** Record completed setup
      - 状态: done
      - 涉及文件: `docs/specs/tasks.md`
      - 验证命令: python scripts/check.py
      - 验证证据: pytest passed
      - 依赖: T-001
      - 风险: low
      - 覆盖: NFR-001
      - 可并行: 是
      - 验证标准: Completion evidence is recorded

    - [~] **T-003:** Human-approved skip for optional export
      - 状态: skipped
      - 涉及文件: `src/export.py`
      - 验证命令: n/a
      - 验证证据: user approved skip
      - 依赖: T-002
      - 风险: low
      - 覆盖: n/a
      - 可并行: 否
      - 验证标准: Skip approval is recorded
    """


def valid_bugfix() -> str:
    return """
    # Bugfix Spec

    ## 证据与复现

    Evidence shows duplicate processing.

    ## 当前错误行为

    ### BUG-001: Duplicate deduction

    - **WHEN** the same order message is processed twice
    - **THEN** current behavior deducts inventory twice

    ## 修复后的期望行为

    ### FIX-001: Idempotent deduction

    - **WHEN** the same order message is processed twice
    - **THEN** inventory is deducted once

    ## 必须保持不变的行为

    ### SAFE-001: Normal order behavior

    - **WHEN** one valid order is submitted
    - **THEN** the original response contract remains unchanged

    ## 范围与约束

    The fix is limited to the inventory deduction path.
    """


def valid_bugfix_design() -> str:
    return """
    # Bugfix Design

    ## 根因分析 / Root Cause

    The retry consumer lacks an idempotency check.

    ## 代码路径与影响面

    The affected Surface is the retry consumer and inventory repository.

    ## 修复策略

    The Fix Strategy is to guard deduction by order id.

    ## 测试与验证策略

    Regression tests cover duplicate and normal single-order behavior.

    ## 风险与发布计划

    Rollout risk is low and rollback removes the guard.

    ```mermaid
    flowchart TD
        Retry --> Guard
        Guard --> Inventory
    ```
    """


def valid_bugfix_tasks(prefix: str = "B") -> str:
    return f"""
    # Bugfix Tasks

    ## 阶段 1

    - [ ] **{prefix}-001:** 建立复现失败证明
      - 状态: pending
      - 涉及文件: `tests/test_inventory.py`
      - 验证命令: pytest tests/test_inventory.py
      - 验证证据: pending
      - 依赖: 无
      - 风险: high
      - 覆盖: BUG-001
      - 可并行: 否
      - 验证标准: 复现测试稳定失败

    - [ ] **{prefix}-002:** 实现最小修复
      - 状态: pending
      - 涉及文件: `src/inventory.py`
      - 验证命令: pytest tests/test_inventory.py
      - 验证证据: pending
      - 依赖: {prefix}-001
      - 风险: high
      - 覆盖: FIX-001
      - 可并行: 否
      - 验证标准: 复现测试转为通过

    - [ ] **{prefix}-003:** 补充回归防护
      - 状态: pending
      - 涉及文件: `tests/test_inventory.py`
      - 验证命令: pytest tests/test_inventory.py
      - 验证证据: pending
      - 依赖: {prefix}-002
      - 风险: medium
      - 覆盖: SAFE-001
      - 可并行: 否
      - 验证标准: 回归测试证明不变行为未破坏
    """


def make_requirements_first(specs_dir: Path, product: str | None = None, tasks: str | None = None) -> None:
    write(specs_dir / "product.md", product or valid_product())
    write(specs_dir / "architecture.md", valid_architecture())
    write(specs_dir / "tasks.md", tasks or valid_feature_tasks())


def init_progress(specs_dir: Path) -> None:
    result = run_progress("init", str(specs_dir))
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)


def make_design_first(specs_dir: Path, design: str | None = None) -> None:
    write(specs_dir / "design.md", design or valid_design())
    write(specs_dir / "requirements.md", valid_requirements())
    write(specs_dir / "tasks.md", valid_design_tasks())


def make_bugfix(specs_dir: Path, tasks: str | None = None) -> None:
    write(specs_dir / "bugfix.md", valid_bugfix())
    write(specs_dir / "design.md", valid_bugfix_design())
    write(specs_dir / "tasks.md", tasks or valid_bugfix_tasks())


class ValidatorRegressionTests(unittest.TestCase):
    def test_raw_templates_fail_for_all_workflows(self) -> None:
        cases = [
            (
                "requirements-first",
                {
                    "product_template.md": "product.md",
                    "architecture_template.md": "architecture.md",
                    "tasks_template.md": "tasks.md",
                },
            ),
            (
                "design-first",
                {
                    "design_first_design_template.md": "design.md",
                    "requirements_template.md": "requirements.md",
                    "design_first_tasks_template.md": "tasks.md",
                },
            ),
            (
                "bugfix",
                {
                    "bugfix_template.md": "bugfix.md",
                    "bugfix_design_template.md": "design.md",
                    "bugfix_tasks_template.md": "tasks.md",
                },
            ),
        ]

        for workflow, mapping in cases:
            with self.subTest(workflow=workflow), tempfile.TemporaryDirectory() as tmp:
                specs_dir = Path(tmp)
                for source, target in mapping.items():
                    shutil.copyfile(TEMPLATES / source, specs_dir / target)

                result = run_validator(specs_dir, workflow)

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("占位符", result.stdout)
                self.assertRegex(result.stdout, r"\.md:\d+")

    def test_prose_gwt_words_do_not_count_as_acceptance_criteria(self) -> None:
        prose_product = """
        # Product

        ## 用户故事

        ### US-001: Prose only

        This prose says given enough time users decide when to act and then expect output.

        ## 非功能性需求

        NFR-001: Fast enough.
        """
        with tempfile.TemporaryDirectory() as tmp:
            specs_dir = Path(tmp)
            make_requirements_first(specs_dir, product=prose_product)

            result = run_validator(specs_dir, "requirements-first")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("缺少正式 GWT 行", result.stdout)

    def test_task_count_ignores_inline_checkbox_examples(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            specs_dir = Path(tmp)
            make_requirements_first(specs_dir)

            result = run_validator(specs_dir, "requirements-first")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("tasks.md 包含 3 个任务 (待完成: 1, 已完成: 1, 已跳过: 1)", result.stdout)

    def test_bugfix_rejects_t_prefixed_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            specs_dir = Path(tmp)
            make_bugfix(specs_dir, tasks=valid_bugfix_tasks(prefix="T"))

            result = run_validator(specs_dir, "bugfix")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("B-xxx", result.stdout)

    def test_lld_markers_trigger_lld_depth_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            specs_dir = Path(tmp)
            make_design_first(specs_dir, design=valid_design(level="详细设计", include_lld=False))

            result = run_validator(specs_dir, "design-first")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Low Level Design 模块", result.stdout)

        with tempfile.TemporaryDirectory() as tmp:
            specs_dir = Path(tmp)
            make_design_first(specs_dir, design=valid_design(level="High Level Design", include_lld=False))

            result = run_validator(specs_dir, "design-first")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_valid_minimal_workflows_pass(self) -> None:
        makers = [
            ("requirements-first", make_requirements_first),
            ("design-first", make_design_first),
            ("bugfix", make_bugfix),
        ]

        for workflow, maker in makers:
            with self.subTest(workflow=workflow), tempfile.TemporaryDirectory() as tmp:
                specs_dir = Path(tmp)
                maker(specs_dir)

                result = run_validator(specs_dir, workflow)

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_invalid_utf8_fails_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            specs_dir = Path(tmp)
            make_requirements_first(specs_dir)
            (specs_dir / "product.md").write_bytes(b"\xff\xfe\x00\x00")

            result = run_validator(specs_dir, "requirements-first")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("UTF-8", result.stdout)
            self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_no_color_environment_suppresses_ansi(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            specs_dir = Path(tmp)
            make_requirements_first(specs_dir)

            result = run_validator(specs_dir, "requirements-first", env={"NO_COLOR": "1"})

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("\x1b[", result.stdout)

    def test_new_progress_files_enable_resume_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            specs_dir = Path(tmp)
            make_requirements_first(specs_dir)
            init_progress(specs_dir)

            result = run_validator(specs_dir, "requirements-first")
            resume = subprocess.run(
                [sys.executable, str(VALIDATOR), str(specs_dir), "--resume"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(resume.returncode, 0, resume.stdout + resume.stderr)
            self.assertIn("spec.yml", (specs_dir / "spec.yml").read_text(encoding="utf-8"))

    def test_complete_requires_evidence_and_updates_all_state_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            specs_dir = Path(tmp)
            make_requirements_first(specs_dir)
            init_progress(specs_dir)

            no_evidence = run_progress("complete", str(specs_dir), "T-001", "--evidence", "")
            self.assertNotEqual(no_evidence.returncode, 0)
            self.assertIn("evidence", no_evidence.stderr)

            started = run_progress("start", str(specs_dir), "T-001")
            completed = run_progress(
                "complete",
                str(specs_dir),
                "T-001",
                "--evidence",
                "pytest tests/test_comments.py passed",
            )

            self.assertEqual(started.returncode, 0, started.stdout + started.stderr)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertIn("- [x] **T-001:**", (specs_dir / "tasks.md").read_text(encoding="utf-8"))
            self.assertIn("pytest tests/test_comments.py passed", (specs_dir / "progress.md").read_text(encoding="utf-8"))
            self.assertIn("current_task:", (specs_dir / "spec.yml").read_text(encoding="utf-8"))
            self.assertIn("> **进度：** 3 / 3 已完成", (specs_dir / "tasks.md").read_text(encoding="utf-8"))
            self.assertIn("| T-001 |", (specs_dir / "tasks.md").read_text(encoding="utf-8"))

    def test_validator_flags_stale_tasks_progress_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            specs_dir = Path(tmp)
            tasks = valid_feature_tasks().replace("> **进度：** 2 / 3 已完成", "> **进度：** 0 / 3 已完成")
            make_requirements_first(specs_dir, tasks=tasks)

            result = run_validator(specs_dir, "requirements-first")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("顶部进度与复选框状态不一致", result.stdout)

    def test_acceptance_state_recovers_pending_agents_after_partial_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            specs_dir = Path(tmp)
            tasks = valid_feature_tasks().replace("- [ ] **T-001:**", "- [x] **T-001:**")
            tasks = tasks.replace("- 状态: pending", "- 状态: done", 1)
            tasks = tasks.replace("- 验证证据: pending", "- 验证证据: pytest passed", 1)
            make_requirements_first(specs_dir, tasks=tasks)
            init_progress(specs_dir)

            init = run_progress("acceptance-init", str(specs_dir))
            self.assertEqual(init.returncode, 0, init.stdout + init.stderr)
            state = json.loads((specs_dir / "acceptance_state.json").read_text(encoding="utf-8"))
            first_agent = state["agents"][0]["agent_id"]
            self.assertEqual(run_progress("acceptance-start-agent", str(specs_dir), first_agent).returncode, 0)
            completed = run_progress(
                "acceptance-complete-agent",
                str(specs_dir),
                first_agent,
                "--result",
                "PASS",
                "--report",
                "unit passed",
            )
            status = run_progress("acceptance-status", str(specs_dir))

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
            summary = json.loads(status.stdout)
            self.assertNotIn(first_agent, summary["agents"]["pending_or_running"])
            self.assertGreater(len(summary["agents"]["pending_or_running"]), 0)

    def test_acceptance_fixes_do_not_append_original_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            specs_dir = Path(tmp)
            tasks = valid_feature_tasks().replace("- [ ] **T-001:**", "- [x] **T-001:**")
            tasks = tasks.replace("- 状态: pending", "- 状态: done", 1)
            tasks = tasks.replace("- 验证证据: pending", "- 验证证据: pytest passed", 1)
            make_requirements_first(specs_dir, tasks=tasks)
            init_progress(specs_dir)
            self.assertEqual(run_progress("acceptance-init", str(specs_dir)).returncode, 0)
            before = (specs_dir / "tasks.md").read_text(encoding="utf-8")
            issue = run_progress(
                "acceptance-record-issue",
                str(specs_dir),
                "--unit",
                "U-001",
                "--severity",
                "P2",
                "--title",
                "Missing regression proof",
                "--evidence",
                "review report showed missing regression proof",
            )
            planned = run_progress("acceptance-plan-fixes", str(specs_dir))
            after = (specs_dir / "tasks.md").read_text(encoding="utf-8")

            self.assertEqual(issue.returncode, 0, issue.stdout + issue.stderr)
            self.assertEqual(planned.returncode, 0, planned.stdout + planned.stderr)
            self.assertEqual(before, after)
            self.assertTrue((specs_dir / "acceptance-fixes.md").is_file())
            self.assertIn("F-001", (specs_dir / "acceptance-fixes.md").read_text(encoding="utf-8"))

    def test_acceptance_round_four_defers_p3_and_fixes_p2_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            specs_dir = Path(tmp)
            tasks = valid_feature_tasks().replace("- [ ] **T-001:**", "- [x] **T-001:**")
            tasks = tasks.replace("- 状态: pending", "- 状态: done", 1)
            tasks = tasks.replace("- 验证证据: pending", "- 验证证据: pytest passed", 1)
            make_requirements_first(specs_dir, tasks=tasks)
            init_progress(specs_dir)
            self.assertEqual(run_progress("acceptance-init", str(specs_dir)).returncode, 0)
            state = json.loads((specs_dir / "acceptance_state.json").read_text(encoding="utf-8"))
            state["round"] = 4
            (specs_dir / "acceptance_state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(run_progress(
                "acceptance-record-issue",
                str(specs_dir),
                "--unit",
                "U-001",
                "--severity",
                "P2",
                "--title",
                "Blocking issue",
                "--evidence",
                "evidence for p2",
            ).returncode, 0)
            self.assertEqual(run_progress(
                "acceptance-record-issue",
                str(specs_dir),
                "--unit",
                "U-001",
                "--severity",
                "P3",
                "--title",
                "Non-blocking polish",
                "--evidence",
                "evidence for p3",
            ).returncode, 0)
            planned = run_progress("acceptance-plan-fixes", str(specs_dir))

            self.assertEqual(planned.returncode, 0, planned.stdout + planned.stderr)
            state = json.loads((specs_dir / "acceptance_state.json").read_text(encoding="utf-8"))
            self.assertEqual([fix["severity"] for fix in state["fixes"]], ["P2"])
            self.assertEqual([issue["severity"] for issue in state["deferred_issues"]], ["P3"])

    def test_task_graph_blocks_unmet_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            specs_dir = Path(tmp)
            tasks = valid_feature_tasks().replace("- [x] **T-002:**", "- [ ] **T-002:**")
            tasks = tasks.replace("- 状态: done", "- 状态: pending", 1)
            make_requirements_first(specs_dir, tasks=tasks)
            init_progress(specs_dir)

            result = run_progress("start", str(specs_dir), "T-002")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unmet dependencies", result.stderr)

    def test_resume_marks_active_dirty_work_as_interrupted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            specs_dir = repo / "docs" / "specs"
            specs_dir.mkdir(parents=True)
            make_requirements_first(specs_dir)
            init_progress(specs_dir)
            subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "init"],
                cwd=repo,
                check=True,
                capture_output=True,
            )

            self.assertEqual(run_progress("start", str(specs_dir), "T-001", cwd=repo).returncode, 0)
            (repo / "src.py").write_text("print('changed')\n", encoding="utf-8")
            result = run_progress("resume", str(specs_dir), cwd=repo)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("interrupted", result.stdout)

    def test_guard_commit_blocks_business_code_without_progress_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            specs_dir = repo / "docs" / "specs"
            specs_dir.mkdir(parents=True)
            make_requirements_first(specs_dir)
            init_progress(specs_dir)
            (repo / "src.py").write_text("print('changed')\n", encoding="utf-8")
            subprocess.run(["git", "add", "src.py"], cwd=repo, check=True, capture_output=True)

            blocked = run_progress("guard-commit", str(specs_dir), cwd=repo)
            subprocess.run(["git", "add", "docs/specs/tasks.md"], cwd=repo, check=True, capture_output=True)
            allowed = run_progress("guard-commit", str(specs_dir), cwd=repo)

            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn("Business-code changes", blocked.stdout)
            self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)

    def test_pre_acceptance_is_not_final_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            specs_dir = Path(tmp)
            tasks = valid_feature_tasks().replace("- [ ] **T-001:**", "- [x] **T-001:**")
            tasks = tasks.replace("- 状态: pending", "- 状态: done", 1)
            tasks = tasks.replace("- 验证证据: pending", "- 验证证据: pytest passed", 1)
            make_requirements_first(specs_dir, tasks=tasks)
            init_progress(specs_dir)
            result = run_progress("pre-acceptance", str(specs_dir))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("strict multi-agent final acceptance is still required", result.stdout)

    def test_guard_commit_honors_non_default_specs_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            # Specs live outside docs/specs/ — guard must still detect them.
            specs_dir = repo / "spec"
            specs_dir.mkdir(parents=True)
            make_requirements_first(specs_dir)
            init_progress(specs_dir)
            (repo / "src.py").write_text("print('changed')\n", encoding="utf-8")
            subprocess.run(["git", "add", "src.py"], cwd=repo, check=True, capture_output=True)

            blocked = run_progress("guard-commit", str(specs_dir), cwd=repo)
            subprocess.run(["git", "add", "spec/tasks.md"], cwd=repo, check=True, capture_output=True)
            allowed = run_progress("guard-commit", str(specs_dir), cwd=repo)

            self.assertNotEqual(blocked.returncode, 0, blocked.stdout)
            self.assertIn("spec/tasks.md", blocked.stdout)
            self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)

    def test_block_records_blocker_without_completing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            specs_dir = Path(tmp)
            make_requirements_first(specs_dir)
            init_progress(specs_dir)

            no_reason = run_progress("block", str(specs_dir), "T-001", "--reason", "")
            blocked = run_progress("block", str(specs_dir), "T-001", "--reason", "waiting on upstream API")

            self.assertNotEqual(no_reason.returncode, 0)
            self.assertEqual(blocked.returncode, 0, blocked.stdout + blocked.stderr)
            tasks_text = (specs_dir / "tasks.md").read_text(encoding="utf-8")
            self.assertIn("- [ ] **T-001:**", tasks_text)
            self.assertIn("waiting on upstream API", tasks_text)
            self.assertIn("Blocked", (specs_dir / "progress.md").read_text(encoding="utf-8"))

    def test_waves_detects_circular_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            specs_dir = Path(tmp)
            tasks = valid_feature_tasks()
            tasks = tasks.replace("- [x] **T-002:**", "- [ ] **T-002:**")
            tasks = tasks.replace("- [~] **T-003:**", "- [ ] **T-003:**")
            tasks = tasks.replace("- 状态: done", "- 状态: pending")
            tasks = tasks.replace("- 状态: skipped", "- 状态: pending")
            # Introduce a cycle: T-001 depends on T-003, T-003 depends on T-002, T-002 on T-001.
            tasks = tasks.replace("- 依赖: 无", "- 依赖: T-003", 1)
            make_requirements_first(specs_dir, tasks=tasks)

            result = run_progress("waves", str(specs_dir))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Circular", result.stderr)

    def test_sync_check_flags_changed_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            specs_dir = Path(tmp)
            make_requirements_first(specs_dir)
            init_progress(specs_dir)
            # init writes spec.yml with current artifact hashes; mutate product.md.
            run_progress("sync-check", str(specs_dir), "--write")
            (specs_dir / "product.md").write_text(
                valid_product() + "\n## Extra section\nNew content.\n", encoding="utf-8"
            )

            result = run_progress("sync-check", str(specs_dir))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("product.md changed", result.stdout)

    def test_specs_path_rejects_traversal_outside_base(self) -> None:
        if str(SCRIPT_DIR) not in sys.path:
            sys.path.insert(0, str(SCRIPT_DIR))
        import spec_progress

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "repo"
            (base / "docs" / "specs").mkdir(parents=True)
            # Inside the base is allowed.
            self.assertTrue(
                spec_progress.specs_path(base / "docs" / "specs", base_dir=base)
            )
            # ../ traversal outside the base is rejected.
            with self.assertRaises(spec_progress.SpecProgressError):
                spec_progress.specs_path(base / ".." / "outside", base_dir=base)


if __name__ == "__main__":
    unittest.main()
