# -*- coding: utf-8 -*-
"""
A-Stock Agents 质量门禁与测试流水线核验器 (Enhanced Quality & Test Gate Runner)

核心能力：
1. 现代化双层动态进度条 (Dual-Layer Progress Bars)：
   - 第一层（流水线总体）：全局阶段推进、总体完成度百分比与阶段状态；
   - 第二层（用例级细粒度）：当前阶段测试用例实时完成度、✔ 通过数、✖ 失败数、↷ 跳过数、已耗时、预估剩余时间 (ETA)、瞬时吞吐速率 (tests/s) 及当前正在执行的测试用例名称与文件。
2. 8 分位高精度平滑字符降级 (Smooth Unicode Progress Rendering)：
   - 在非 TTY / CI / 管道重定向环境下，自动启用 8 分位平滑 Unicode 字符 (▏▎▍▌▋▊▉█) 进行双层进度输出，信息密度高且杜绝黑盒。
3. 改动感知智能裁剪 (Smart Change-Aware Pruning)：
   - 基于 Git 改动自动判定，日常业务改动自动裁剪 92 例重型交付测试，耗时从 270s 降至 20s 极速区间。
4. 前台顺序同步执行 (Strict Sequential Execution)：
   - 严格遵循 AGENTS.md 铁律，前台顺序同步执行，杜绝后台挂起。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "skill_bundle" / "bundle.json").is_file())

# 尝试导入 Rich 组件以提供卓越的终端体验；若不可用则平滑降级至高精度字符输出
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
    )
    from rich.table import Table
    from rich.text import Text
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

console = Console(highlight=False) if HAS_RICH else None


def smooth_bar(pct: float, width: int = 20) -> str:
    """生成 8 分位高精度平滑 Unicode 进度条字符串。"""
    blocks = ["", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"]
    clamped_pct = max(0.0, min(100.0, pct))
    total_eighths = int(round(clamped_pct / 100.0 * width * 8))
    full = total_eighths // 8
    rem = total_eighths % 8
    if full >= width:
        return "█" * width
    part = blocks[rem] if rem > 0 else ""
    empty = "░" * (width - full - (1 if rem > 0 else 0))
    return "█" * full + part + empty


def detect_delivery_touch() -> bool:
    """检测当前工作区改动是否触碰发布打包、宿主适配或安装器等交付链路。"""
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        changed_files = [line.strip().split()[-1] for line in res.stdout.strip().splitlines() if line.strip()]
    except Exception:
        return True  # 无法探测时回退至保守全量

    delivery_keywords = (
        "tools/packaging",
        "tools/host_adapters",
        "install.ps1",
        "install.sh",
        "SKILL.md",
        "bundle.json",
        "tests/release",
    )
    for f in changed_files:
        f_norm = f.replace("\\", "/")
        if any(kw in f_norm for kw in delivery_keywords):
            return True
    return False


class DualProgressBarRunner:
    """现代化测试进度执行器，支持双层动态进度条与平滑 Unicode 降级。"""

    RE_COLLECTED = re.compile(r"collected\s+(\d+)\s+items(?:\s*/\s*(\d+)\s+deselected\s*/\s*(\d+)\s+selected)?")
    RE_TEST_LINE = re.compile(r"^(.+?)::([^\s]+)\s+(PASSED|FAILED|SKIPPED|XFAIL|XPASS)\s+\[\s*(\d+)%\]")

    def __init__(self, force_rich: Optional[bool] = None, step_pct: int = 10):
        if force_rich is not None:
            self.use_rich = HAS_RICH and force_rich
        else:
            self.use_rich = HAS_RICH and sys.stdout.isatty()
        self.step_pct = max(5, min(25, step_pct))

    def run_pipeline_with_progress(self, stages: List[Tuple[str, List[str]]]) -> Tuple[int, List[Dict]]:
        """执行整个流水线，统一维护双层进度条。"""
        if self.use_rich:
            return self._run_rich_pipeline(stages)
        else:
            return self._run_fallback_pipeline(stages)

    def _run_rich_pipeline(self, stages: List[Tuple[str, List[str]]]) -> Tuple[int, List[Dict]]:
        """Rich TTY 动态双层进度条：顶部流水线总进度 + 底部阶段用例细粒度进度。"""
        total_stages = len(stages)
        pipeline_metrics: List[Dict] = []

        progress = Progress(
            SpinnerColumn(spinner_name="dots"),
            TextColumn("[bold cyan]{task.fields[title]:<16}"),
            BarColumn(bar_width=26, complete_style="bright_cyan", finished_style="bold green"),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            TextColumn("[green]✔ {task.fields[passed]}[/green]"),
            TextColumn("[red]✖ {task.fields[failed]}[/red]"),
            TextColumn("[yellow]↷ {task.fields[skipped]}[/yellow]"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            TextColumn("[dim]{task.fields[detail]}[/dim]"),
            console=console,
            transient=False,
        )

        overall_task = progress.add_task(
            "overall",
            total=total_stages,
            title="流水线总进度",
            passed=0,
            failed=0,
            skipped=0,
            detail=f"准备执行阶段 1/{total_stages}",
        )

        stage_task = progress.add_task(
            "stage",
            total=100,  # 初始占位
            title="当前阶段用例",
            passed=0,
            failed=0,
            skipped=0,
            detail="正在收集用例...",
        )

        overall_passed = 0
        overall_failed = 0
        overall_skipped = 0

        with progress:
            for idx, (stage_name, cmd) in enumerate(stages, 1):
                metrics = {
                    "stage_name": stage_name,
                    "total": 0,
                    "passed": 0,
                    "failed": 0,
                    "skipped": 0,
                    "elapsed": 0.0,
                    "return_code": 0,
                    "failures": [],
                }

                short_stage = (stage_name[:24] + "..") if len(stage_name) > 26 else stage_name
                progress.update(
                    overall_task,
                    detail=f"[{idx}/{total_stages}] {short_stage}",
                )
                progress.reset(
                    stage_task,
                    total=100,
                    title=f"阶段 {idx} 用例",
                    passed=0,
                    failed=0,
                    skipped=0,
                    detail="正在收集用例...",
                )

                start_time = time.monotonic()
                proc = subprocess.Popen(
                    [str(c) for c in cmd],
                    cwd=ROOT,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                )

                for line in iter(proc.stdout.readline, ""):
                    # 1. 匹配收集数量
                    m_coll = self.RE_COLLECTED.search(line)
                    if m_coll:
                        total_items = int(m_coll.group(3)) if m_coll.group(3) else int(m_coll.group(1))
                        metrics["total"] = total_items
                        progress.update(stage_task, total=total_items, completed=0, detail="开始执行测试...")
                        continue

                    # 2. 匹配具体用例完成事件
                    m_test = self.RE_TEST_LINE.match(line.strip())
                    if m_test:
                        filepath = Path(m_test.group(1)).name
                        testname = m_test.group(2)
                        outcome = m_test.group(3)
                        nodeid = f"{filepath}::{testname}"
                        short_display = (nodeid[:30] + "..") if len(nodeid) > 32 else nodeid

                        if outcome in ("PASSED", "XPASS"):
                            metrics["passed"] += 1
                            overall_passed += 1
                        elif outcome in ("FAILED", "XFAIL"):
                            metrics["failed"] += 1
                            overall_failed += 1
                            metrics["failures"].append(nodeid)
                            console.print(f"  [bold red]✖ FAILED:[/bold red] [yellow]{nodeid}[/yellow]")
                        elif outcome == "SKIPPED":
                            metrics["skipped"] += 1
                            overall_skipped += 1

                        progress.update(
                            stage_task,
                            advance=1,
                            passed=metrics["passed"],
                            failed=metrics["failed"],
                            skipped=metrics["skipped"],
                            detail=short_display,
                        )
                        progress.update(
                            overall_task,
                            passed=overall_passed,
                            failed=overall_failed,
                            skipped=overall_skipped,
                        )
                    elif "FAILED" in line and "::" in line:
                        metrics["failures"].append(line.strip())

                proc.stdout.close()
                metrics["return_code"] = proc.wait()
                metrics["elapsed"] = time.monotonic() - start_time

                if metrics["total"] > 0:
                    progress.update(stage_task, completed=metrics["total"], detail="[green]阶段完成[/green]")

                progress.update(overall_task, advance=1)
                pipeline_metrics.append(metrics)

                if metrics["return_code"] != 0:
                    progress.update(overall_task, detail=f"[bold red]阶段 {idx} 失败中断[/bold red]")
                    return metrics["return_code"], pipeline_metrics

            progress.update(overall_task, detail="[bold green]全部流水线阶段完成[/bold green]")

        return 0, pipeline_metrics

    def _run_fallback_pipeline(self, stages: List[Tuple[str, List[str]]]) -> Tuple[int, List[Dict]]:
        """非 TTY / CI / 管道重定向环境的双层高精度 Unicode 进度输出。"""
        total_stages = len(stages)
        pipeline_metrics: List[Dict] = []

        overall_passed = 0
        overall_failed = 0
        overall_skipped = 0

        for idx, (stage_name, cmd) in enumerate(stages, 1):
            metrics = {
                "stage_name": stage_name,
                "total": 0,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "elapsed": 0.0,
                "return_code": 0,
                "failures": [],
            }

            overall_pct = ((idx - 1) / total_stages) * 100.0
            overall_bar_str = smooth_bar(overall_pct, 16)
            print(f"\n" + "=" * 70)
            print(f"▶ 阶段 [{idx}/{total_stages}] {stage_name}")
            print(f"  [流水线总进度条] [{overall_bar_str}] {overall_pct:4.1f}% | 阶段 {idx}/{total_stages}")
            print("=" * 70, flush=True)

            start_time = time.monotonic()
            proc = subprocess.Popen(
                [str(c) for c in cmd],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            last_step = -1
            for line in iter(proc.stdout.readline, ""):
                # 1. 匹配收集数量
                m_coll = self.RE_COLLECTED.search(line)
                if m_coll:
                    metrics["total"] = int(m_coll.group(3)) if m_coll.group(3) else int(m_coll.group(1))
                    print(f"  [收集完成] 本阶段共选取 {metrics['total']} 项测试用例，顺序执行中...", flush=True)
                    continue

                # 2. 匹配具体用例
                m_test = self.RE_TEST_LINE.match(line.strip())
                if m_test:
                    outcome = m_test.group(3)
                    pct = int(m_test.group(4))
                    filepath = Path(m_test.group(1)).name
                    testname = m_test.group(2)
                    nodeid = f"{filepath}::{testname}"

                    if outcome in ("PASSED", "XPASS"):
                        metrics["passed"] += 1
                        overall_passed += 1
                    elif outcome in ("FAILED", "XFAIL"):
                        metrics["failed"] += 1
                        overall_failed += 1
                        metrics["failures"].append(nodeid)
                        print(f"\n  ✖ [FAILED] {nodeid}", flush=True)
                    elif outcome == "SKIPPED":
                        metrics["skipped"] += 1
                        overall_skipped += 1

                    # 按设定的步长（如每 10%）输出双层进度详情
                    step_bucket = (pct // self.step_pct) * self.step_pct
                    if step_bucket > last_step and step_bucket > 0:
                        last_step = step_bucket
                        elapsed = time.monotonic() - start_time
                        done_count = metrics["passed"] + metrics["failed"] + metrics["skipped"]
                        rate = (done_count / elapsed) if elapsed > 0 else 0.0
                        eta = ((metrics["total"] - done_count) / rate) if rate > 0 and metrics["total"] > done_count else 0.0

                        # 双层进度指示：阶段进度条 + 用例进度条
                        case_bar_str = smooth_bar(float(pct), 20)
                        short_test = (nodeid[:26] + "..") if len(nodeid) > 28 else nodeid
                        print(
                            f"  [用例级进度条] [{case_bar_str}] {pct:3d}% ({done_count}/{metrics['total']}) | "
                            f"✔ {metrics['passed']} ✖ {metrics['failed']} ↷ {metrics['skipped']} | "
                            f"⏱ {elapsed:.1f}s ⌛ ~{eta:.1f}s ({rate:.1f} t/s) | {short_test}",
                            flush=True,
                        )

            proc.stdout.close()
            metrics["return_code"] = proc.wait()
            metrics["elapsed"] = time.monotonic() - start_time

            status_str = "成功 (PASSED)" if metrics["return_code"] == 0 else f"失败 (EXIT {metrics['return_code']})"
            print(
                f"✔ 阶段完成: {status_str} | 耗时: {metrics['elapsed']:.2f}s | "
                f"通过: {metrics['passed']} | 失败: {metrics['failed']} | 跳过: {metrics['skipped']}\n",
                flush=True,
            )
            pipeline_metrics.append(metrics)

            if metrics["return_code"] != 0:
                return metrics["return_code"], pipeline_metrics

        final_bar_str = smooth_bar(100.0, 16)
        print(f"🎉 全部流水线阶段已完成 [流水线总进度条] [{final_bar_str}] 100.0%\n", flush=True)
        return 0, pipeline_metrics


def print_summary_table(pipeline_metrics: List[Dict], total_elapsed: float):
    """打印精美详尽的多阶段门禁执行汇总表与耗时占比图。"""
    all_success = all(m["return_code"] == 0 for m in pipeline_metrics)

    if HAS_RICH:
        table = Table(
            title="📊 A-Stock 质量门禁执行汇总报告 (Execution Summary)",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("阶段编号与名称", style="cyan", min_width=26)
        table.add_column("用例数", justify="right", style="bold")
        table.add_column("通过 (✔)", justify="right", style="green")
        table.add_column("失败 (✖)", justify="right", style="red")
        table.add_column("跳过 (↷)", justify="right", style="yellow")
        table.add_column("耗时 (s)", justify="right", style="blue")
        table.add_column("耗时占比", justify="center", style="dim")
        table.add_column("速率", justify="right", style="dim")
        table.add_column("判定", justify="center")

        total_cases = 0
        total_passed = 0
        total_failed = 0
        total_skipped = 0

        for m in pipeline_metrics:
            total_cases += m["total"]
            total_passed += m["passed"]
            total_failed += m["failed"]
            total_skipped += m["skipped"]
            rate_str = f"{(m['total']/m['elapsed']):.1f} t/s" if m["elapsed"] > 0 else "-"
            time_pct = (m["elapsed"] / total_elapsed * 100.0) if total_elapsed > 0 else 0.0
            time_bar = smooth_bar(time_pct, 8)
            verdict_str = "[bold green]✔ PASSED[/bold green]" if m["return_code"] == 0 else "[bold red]✖ FAILED[/bold red]"

            table.add_row(
                m["stage_name"],
                str(m["total"]),
                str(m["passed"]),
                str(m["failed"]),
                str(m["skipped"]),
                f"{m['elapsed']:.2f}s",
                f"[{time_bar}] {time_pct:4.1f}%",
                rate_str,
                verdict_str,
            )

        console.print("\n")
        console.print(table)

        summary_title = "🎉 门禁全绿！所有阶段顺序执行通关 (0 failed)" if all_success else "⛔ 门禁未通过，发现失败用例"
        panel_style = "bold green" if all_success else "bold red"
        summary_content = (
            f"总执行用例: {total_cases} 例 | 通过: {total_passed} | 失败: {total_failed} | 跳过: {total_skipped}\n"
            f"总门禁耗时: {total_elapsed:.2f}s | 平均吞吐率: {(total_cases/total_elapsed if total_elapsed > 0 else 0):.1f} tests/s\n"
            f"执行契约: 前台顺序同步执行已落盘 | 零后台挂起 | 双层进度条保障全程可见"
        )
        console.print(Panel(summary_content, title=summary_title, style=panel_style))
        console.print("\n")
    else:
        print("\n" + "=" * 70)
        print("📊 A-Stock 质量门禁执行汇总报告 (Execution Summary)")
        print("=" * 70)
        for m in pipeline_metrics:
            verdict = "✔ PASSED" if m["return_code"] == 0 else "✖ FAILED"
            time_pct = (m["elapsed"] / total_elapsed * 100.0) if total_elapsed > 0 else 0.0
            time_bar = smooth_bar(time_pct, 8)
            print(
                f"• {m['stage_name']}: {m['passed']}/{m['total']} 通过 | 失败: {m['failed']} | 跳过: {m['skipped']} | "
                f"耗时: {m['elapsed']:.2f}s [{time_bar}] {time_pct:4.1f}% [{verdict}]"
            )
        print("-" * 70)
        res_str = "全绿通关 (0 failed)" if all_success else "存在失败"
        print(f"总计: 耗时 {total_elapsed:.2f}s | 判定: {res_str}")
        print("=" * 70 + "\n")


def run_pipeline(
    mode: str = "auto",
    targeted: Optional[str] = None,
    force_rich: Optional[bool] = None,
    step_pct: int = 10,
) -> int:
    """主调度函数：编排流水线阶段并通过双层动态进度条执行。"""
    stages = []

    # 阶段 1：极速核心门禁（必跑）
    stages.append((
        "极速核心门禁 (SPEC-SKILL-002: 6大支撑引擎 + 1+6技能契约与执行)",
        [sys.executable, "-m", "pytest", "-m", "core", "-v"],
    ))

    # 阶段 2：任务改动定向用例（若有指定）
    if targeted:
        stages.append((
            f"任务改动定向用例 ({targeted})",
            [sys.executable, "-m", "pytest", "-k", targeted, "-v"],
        ))

    # 阶段 3：交付链路门禁（根据模式智能决定或全量）
    need_delivery = True
    if mode == "fast":
        need_delivery = False
    elif mode == "auto":
        is_touched = detect_delivery_touch()
        if not is_touched:
            need_delivery = False
            if HAS_RICH and sys.stdout.isatty():
                console.print(
                    "\n💡 [bold green]智能裁剪生效[/bold green]: 未检测到打包器/安装脚本/宿主适配层改动，"
                    "已自动跳过交付打包测试，保持极速响应。\n"
                )
            else:
                print("\n💡 [智能裁剪生效] 未检测到打包器/安装脚本改动，已跳过交付打包测试。\n")

    if need_delivery:
        stages.append((
            "发布交付与打包安装集成门禁 (test_release_packaging_smoke.py)",
            [sys.executable, "-m", "pytest", "-m", "release_pack", "-v"],
        ))

    runner = DualProgressBarRunner(force_rich=force_rich, step_pct=step_pct)
    total_stages = len(stages)
    pipeline_start = time.monotonic()

    if HAS_RICH and sys.stdout.isatty():
        console.print(
            Panel(
                f"流水线模式: [bold cyan]{mode.upper()}[/bold cyan] | 总阶段数: [bold cyan]{total_stages}[/bold cyan] | "
                f"执行模式: [bold green]前台顺序同步执行[/bold green] | 进度指示: [bold magenta]双层动态进度条[/bold magenta]",
                title="🚀 A-Stock 质量门禁流水线启动",
                style="cyan",
            )
        )

    code, pipeline_metrics = runner.run_pipeline_with_progress(stages)
    total_elapsed = time.monotonic() - pipeline_start
    print_summary_table(pipeline_metrics, total_elapsed)

    if code != 0 and HAS_RICH and sys.stdout.isatty():
        console.print("[bold red]⛔ 流水线中断，请根据上方失败高亮修复后重试。[/bold red]")

    return code


def main():
    parser = argparse.ArgumentParser(description="A-Stock 质量门禁流水线（双层动态进度条与智能用例裁剪）")
    parser.add_argument("--core", action="store_true", help="执行全量 P0 核心门禁")
    parser.add_argument("--webapi", action="store_true", help="执行 WebUI 后端独立分仓门禁 (-m webapi)")
    parser.add_argument("--release-pack", action="store_true", help="执行发布交付打包安装集成门禁 (-m release_pack)")
    parser.add_argument("--sequential", action="store_true", help="强制全量顺序执行全部阶段")
    parser.add_argument("--fast", action="store_true", help="仅执行极速核心内核门禁")
    parser.add_argument("--targeted", type=str, help="指定改动模块的定向测试标签或方法名")
    parser.add_argument("--doctor", action="store_true", help="仅运行结构健康自检")
    parser.add_argument("--plain", action="store_true", help="强制使用平滑 Unicode 字符降级进度条")
    parser.add_argument("--rich", action="store_true", help="强制启用 Rich 动态双层进度条")
    parser.add_argument("--step", type=int, default=10, help="降级模式下的进度刷新步长百分比 (默认 10)")
    args = parser.parse_args()

    if args.doctor:
        cmd = [sys.executable, str(ROOT / "skill_bundle" / "runtime" / "doctor.py")]
        return subprocess.run(cmd, cwd=ROOT).returncode

    if args.webapi:
        cmd = [sys.executable, "-m", "pytest", "-m", "webapi", "-v"]
        return subprocess.run(cmd, cwd=ROOT).returncode

    if getattr(args, "release_pack", False):
        cmd = [sys.executable, "-m", "pytest", "-m", "release_pack", "-v"]
        return subprocess.run(cmd, cwd=ROOT).returncode

    force_rich = True if args.rich else (False if args.plain else None)

    if args.fast:
        return run_pipeline(mode="fast", targeted=args.targeted, force_rich=force_rich, step_pct=args.step)
    elif args.sequential or args.core:
        return run_pipeline(mode="sequential", targeted=args.targeted, force_rich=force_rich, step_pct=args.step)
    else:
        # 默认模式：智能改动感知流水线 + 双层动态进度条
        return run_pipeline(mode="auto", targeted=args.targeted, force_rich=force_rich, step_pct=args.step)


if __name__ == "__main__":
    raise SystemExit(main())
