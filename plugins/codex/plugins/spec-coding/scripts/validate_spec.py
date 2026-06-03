#!/usr/bin/env python3
"""
Spec Coding 规范完整性验证脚本

支持三类工作流：
1. Feature / Requirements-First: product.md + architecture.md + tasks.md
2. Feature / Design-First: design.md + requirements.md + tasks.md
3. Bugfix: bugfix.md + design.md + tasks.md

用法:
    python validate_spec.py docs/specs/
    python validate_spec.py docs/specs/ --workflow feature
    python validate_spec.py docs/specs/ --workflow requirements-first
    python validate_spec.py docs/specs/ --workflow design-first
    python validate_spec.py docs/specs/ --workflow bugfix
"""

from __future__ import annotations

import argparse
import os
import re
import sys


Result = tuple[bool, str]


class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def colorize(text: str, color: str) -> str:
    return f"{color}{text}{Colors.RESET}"


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def check_file_exists(specs_dir: str, filename: str) -> Result:
    filepath = os.path.join(specs_dir, filename)
    if os.path.isfile(filepath):
        return True, f"文件存在: {filename}"
    return False, f"缺失文件: {filename}"


def has_pattern(content: str, pattern: str) -> bool:
    return bool(re.search(pattern, content, re.IGNORECASE))


def normalize_workflow(workflow: str | None) -> str | None:
    aliases = {
        "feature": "feature",
        "requirements-first": "feature",
        "design-first": "design-first",
        "bugfix": "bugfix",
        "auto": "auto",
    }
    if workflow is None:
        return None
    return aliases.get(workflow)


def detect_workflow(specs_dir: str) -> str | None:
    has_requirements_first = all(
        os.path.isfile(os.path.join(specs_dir, filename))
        for filename in ("product.md", "architecture.md")
    )
    has_design_first = all(
        os.path.isfile(os.path.join(specs_dir, filename))
        for filename in ("design.md", "requirements.md")
    )
    has_bugfix = all(
        os.path.isfile(os.path.join(specs_dir, filename))
        for filename in ("bugfix.md", "design.md")
    )

    matches = [
        workflow
        for workflow, present in (
            ("feature", has_requirements_first),
            ("design-first", has_design_first),
            ("bugfix", has_bugfix),
        )
        if present
    ]

    if len(matches) == 1:
        return matches[0]
    return None


def check_product_spec(specs_dir: str) -> list[Result]:
    results: list[Result] = []
    filepath = os.path.join(specs_dir, "product.md")

    if not os.path.isfile(filepath):
        return [(False, "product.md 不存在，跳过内容检查")]

    content = read_text(filepath)
    has_given = has_pattern(content, r"\*\*GIVEN\*\*|GIVEN\s")
    has_when = has_pattern(content, r"\*\*WHEN\*\*|WHEN\s")
    has_then = has_pattern(content, r"\*\*THEN\*\*|THEN\s")

    if has_given and has_when and has_then:
        results.append((True, "product.md 包含 GIVEN / WHEN / THEN 验收标准"))
    else:
        missing = []
        if not has_given:
            missing.append("GIVEN")
        if not has_when:
            missing.append("WHEN")
        if not has_then:
            missing.append("THEN")
        results.append((False, f"product.md 缺少验收标准关键词: {', '.join(missing)}"))

    if has_pattern(content, r"US-\d+|用户故事|User Story"):
        results.append((True, "product.md 包含用户故事标识"))
    else:
        results.append((False, "product.md 缺少用户故事标识 (如 US-001)"))

    if has_pattern(content, r"非功能|NFR|Non-Functional"):
        results.append((True, "product.md 包含非功能性需求章节"))
    else:
        results.append((False, "product.md 缺少非功能性需求章节"))

    return results


