"""记忆检索基线评测（022 §7-7）。

用法（divine-server 目录下）::

    .venv/bin/python -m evals.memory_retrieval.runner

在临时 DB 里灌入语料，对每条 query 跑生产检索（db.search_memories），
统计 top-5 命中率与 MRR，结果写入 ``evals/results/memory_retrieval_<ts>.json``。
该基线是“是否引入本地 embedding 模型”的量化退出条件。
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .dataset import CASES, CORPUS


def run_eval() -> dict:
    tmp = tempfile.mkdtemp(prefix="divine-memory-eval-")
    import os

    os.environ["DB_PATH"] = str(Path(tmp) / "memories.db")
    os.environ["DIVINE_DATA_DIR"] = str(Path(tmp) / "data")
    os.environ["DIVINE_WORKSPACE_DIR"] = str(Path(tmp) / "workspace")

    from app import db

    db.init_db()
    for entry in CORPUS:
        db.save_memory(
            entry["content"],
            category=entry["category"],
            importance=0.6,
        )

    hits = 0
    mrr_total = 0.0
    details: list[dict] = []
    for case in CASES:
        results = db.search_memories(case["query"], limit=5)
        rank = 0
        for index, memory in enumerate(results, start=1):
            content = str(memory.get("content") or "")
            if any(token in content for token in case["expect"]):
                rank = index
                break
        hits += 1 if rank else 0
        mrr_total += 1.0 / rank if rank else 0.0
        details.append(
            {
                "query": case["query"],
                "expect": case["expect"],
                "rank": rank,
                "top5": [str(m.get("content") or "") for m in results],
            }
        )

    total = len(CASES)
    return {
        "total": total,
        "hit_at_5": round(hits / total, 4),
        "mrr": round(mrr_total / total, 4),
        "cases": details,
    }


def main() -> None:
    report = run_eval()
    results_dir = Path(__file__).resolve().parents[1] / "results"
    results_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = results_dir / f"memory_retrieval_{stamp}.json"
    out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"记忆检索基线：top-5 命中率 {report['hit_at_5']:.1%}，"
        f"MRR {report['mrr']:.3f}（{report['total']} 条用例）"
    )
    print(f"报告已写入 {out}")
    misses = [c for c in report["cases"] if not c["rank"]]
    if misses:
        print("未命中用例：")
        for case in misses:
            print(f"  - {case['query']}（期望 {case['expect']}）")


if __name__ == "__main__":
    main()
