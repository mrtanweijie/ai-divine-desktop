"""End-to-end eval harness for the Divine agent's coding capability.

每个场景是一道"考题"：一个埋了 bug / 缺了功能的夹具项目（scenarios/<id>/repo），
一段真实口吻的中文任务描述（task.md），以及一组隐藏测试（tests/）。

评分完全客观（SWE-bench 风格）：
- fail_to_pass：修复前必须失败、修复后必须通过——证明问题真的解决了；
- pass_to_pass：修复前后都必须通过——证明没有改坏别的东西；
- forbidden_paths：agent 不允许改动的路径（如 tests/**，防"删测试作弊"）。

agent 侧跑的是生产同一条链路（app.agent 的 _build_llm/_build_tools/_build_agent），
只是把 SSE/DB 隔离到临时目录，所以测出来的数字反映真实框架行为。

用法（在 divine-server 目录下）::

    .venv/bin/python -m evals.harness list
    .venv/bin/python -m evals.harness check                 # 场景夹具自检（不跑 agent）
    .venv/bin/python -m evals.harness run --fake            # 剧本模型全链路冒烟（零 API 成本）
    .venv/bin/python -m evals.harness run --model <model_id> [--runs 3]
    .venv/bin/python -m evals.harness run --scenario s01_off_by_one --model <model_id>
"""

from __future__ import annotations

import argparse
import asyncio
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = EVALS_DIR.parent  # divine-server/
SCENARIOS_DIR = EVALS_DIR / "scenarios"
RESULTS_DIR = EVALS_DIR / "results"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DEFAULT_MAX_MINUTES = 8


class EvalError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Scenario model
# ---------------------------------------------------------------------------


@dataclass
class Scenario:
    id: str
    category: str
    dir: Path
    fail_to_pass: list[str] = field(default_factory=list)
    pass_to_pass: list[str] = field(default_factory=list)
    forbidden_paths: list[str] = field(default_factory=list)
    max_minutes: int = DEFAULT_MAX_MINUTES
    task_text: str = ""
    solution_ops: list[dict] = field(default_factory=list)


def load_scenarios(only: list[str] | None = None, category: str | None = None) -> list[Scenario]:
    import yaml

    if not SCENARIOS_DIR.is_dir():
        raise EvalError(f"scenarios 目录不存在: {SCENARIOS_DIR}")
    scenarios: list[Scenario] = []
    for scenario_dir in sorted(SCENARIOS_DIR.iterdir()):
        config_path = scenario_dir / "config.yaml"
        if not config_path.is_file():
            continue
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        scenario = Scenario(
            id=str(config.get("id") or scenario_dir.name),
            category=str(config.get("category") or "uncategorized"),
            dir=scenario_dir,
            fail_to_pass=list(config.get("fail_to_pass") or []),
            pass_to_pass=list(config.get("pass_to_pass") or []),
            forbidden_paths=list(config.get("forbidden_paths") or []),
            max_minutes=int((config.get("budget") or {}).get("max_minutes") or DEFAULT_MAX_MINUTES),
            task_text=(scenario_dir / "task.md").read_text(encoding="utf-8"),
            solution_ops=list(config.get("solution") or []),
        )
        for required in ("fail_to_pass", "pass_to_pass"):
            if not getattr(scenario, required):
                raise EvalError(f"{scenario.id}: config.yaml 缺少 {required}")
        if only and scenario.id not in only:
            continue
        if category and scenario.category != category:
            continue
        scenarios.append(scenario)
    if only:
        found = {s.id for s in scenarios}
        missing = set(only) - found
        if missing:
            raise EvalError(f"场景不存在: {', '.join(sorted(missing))}")
    return scenarios


# ---------------------------------------------------------------------------
# Workspace / git helpers
# ---------------------------------------------------------------------------


def _git(ws: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(ws), *args], capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise EvalError(f"git {' '.join(args)} 失败: {proc.stderr.strip()[:500]}")
    return proc.stdout