def check_architecture_spec(specs_dir: str) -> list[Result]:
    results: list[Result] = []
    filepath = os.path.join(specs_dir, "architecture.md")

    if not os.path.isfile(filepath):
        return [(False, "architecture.md 不存在，跳过内容检查")]

    content = read_text(filepath)
    required_sections = [
        (r"数据模型|Data Model|实体", "数据模型定义"),
        (r"API|接口|Interface|端点|Endpoint", "API / 接口签名"),
        (r"依赖|Dependency|Dependencies", "依赖清单"),
        (r"错误处理|Error Handling|异常", "错误处理策略"),
        (r"安全|Security|认证|Authorization", "安全策略"),
    ]

    for pattern, desc in required_sections:
        if has_pattern(content, pattern):
            results.append((True, f"architecture.md 包含: {desc}"))
        else:
            results.append((False, f"architecture.md 缺少: {desc}"))

    if "```mermaid" in content:
        results.append((True, "architecture.md 包含 Mermaid 图"))
    else:
        results.append((False, "architecture.md 缺少 Mermaid 图"))

    return results


def check_requirements_spec(specs_dir: str) -> list[Result]:
    results: list[Result] = []
    filepath = os.path.join(specs_dir, "requirements.md")

    if not os.path.isfile(filepath):
        return [(False, "requirements.md 不存在，跳过内容检查")]

    content = read_text(filepath)
    has_given = has_pattern(content, r"\*\*GIVEN\*\*|GIVEN\s")
    has_when = has_pattern(content, r"\*\*WHEN\*\*|WHEN\s")
    has_then = has_pattern(content, r"\*\*THEN\*\*|THEN\s")

    if has_given and has_when and has_then:
        results.append((True, "requirements.md 包含 GIVEN / WHEN / THEN 验收标准"))
    else:
        results.append((False, "requirements.md 缺少 GIVEN / WHEN / THEN 验收标准"))

    if has_pattern(content, r"REQ-\d+|需求|Requirement"):
        results.append((True, "requirements.md 包含需求标识"))
    else:
        results.append((False, "requirements.md 缺少需求标识 (如 REQ-001)"))

    if has_pattern(content, r"设计映射|来源设计|Derived from Design|design\.md"):
        results.append((True, "requirements.md 明确标注了设计来源"))
    else:
        results.append((False, "requirements.md 缺少设计来源或映射说明"))

    if has_pattern(content, r"非功能|NFR|Non-Functional"):
        results.append((True, "requirements.md 包含非功能性需求章节"))
    else:
        results.append((False, "requirements.md 缺少非功能性需求章节"))

    return results


def check_design_first_spec(specs_dir: str) -> list[Result]:
    results: list[Result] = []
    filepath = os.path.join(specs_dir, "design.md")

    if not os.path.isfile(filepath):
        return [(False, "design.md 不存在，跳过内容检查")]

    content = read_text(filepath)
    required_sections = [
        (r"设计粒度|Design Level|High Level Design|Low Level Design", "设计粒度"),
        (r"设计起点|设计输入|约束|Constraint", "设计起点与约束"),
        (r"组件|边界|系统边界|Scope", "目标系统边界"),
        (r"方案设计|接口|数据流|Topology|调用链", "方案设计"),
        (r"备选方案|取舍|Alternative", "备选方案与取舍"),
        (r"风险|验证策略|Risk|Validation", "风险与验证策略"),
    ]

    for pattern, desc in required_sections:
        if has_pattern(content, pattern):
            results.append((True, f"design.md 包含: {desc}"))
        else:
            results.append((False, f"design.md 缺少: {desc}"))

    if "```mermaid" in content:
        results.append((True, "design.md 包含 Mermaid 设计图"))
    else:
        results.append((False, "design.md 缺少 Mermaid 设计图"))

    return results


