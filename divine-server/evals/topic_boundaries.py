"""话题边界调参工具：导出相邻轮相似度 + 统计同/跨话题分布。

使用方法（离线，不碰运行时）：

  1. 导出：python -m evals.topic_boundaries export <session_id> --out conv.jsonl
     → 拉取该会话全量消息，逐轮计算与上一轮的 TF-IDF 余弦相似度，输出 JSONL
     （第一轮 sim_to_prev 为 null；tool 消息跳过）。
  2. 标注：人工编辑 conv.jsonl，为每一行补充 "is_switch": true/false
     （该轮相对上一轮是否发生了话题切换；拿不准的留 null 会跳过）。
  3. 统计：python -m evals.topic_boundaries stats conv.jsonl
     → 分组输出同话题 / 跨话题的相似度分布（均值/标准差/数量），并给出
     「间隔带」建议阈值；若两分布重叠则提示需要增加意图分类/实体信号。

阈值落地参考：间隔带内取值。阈值偏高 → 漏切/串味；偏低 → 误切/断上下文。
建议收集 50+ 段真实对话标注后统计，比拍脑袋阈值可靠。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db  # noqa: E402
from app.db.retrieval import rank_documents  # noqa: E402

# 导出时跳过的消息角色（工具结果等非对话内容）。
_SKIP_ROLES = {"tool", "system"}


def _pair_similarity(prev: str, cur: str) -> float:
    """TF-IDF 余弦：prev 作为 query，cur 作为唯一文档（单文档时 IDF=1）。"""
    hits = rank_documents(prev, [cur], top_k=1)
    return round(hits[0][0], 4) if hits else 0.0


def export_session(session_id: str, out_path: Path) -> int:
    rows = db.list_messages(session_id)
    lines: list[dict] = []
    prev_text = ""
    for row in rows:
        role = str(row.get("role") or "")
        if role in _SKIP_ROLES:
            continue
        text = str(row.get("content") or "").strip()
        if not text:
            continue
        sim = _pair_similarity(prev_text, text) if prev_text else None
        lines.append(
            {
                "turn": len(lines) + 1,
                "role": role,
                "text": text[:500],
                "sim_to_prev": sim,
            }
        )
        prev_text = text
    out_path.write_text(
        "\n".join(json.dumps(line, ensure_ascii=False) for line in lines)
        + "\n",
        encoding="utf-8",
    )
    print(f"导出了 {len(lines)} 条消息 -> {out_path}")
    print("下一步：人工在 JSONL 中为每行补充 is_switch: true/false，再运行 stats 子命令。")
    return 0


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mean = _mean(xs)
    return (sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def stats(annotated: Path) -> int:
    pairs: list[tuple[float, bool]] = []
    for line_num, line in enumerate(annotated.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            print(f"警告：{annotated}:{line_num} 不是合法 JSON，跳过", file=sys.stderr)
            continue
        sim = row.get("sim_to_prev")
        switch = row.get("is_switch")
        if sim is None or switch not in (True, False):
            continue
        pairs.append((float(sim), bool(switch)))

    if len(pairs) < 2:
        print("有效标注不足（至少需要 2 条带 is_switch 且 sim 非空的记录）。")
        return 1

    same = [sim for sim, sw in pairs if not sw]
    diff = [sim for sim, sw in pairs if sw]

    print("=" * 60)
    print("话题边界相似度分布")
    print("=" * 60)
    print(
        f"同话题:  n={len(same):3d}  均值={_mean(same):.3f}  "
        f"σ={_std(same):.3f}  区间=[{min(same):.3f}, {max(same):.3f}]"
    )
    print(
        f"跨话题:  n={len(diff):3d}  均值={_mean(diff):.3f}  "
        f"σ={_std(diff):.3f}  区间=[{min(diff):.3f}, {max(diff):.3f}]"
    )
    print("-" * 60)

    if not same or not diff:
        print("只有单侧标注，无法给出间隔带。请补另一侧样本。")
        return 0

    # 间隔带 = [跨话题上界, 同话题下界]
    lo = max(_mean(diff) + _std(diff), min(diff))
    hi = min(_mean(same) - _std(same), max(same))
    if lo < hi:
        print(f"建议阈值（间隔带）: 相似度 < {lo:.3f} 视为切换，> {hi:.3f} 视为同话题")
        print(f"中间灰色区 [{lo:.3f}, {hi:.3f}] 建议交给意图/实体信号判断")
    else:
        overlap = max(lo - hi, 0.0)
        print(f"两分布重叠（间隔带不存在，重叠 {overlap:.3f}）——单靠相似度区分不了话题")
        print("建议：增加显式切换词 / 意图分类 / 实体重叠信号后重新统计。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_export = sub.add_parser("export", help="导出会话相邻轮相似度 JSONL")
    p_export.add_argument("session_id")
    p_export.add_argument("--out", default="topic_boundaries.jsonl")

    p_stats = sub.add_parser("stats", help="统计已标注 JSONL 的相似度分布")
    p_stats.add_argument("annotated")

    args = parser.parse_args()
    if args.command == "export":
        return export_session(args.session_id, Path(args.out))
    return stats(Path(args.annotated))


if __name__ == "__main__":
    raise SystemExit(main())