def make_workspace(scenario: Scenario, root: Path) -> Path:
    """Fresh workspace: fixture repo + baseline git commit."""
    ws = root / scenario.id
    shutil.copytree(scenario.dir / "repo", ws)
    _git(ws, "init", "-q", "-b", "main")
    _git(ws, "-c", "user.name=eval", "-c", "user.email=eval@local", "add", "-A")
    _git(ws, "-c", "user.name=eval", "-c", "user.email=eval@local", "commit", "-qm", "baseline")
    return ws


def install_hidden_tests(scenario: Scenario, ws: Path) -> None:
    shutil.copytree(scenario.dir / "tests", ws / "tests")


def changed_files(ws: Path) -> list[str]:
    """All paths added/modified/deleted relative to the baseline commit."""
    lines = _git(ws, "status", "--porcelain").splitlines()
    paths: list[str] = []
    for line in lines:
        if len(line) < 4:
            continue
        raw = line[3:].strip().strip('"')
        if " -> " in raw:
            paths.extend(part.strip() for part in raw.split(" -> "))
        else:
            paths.append(raw)
    return sorted(set(paths))


def forbidden_hits(scenario: Scenario, ws: Path) -> list[str]:
    files = changed_files(ws)
    return [
        path
        for path in files
        if any(fnmatch.fnmatch(path, pattern) for pattern in scenario.forbidden_paths)
    ]


# ---------------------------------------------------------------------------
# Grading (pytest via the id plugin)
# ---------------------------------------------------------------------------


def run_pytest(ws: Path, out_dir: Path) -> dict[str, str]:
    """Run the hidden tests in ``ws``; return {nodeid: outcome}.

    结果 JSON 写到 ``out_dir``（工作区外），避免污染改动快照。
    """
    out_json = out_dir / ".eval_pytest_results.json"
    if out_json.exists():
        out_json.unlink()
    env = dict(os.environ)
    env["EVAL_PYTEST_JSON"] = str(out_json)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(EVALS_DIR), env.get("PYTHONPATH", ""), str(ws)]
    )
    try:
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest", "tests", "-q",
                "--tb=short", "--disable-warnings",
                # 显式锚定 rootdir：pytest 的 nodeid 是相对 rootdir 算的。
                # 工作区在 evals/.runs/ 下（仓库内）时，pytest 会向上找到
                # divine-server/pytest.ini 并把 rootdir 定成 divine-server，
                # nodeid 于是变成 "evals/.runs/<...>/tests/test_x.py::test_y"，
                # 与 config.yaml 里写的 "tests/test_x.py::test_y" 永不相等——
                # 全部场景会被误判成夹具损坏。锚到工作区即可与配置对齐。
                "--rootdir", str(ws),
                "-p", "evals_pytest_plugin",
            ],
            cwd=ws, env=env, capture_output=True, text=True, timeout=180,
        )
    except subprocess.TimeoutExpired as exc:
        raise EvalError(f"pytest 超时: {exc}") from exc
    if not out_json.exists():
        raise EvalError(
            f"pytest 未产出结果（exit={proc.returncode}）\n"
            f"stdout: {proc.stdout[-1500:]}\nstderr: {proc.stderr[-1500:]}"
        )
    items = json.loads(out_json.read_text(encoding="utf-8"))
    return {item["nodeid"]: item["outcome"] for item in items}


def grade(scenario: Scenario, ws: Path, out_dir: Path, changed: list[str]) -> dict:
    """Grade the workspace. ``changed`` 必须是装隐藏测试之前的改动快照。"""
    results = run_pytest(ws, out_dir)
    fail_to_pass = {t: results.get(t, "missing") for t in scenario.fail_to_pass}
    pass_to_pass = {t: results.get(t, "missing") for t in scenario.pass_to_pass}
    fixed = all(v == "passed" for v in fail_to_pass.values())
    stable = all(v == "passed" for v in pass_to_pass.values())
    hits = [
        path
        for path in changed
        if any(fnmatch.fnmatch(path, pattern) for pattern in scenario.forbidden_paths)
    ]
    return {
        "fail_to_pass": fail_to_pass,
        "pass_to_pass": pass_to_pass,
        "forbidden_hits": hits,
        "resolved": fixed and stable and not hits,
        "changed_files": changed,
    }