def check_bugfix_spec(specs_dir: str) -> list[Result]:
    results: list[Result] = []
    filepath = os.path.join(specs_dir, "bugfix.md")

    if not os.path.isfile(filepath):
        return [(False, "bugfix.md 不存在，跳过内容检查")]

    content = read_text(filepath)
    required_sections = [
        (r"证据|Evidence|复现|Reproduction", "证据与复现"),
        (r"当前错误行为|Current Behavior|BUG-\d+", "当前错误行为"),
        (r"期望行为|Expected Behavior|FIX-\d+", "修复后的期望行为"),
        (r"保持不变|Unchanged Behavior|SAFE-\d+|Regression", "必须保持不变的行为"),
        (r"范围|Scope|约束|Guardrails", "范围与约束"),
    ]

    for pattern, desc in required_sections:
        if has_pattern(content, pattern):
            results.append((True, f"bugfix.md 包含: {desc}"))
        else:
            results.append((False, f"bugfix.md 缺少: {desc}"))

    has_when = has_pattern(content, r"\*\*WHEN\*\*|WHEN\s")
    has_then = has_pattern(content, r"\*\*THEN\*\*|THEN\s")
    if has_when and has_then:
        results.append((True, "bugfix.md 使用 WHEN / THEN 描述行为"))
    else:
        results.append((False, "bugfix.md 缺少 WHEN / THEN 行为描述"))

    return results


def check_bugfix_design_spec(specs_dir: str) -> list[Result]:
    results: list[Result] = []
    filepath = os.path.join(specs_dir, "design.md")

    if not os.path.isfile(filepath):
        return [(False, "design.md 不存在，跳过内容检查")]

    content = read_text(filepath)
    required_sections = [
        (r"根因|Root Cause|初始假设", "根因分析"),
        (r"路径|影响面|组件|Surface", "代码路径与影响面"),
        (r"修复策略|Fix Strategy|最小安全修复", "修复策略"),
        (r"测试|验证|Regression|复现证明|修复证明", "测试与验证策略"),
        (r"风险|回滚|发布|Rollout", "风险与发布计划"),
    ]

    for pattern, desc in required_sections:
        if has_pattern(content, pattern):
            results.append((True, f"design.md 包含: {desc}"))
        else:
            results.append((False, f"design.md 缺少: {desc}"))

    if "```mermaid" in content:
        results.append((True, "design.md 包含 Mermaid 路径图"))
    else:
        results.append((False, "design.md 缺少 Mermaid 路径图"))

    return results


def check_tasks_spec(specs_dir: str, workflow: str) -> list[Result]:
    results: list[Result] = []
    filepath = os.path.join(specs_dir, "tasks.md")

    if not os.path.isfile(filepath):
        return [(False, "tasks.md 不存在，跳过内容检查")]

    content = read_text(filepath)
    unchecked = re.findall(r"- \[ \]", content)
    checked = re.findall(r"- \[x\]", content, re.IGNORECASE)
    skipped = re.findall(r"- \[~\]", content)
    total_tasks = len(unchecked) + len(checked) + len(skipped)

    if total_tasks > 0:
        results.append((
            True,
            f"tasks.md 包含 {total_tasks} 个任务 "
            f"(待完成: {len(unchecked)}, 已完成: {len(checked)}, 已跳过: {len(skipped)})",
        ))
    else:
        results.append((False, "tasks.md 缺少复选框格式任务 (应使用 - [ ] 格式)"))

    task_id_pattern = r"(B|T)-\d+" if workflow == "bugfix" else r"T-\d+"
    task_label = "B-xxx / T-xxx" if workflow == "bugfix" else "T-xxx"
    if has_pattern(content, task_id_pattern):
        results.append((True, f"tasks.md 包含任务编号标识 ({task_label})"))
    else:
        results.append((False, f"tasks.md 缺少任务编号标识 (建议使用 {task_label} 格式)"))

    if has_pattern(content, r"验证标准|Validation|Test|测试|✅"):
        results.append((True, "tasks.md 包含验证标准"))
    else:
        results.append((False, "tasks.md 缺少验证标准"))

    if workflow == "design-first":
        if has_pattern(content, r"设计|Design|design\.md"):
            results.append((True, "tasks.md 体现了设计约束或设计来源"))
        else:
            results.append((False, "tasks.md 缺少设计约束或设计来源说明"))

    if workflow == "bugfix":
        if has_pattern(content, r"复现|Reproduction|失败证明"):
            results.append((True, "tasks.md 包含复现或失败证明任务"))
        else:
            results.append((False, "tasks.md 缺少复现或失败证明任务"))

        if has_pattern(content, r"回归|Regression|不变行为"):
            results.append((True, "tasks.md 包含回归防护任务"))
        else:
            results.append((False, "tasks.md 缺少回归防护任务"))

    return results


