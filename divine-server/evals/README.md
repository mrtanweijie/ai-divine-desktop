# Agent 编程能力 Eval Harness

客观度量 agent 的真实编码能力：每个场景是一个埋了 bug / 缺了功能的迷你项目，
agent 用**生产同一条链路**（`app/agent` 的模型构建、工具、审批、prompt）完成中文任务，
最后由隐藏测试自动判分（SWE-bench 风格）。

## 评分规则

- `fail_to_pass`：修复前必须失败、修复后必须通过——证明问题真被解决；
- `pass_to_pass`：修复前后都必须通过——证明没改坏别的东西；
- `forbidden_paths`：禁止改动的路径（默认 `tests/**`，防"删测试作弊"）；
- 预算：每场景有 `max_minutes` 时间上限，超时判负。

## 用法（在 divine-server 目录下）

```bash
.venv/bin/python -m evals.harness list              # 列出场景
.venv/bin/python -m evals.harness check             # 夹具自检（不跑 agent，秒级）
.venv/bin/python -m evals.harness run --fake        # 剧本模型全链路冒烟（零 API 成本）
.venv/bin/python -m evals.harness run               # 用当前 active 模型跑分
.venv/bin/python -m evals.harness run --model glm-5.3 --runs 3
.venv/bin/python -m evals.harness run --category bug_cross
.venv/bin/python -m evals.harness run --scenario s01_pagination_off_by_one --keep
```

报告写入 `evals/results/<时间戳>__<模型>.json`，含每场景的
resolved / 步数 / token / 耗时 / 改动文件，以及整体 resolve rate。
`--keep` 保留临时工作区（`.evals/.runs/`）便于人工排查。

## 场景结构

```
scenarios/s01_pagination_off_by_one/
├── repo/        # 夹具项目（会被拷到临时目录并 git init 基线提交）
├── tests/       # 隐藏测试：agent 跑完任务后才拷进工作区评分
├── task.md      # 用户任务描述（真实口吻中文）
└── config.yaml  # 评分配置 + solution（--fake 剧本用，也当作"标准答案"文档）
```

## 隔离说明

跑分时 DB（`DB_PATH`）与数据目录（`DIVINE_DATA_DIR`）全部指向
`evals/.runs/<本次运行>/`，不影响真实应用数据；用户真实 settings 只读加载
（用于 `--model` 解析模型配置），不会被修改。审批固定绕过交互确认
（`--approval assist`），terminal 仍受安全策略约束。

## 约定

- `check` 必须全绿才能跑分——保证夹具本身没坏；
- 每次改动 agent 框架（prompt/工具/上下文策略）前后各跑一轮对比；
- LLM 有随机性，正式对比用 `--runs 3` 取平均；
- 新场景四类必备：单文件 bug / 跨文件 bug / 小功能 / 排障，逐步补充
  重构与大任务（上下文压力）场景。