def check_baseline(scenario: Scenario, root: Path) -> dict:
    """Fixture self-check: fail_to_pass must fail, pass_to_pass must pass."""
    ws = make_workspace(scenario, root)
    try:
        install_hidden_tests(scenario, ws)
        results = run_pytest(ws, ws.parent)
        bad_ftp = [t for t in scenario.fail_to_pass if results.get(t) == "passed"]
        bad_ptp = [t for t in scenario.pass_to_pass if results.get(t) != "passed"]
        missing = [
            t for t in scenario.fail_to_pass + scenario.pass_to_pass
            if t not in results
        ]
        ok = not bad_ftp and not bad_ptp and not missing
        return {"ok": ok, "bad_ftp": bad_ftp, "bad_ptp": bad_ptp, "missing": missing}
    finally:
        shutil.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# Agent execution (production stack, isolated env)
# ---------------------------------------------------------------------------


def prepare_isolated_env(run_root: Path) -> None:
    """Point the app's storage at the run dir; keep real settings for models.

    settings_store.load() 在覆盖 env 前先读一次真实配置并打补丁返回，
    这样 ``run --model`` 能用用户已配置的模型/Key，而 DB/输出全部落在临时目录。
    """
    real_settings = None
    try:
        from app.config import settings_store

        real_settings = settings_store.load()
    except Exception:  # noqa: BLE001 — demo 环境没有配置文件也能跑 --fake
        real_settings = None

    os.environ["DB_PATH"] = str(run_root / "eval.db")
    os.environ["DIVINE_DATA_DIR"] = str(run_root / "data")
    os.environ["DIVINE_WORKSPACE_DIR"] = str(run_root / "workspaces-root")
    os.makedirs(run_root / "data", exist_ok=True)

    if real_settings is not None:
        settings_store.load = lambda: real_settings  # type: ignore[assignment]

    from app.db.migrations import init_db

    init_db()


async def run_agent(scenario: Scenario, ws: Path, *, model_id: str | None,
                    think: bool, fake: bool, approval: str) -> dict:
    """Run one agent turn against the production stack; return run metrics."""
    from langchain_core.messages import HumanMessage

    from app.agent.core import AgentRunContext, _build_llm
    from app.agent.tools import _build_agent, _build_tools
    from app.db.sessions import create_session

    # 生产链路的工具执行会写 tool_runs 等表（session 外键），先建会话行。
    session = await asyncio.to_thread(
        create_session, f"eval-{scenario.id}"
    )
    ctx = AgentRunContext(
        session_id=session["id"],
        workspace=ws,
        approval_mode=approval,
        plan_choice_resolved=True,   # 跳过"是否先出方案"交互
        plan_approved=True,          # 跳过 write_todos 审批交互
        intents=set(),               # 空 → 注入全量工具（不按意图裁减）
        think=think,
        model_id=model_id,
        tool_mode="native",
    )
    tools = _build_tools(ctx)
    if fake:
        from evals.fake_model import build_fake_llm

        llm = build_fake_llm(scenario.solution_ops)
    else:
        llm = _build_llm(think=think, model_id=model_id)
    agent = _build_agent(llm, tools, ctx)
    config = {
        "configurable": {"thread_id": ctx.session_id},
        "recursion_limit": 256,
    }

    started = time.monotonic()
    try:
        state = await asyncio.wait_for(
            agent.ainvoke(
                {"messages": [HumanMessage(content=scenario.task_text)]}, config
            ),
            timeout=scenario.max_minutes * 60,
        )
    except asyncio.TimeoutError:
        raise EvalError(
            f"agent 超出场景时间预算（{scenario.max_minutes} 分钟）"
        ) from None
    seconds = round(time.monotonic() - started, 1)

    messages = state.get("messages") or []
    ai_messages = [m for m in messages if getattr(m, "type", "") == "ai"]
    tokens_in = tokens_out = 0
    for message in ai_messages:
        usage = getattr(message, "usage_metadata", None) or {}
        tokens_in += int(usage.get("input_tokens") or 0)
        tokens_out += int(usage.get("output_tokens") or 0)
    return {
        "seconds": seconds,
        "model_calls": len(ai_messages),
        "tool_calls": sum(len(getattr(m, "tool_calls") or []) for m in ai_messages),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
    }


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_list(scenarios: list[Scenario]) -> None:
    print(f"{'id':<34} {'category':<12} fail_to_pass pass_to_pass")
    for sc in scenarios:
        print(
            f"{sc.id:<34} {sc.category:<12} "
            f"{len(sc.fail_to_pass):>12} {len(sc.pass_to_pass):>13}"
        )
    print(f"\n共 {len(scenarios)} 个场景")