def print_section(title: str) -> None:
    print(colorize(f"\n── {title} ──", Colors.BOLD))


def print_result(result: Result) -> None:
    icon = colorize("✔", Colors.GREEN) if result[0] else colorize("✖", Colors.RED)
    print(f"  {icon} {result[1]}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Spec Coding 规范完整性验证工具",
        epilog="用于验证 docs/specs/ 目录下的 Requirements-First、Design-First 或 Bugfix 工件。",
    )
    parser.add_argument("specs_dir", help="规范文件所在目录路径 (如 docs/specs/)")
    parser.add_argument(
        "--workflow",
        choices=["auto", "feature", "requirements-first", "design-first", "bugfix"],
        default="auto",
        help="指定要验证的规范分支，默认自动检测",
    )
    args = parser.parse_args()

    print(colorize("\n╔══════════════════════════════════════════════╗", Colors.CYAN))
    print(colorize("║   Spec Coding 规范完整性验证                ║", Colors.CYAN))
    print(colorize("╚══════════════════════════════════════════════╝\n", Colors.CYAN))

    specs_dir = args.specs_dir
    if not os.path.isdir(specs_dir):
        print(colorize(f"✖ 目录不存在: {specs_dir}", Colors.RED))
        print("\n请先运行 Spec Coding 工作流生成规范文件。")
        sys.exit(1)

    workflow = normalize_workflow(args.workflow)
    if workflow == "auto":
        workflow = detect_workflow(specs_dir)
        if workflow is None:
            print(colorize("✖ 无法自动确定工作流。", Colors.RED))
            print("请确认规范目录只包含一套工件，或使用 --workflow feature / design-first / bugfix 显式指定。")
            sys.exit(1)

    required_files = {
        "feature": ["product.md", "architecture.md", "tasks.md"],
        "design-first": ["design.md", "requirements.md", "tasks.md"],
        "bugfix": ["bugfix.md", "design.md", "tasks.md"],
    }[workflow]

    print(f"📂 检查目录: {os.path.abspath(specs_dir)}")
    print(f"🧭 规范分支: {workflow}\n")

    all_results: list[Result] = []

    print_section("文件存在性检查")
    for filename in required_files:
        result = check_file_exists(specs_dir, filename)
        all_results.append(result)
        print_result(result)

    if workflow == "feature":
        print_section("product.md 内容检查")
        for result in check_product_spec(specs_dir):
            all_results.append(result)
            print_result(result)

        print_section("architecture.md 内容检查")
        for result in check_architecture_spec(specs_dir):
            all_results.append(result)
            print_result(result)
    elif workflow == "design-first":
        print_section("design.md 内容检查")
        for result in check_design_first_spec(specs_dir):
            all_results.append(result)
            print_result(result)

        print_section("requirements.md 内容检查")
        for result in check_requirements_spec(specs_dir):
            all_results.append(result)
            print_result(result)
    else:
        print_section("bugfix.md 内容检查")
        for result in check_bugfix_spec(specs_dir):
            all_results.append(result)
            print_result(result)

        print_section("design.md 内容检查")
        for result in check_bugfix_design_spec(specs_dir):
            all_results.append(result)
            print_result(result)

    print_section("tasks.md 内容检查")
    for result in check_tasks_spec(specs_dir, workflow):
        all_results.append(result)
        print_result(result)

    passed = sum(1 for ok, _ in all_results if ok)
    failed = len(all_results) - passed

    print(colorize("\n══════════════════════════════════════════════", Colors.CYAN))
    print(
        f"  总计: {len(all_results)} 项检查 | "
        f"{colorize(f'{passed} 通过', Colors.GREEN)} | "
        f"{colorize(f'{failed} 失败', Colors.RED)}"
    )

    if failed == 0:
        print(colorize("\n  ✅ 所有规范检查通过！可以进入代码实施阶段。\n", Colors.GREEN))
        sys.exit(0)

    print(colorize(f"\n  ⚠️  存在 {failed} 项问题，请检查并修复后重新验证。\n", Colors.YELLOW))
    sys.exit(1)


if __name__ == "__main__":
    main()