def cmd_check(scenarios: list[Scenario], run_root: Path) -> int:
    failures = 0
    print(f"自检 {len(scenarios)} 个场景的夹具（基线测试预期）...")
    for sc in scenarios:
        try:
            result = check_baseline(sc, run_root)
        except EvalError as exc:
            print(f"  ✗ {sc.id}: {exc}")
            failures += 1
            continue
        if result["ok"]:
            print(
                f"  ✓ {sc.id}: fail_to_pass={len(sc.fail_to_pass)} 全红, "
                f"pass_to_pass={len(sc.pass_to_pass)} 全绿"
            )
        else:
            print(f"  ✗ {sc.id}: {result}")
            failures += 1
    if failures:
        print(f"\n{failures} 个场景夹具有问题，先修复再跑分")
    else:
        print("\n全部夹具符合预期（fail_to_pass 基线全红、pass_to_pass 基线全绿）")
    return 1 if failures else 0


async def run_one(scenario: Scenario, run_root: Path, *, model_id: str | None,
                  think: bool, fake: bool, approval: str, run_index: int) -> dict:
    ws = make_workspace(scenario, run_root / f"{scenario.id}__run{run_index}")
    row: dict = {"scenario": scenario.id, "category": scenario.category,
                 "run": run_index}
    try:
        # 1. 基线验证（临时副本上跑，随后删除隐藏测试，避免 agent 看到答案）
        check = check_baseline(scenario, run_root / f"{scenario.id}__baseline{run_index}")
        if not check["ok"]:
            row.update(error="scenario_fixture_broken", detail=check)
            return row

        # 2. agent 跑任务（生产栈；隐藏测试不在工作区）
        try:
            row.update(await run_agent(
                scenario, ws, model_id=model_id, think=think,
                fake=fake, approval=approval,
            ))
        except EvalError as exc:
            row.update(error=str(exc))
            return row

        # 3. 评分：改动快照必须在装隐藏测试之前截取
        changed = changed_files(ws)
        install_hidden_tests(scenario, ws)
        row.update(grade(scenario, ws, ws.parent, changed))
        return row
    finally:
        shutil.rmtree(ws, ignore_errors=True)


async def cmd_run(scenarios: list[Scenario], args: argparse.Namespace) -> int:
    ts = time.strftime("%Y%m%d_%H%M%S")
    model_tag = "fake" if args.fake else (args.model or "default")
    run_root = EVALS_DIR / ".runs" / f"{ts}__{model_tag}"
    run_root.mkdir(parents=True, exist_ok=True)
    prepare_isolated_env(run_root)

    rows: list[dict] = []
    started = time.time()
    for scenario in scenarios:
        for run_index in range(1, args.runs + 1):
            label = scenario.id if args.runs == 1 else f"{scenario.id}#{run_index}"
            print(f"▶ {label} ...", flush=True)
            try:
                row = await run_one(
                    scenario, run_root,
                    model_id=args.model, think=args.think,
                    fake=args.fake, approval=args.approval,
                    run_index=run_index,
                )
            except Exception as exc:  # noqa: BLE001 — 单场景失败不拖垮整轮
                row = {"scenario": scenario.id, "run": run_index,
                       "error": f"{type(exc).__name__}: {exc}"}
            status = "✓ resolved" if row.get("resolved") else "✗ failed"
            if row.get("error"):
                status = f"✗ error ({row['error']})"
            stats = (
                f"  steps={row.get('model_calls', '-')} "
                f"tools={row.get('tool_calls', '-')} "
                f"tokens={row.get('tokens_in', 0)}+{row.get('tokens_out', 0)} "
                f"{row.get('seconds', '-')}s"
            )
            print(f"  {status}{stats}")
            rows.append(row)

    resolved = sum(1 for r in rows if r.get("resolved"))
    report = {
        "meta": {
            "started": ts,
            "model": model_tag,
            "fake": args.fake,
            "think": args.think,
            "approval": args.approval,
            "runs_per_scenario": args.runs,
            "wall_seconds": round(time.time() - started, 1),
        },
        "scenarios": rows,
        "summary": {
            "resolved": resolved,
            "total": len(rows),
            "resolve_rate": round(resolved / len(rows), 3) if rows else 0.0,
        },
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = RESULTS_DIR / f"{ts}__{model_tag}.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(
        f"\n==== resolve rate: {resolved}/{len(rows)} "
        f"({report['summary']['resolve_rate']:.0%}) ===="
    )
    print(f"报告: {report_path}")
    if not args.keep:
        shutil.rmtree(run_root, ignore_errors=True)
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="evals.harness", description="Divine agent 编程能力评测"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def common(scenario_cmd) -> None:
        scenario_cmd.add_argument("--scenario", action="append", default=[],
                                  help="只跑指定场景 id（可重复）")
        scenario_cmd.add_argument("--category", default=None,
                                  help="只跑指定类别（bug_single/bug_cross/feature/debug/refactor）")

    common(sub.add_parser("list", help="列出场景"))
    p_check = sub.add_parser("check", help="夹具自检：基线 fail_to_pass 全红、pass_to_pass 全绿")
    common(p_check)
    p_run = sub.add_parser("run", help="跑 agent 评分")
    common(p_run)
    p_run.add_argument("--model", default=None, help="settings 里的 model id（默认 active 模型）")
    p_run.add_argument("--think", action="store_true", help="开启思考模式")
    p_run.add_argument("--fake", action="store_true",
                       help="用剧本模型跑全链路（零 API 成本，验证 harness 本身）")
    p_run.add_argument("--runs", type=int, default=1, help="每场景重复次数（默认 1）")
    p_run.add_argument("--approval", default="assist", choices=["assist", "full"],
                       help="审批模式（默认 assist，避免交互确认卡住）")
    p_run.add_argument("--keep", action="store_true", help="保留临时工作区便于调试")
    args = parser.parse_args()

    scenarios = load_scenarios(
        only=args.scenario or None, category=args.category
    )
    if not scenarios:
        print("没有匹配的场景")
        return 1

    if args.command == "list":
        cmd_list(scenarios)
        return 0
    if args.command == "check":
        run_root = EVALS_DIR / ".runs" / f"check_{time.strftime('%Y%m%d_%H%M%S')}"
        run_root.mkdir(parents=True, exist_ok=True)
        try:
            return cmd_check(scenarios, run_root)
        finally:
            shutil.rmtree(run_root, ignore_errors=True)
    return asyncio.run(cmd_run(scenarios, args))


if __name__ == "__main__":
    sys.exit(main())
