# 004 · 交互式图形能力改造方案（2026-09-08）

> **定位**：本文档是执行计划。视觉规范 / 场景矩阵 / GraphIR 完整规范 / P0 验收清单统一见
> `docs/design/020-x6-multi-scenario-20260908.md`（多场景方案，唯一设计真源）。
> 文档冲突时以 020 为准，本文档负责「怎么落地」。

## 背景与目标

现状：图形能力 = Agent 在正文输出 ```mermaid 代码块 → 前端 `MermaidBlock.tsx` 静态渲染；导出走 `mermaid_export` 存 `.mmd`。无交互动画、无数据流向指示，且只有流程图一种。

目标：新增一条与 Mermaid 并存的交互式图形链路——Agent 输出声明式 GraphIR → 前端按 ScenarioPreset 确定性渲染（AntV X6 3.x）。**范围从单一流程图扩展为 13 类「节点 + 边」图**（flow / dag / dataflow / state / org / mindmap / topology / er / swimlane / concept / class / fishbone / timeline），支持：

- 数据流向动画（antline / pulse；particles 降为观察项）
- 生成过程中的"生长式"呈现（真流式增量渲染）
- 节点点击详情、hover 关联高亮
- 导出 PNG/SVG
- **历史回放直接渲染最终图，不自动播动画**（既定决策）

核心原则：**Agent 只输出拓扑与语义意图——不算坐标、不算时序、不写渲染代码、不选布局、不选颜色**。布局交给 `@antv/layout`，形态与节奏由前端 Preset 常量表决定。

## 关键设计决策

1. **GraphIR + 工具 `render_graph`**。IR 只含 `kind` + `role` + 拓扑与语义意图，不含任何视觉形态——布局、节点形态、路由、交互等级、动效全部在前端 **ScenarioPreset** 常量表。加场景 = Preset 表加一行，不改 schema、不改后端、不改渲染器。
2. **`kind` 封闭枚举 13 项**。校验失败**不静默 fallback 到 `flow`**——静默降级会把错误形态固化成正确结果，Agent 永远学不会选对场景。结构化报错让 Agent 自纠。
3. **布局引擎用 `@antv/layout`**。一套库覆盖 9/13 场景（dagre / antv-dagre / force / compactBox / mindmap）；fishbone / timeline 无通用算法，各写一个自定义布局函数。
4. **节点上限按场景分档**（flow 80 / dag 120 / dataflow 80 / state 40 / org 150 / mindmap 120 / topology 100 / er 24 / swimlane 60 / concept 80 / class 20 / fishbone 40 / timeline 30），仍以 P0 实测帧率拐点为准修正。
5. **新增交互分级 L0–L3 + 插件按需加载**：L0 核心包（er/class/fishbone/timeline）→ L1 +Scroller/Minimap（org/mindmap/topology/concept）→ L2 +Selection/History（flow/dag/dataflow/state/swimlane）。**L3 在线编排（拖拽建边、编辑标签、撤销重做）首期不做**——与「AI 直接产出可用结果」的定位冲突。
6. **富节点用纯 SVG markup，禁用 `@antv/x6-react-shape` 与一切 HTML 节点**。React 节点渲染进 `foreignObject`：WKWebView 下 `toPNG` 极易失败、样式是外联 CSS 导出即丢——与「导出 PNG/SVG 是硬需求」直接冲突（P0 清单第 11 条保留反证通道）。
7. **DAG 场景分为 `dag`（任务编排）与 `dataflow`（数据加工）两个 kind**，各用自定义富节点（dag-node 188×40 / dp-node 212×48，图标 + 标题 + 状态徽标）。图标全部内联 path 白名单，**禁止 URL / 外链图片**（本地优先 + 导出后外链失效）。
8. **四类通用矩形撑不住的场景富节点化**：state（UML 状态框 + 伪状态 initial/final/choice + active 脉冲，全图最多 1 个）、org（头像首字 + 职位 + 折叠角标）、mindmap（三级形态 + 分支色）、concept（圆按度定尺寸 + 类型图标 + 名称外置 + 边线型表关系）。规格见 020 §5.5 / §5.6。
9. **tone 收敛**：`neutral ≡ info` 不上色——只有 `success / warning / error` 上语义色且底色仅 8% 微染，info 的蓝只出现在流动线上。默认态是干净的黑白图。dark 档 `info = #61A7D0`（不复用图表色 `#036EAD`，暗底 1px 描边不可见），色值放独立 `graphTones.ts`，**不复用 `chartOptions.ts` 常量**。
10. **双层边**：静态底线（中性色、常驻）讲拓扑 + 流动层（tone 色、可关）讲数据流。导出、历史回放、关动画时图都完整可读。
11. **动效时序定稿**：节点入场 280ms + stagger 45ms；边入场 480ms（必须比节点慢，否则"线画完等节点"观感倒置）；工具条**常驻**（opacity .72→1，播放/流动是持续状态，hover 才出现判断不了当前状态）；分支色（mindmap `bc`）由**前端按分支顺序自动分配，IR 中禁止出现**。
12. **渲染体系边界明确**：时序图 / 甘特图归 Mermaid（X6 自建生命线版式投入产出比差）；类图双轨（快速看 Mermaid、点击详情 X6）；统计图表归 ECharts；地图 / 平面图 / 电路图不做。X6 链路稳定后评估迁移"静态流程图"场景，时序/甘特永久保留 Mermaid。
13. **"生长式"呈现分两档，形态由 P0 定**：tool 参数在 LLM 生成完整 JSON 后才到达 adapter，"后端把完整 IR 拆成事件逐个下发"在时间上无增益（等效伪流式）。真·逐节点生长需在 `core/sse.py` 消息层捕获 `tool_call_chunks` 参数增量 + 流式 JSON 解析（现有 `_consume_message` 只 drain text/reasoning，该管道需新建）——可行性列入 P0 验证（020 §10 增补第 16 条）；验证不通过则采用**回放式生长**（完整 IR 到达后按 nodes→edges 顺序节流播放入场动画）。两档共用同一前端调度器，差异仅在事件到达时机。
14. **导出为前端主导**：generate_chart 的后端 SVG 导出是纯 Python 手写渲染器（`app/docgen/chart/svg.py`），不跑 ECharts；X6 无后端等价物，后端复用导出脚本模式的类比不成立。流程图导出统一走前端 `graph.toSVG()/toPNG()` + Tauri 写文件；PDF 嵌入由前端导出文件后走既有文件引用。**不做后端 export_svg**。

## 架构

```
Agent (LangGraph, divine-server)
  └─ 新工具 render_graph
       ├─ 参数：GraphIR（kind 封闭枚举 + 白名单校验，后端结构校验，拒绝即结构化报错）
       └─ 输出：tool 结果携带完整 GraphIR（持久化 + 前端渲染数据源），经 SSE tool 事件下发（带 call_id）
             │  前端按既定编排规则节流播放（回放式生长）；
             │  若 P0 验证 tool_call_chunks 可行，则升级为真流式（见决策 13）
             ▼
前端渲染进程 (divine-app, React)
  ├─ GraphIR：类型 + 白名单校验（IR 来自 LLM，按不可信输入处理）
  ├─ Preset Resolver：kind → 布局引擎 + 参数 / 节点形态族 / 边族 / 交互等级 / 动效 / 上限
  ├─ RenderScheduler：80ms 窗口批处理，防高频事件卡顿
  ├─ AnimationManager：并发动画 ≤ 20（P0 实测后调整），超限直接置终态
  ├─ LayoutService：流式阶段占位布局 → done 后 @antv/layout 终局布局一次
  └─ GraphRenderer：X6 渲染（自定义 SVG markup 节点）+ 双层边 + 动效编排
```

与现有链路分流（写进工具描述，对齐 `generate_chart` 的引导话术风格）：

| 需求 | 链路 |
| --- | --- |
| 时序图 / 甘特图 / 快速类图 / 静态流程图 | Mermaid 代码块（不动） |
| 13 类「节点 + 边」图，需要动画 / 交互 / 演示 / 导出 | `render_graph` |
| 数据图表 | `generate_chart`（ECharts） |
| 地图 / 平面图 / 电路图 | **不做**，分流话术明确拒绝 |
| C4 / 正经架构图 | 首期不做；`topology` 可近似覆盖，三增强方案见「后续演进」节 |

## GraphIR 设计

```jsonc
{
  "kind": "flow",                        // 唯一场景字段，13 项封闭枚举
  "meta": { "title": "订单支付链路", "summary": "…" },
  "nodes": [
    { "id": "user", "label": "提交订单",
      "role": "start",                   // 节点语义角色（start|end|process|decision|data|entity|state|milestone|member…）
      "tone": "info",                    // success|warning|error|info|neutral（禁止色值）
      "note": "点击节点查看的详情",
      "badge": "P0",
      // ↓ 场景特有可选字段（Preset 声明支持，其他场景忽略）
      "state": "running",                // dag/dataflow：pending|running|success|failed（映射 tone，state 优先）
      "icon": "flask",                   // dag/dataflow：封闭枚举内联图标，禁止 URL
      "pseudo": "initial",               // state：initial|final|choice（伪状态，无 label）
      "active": true,                    // state：当前激活态，全图最多 1 个
      "role_desc": "…",  "count": 4,     // org：职位/编制、子节点数（count 缺失不画角标）
      "type": "module",                  // concept：module|tech|data|process|concept（圆内图标）
      "lane": "order",                   // swimlane：泳道归属
      "parent": "g1" }                   // 层次归属（org / mindmap 可选）
  ],
  "edges": [
    { "id": "e1", "source": "user", "target": "gateway",
      "label": "HTTPS",                  // state 场景支持 UML「事件[守卫]」，守卫由前端解析渲染
      "kind": "flow",                    // 边语义：flow|dep|transit|inherit|assoc|contain（决定线型与 marker）
      "tone": "info",
      "style": "solid",                  // solid|dashed|dotted（concept：实线包含 / 虚线依赖 / 点线引用）
      "flow": { "mode": "antline", "tone": "success", "speed": 1 } }
  ],
  "groups": [
    { "id": "g1", "label": "接入层", "type": "cluster", "members": ["cdn","waf","gw"] }
  ],
  "demoPath": ["user", "gateway", "pay"] // 可选：演示路径，节奏由前端编排
}
```

**禁止出现的字段**：任何 `x/y/w/h` 坐标、任何色值、`bc`（分支色索引，前端按分支顺序分配）、`direction` / `shape`（已下沉 Preset）。

### 后端强校验清单（完整版见 020 §3）

1. `kind` ∈ 13 项枚举，未知即拒绝（**不静默 fallback**）
2. `role` ∈ 枚举；`icon` ∈ 封闭枚举（8 任务图标 / 6 加工类型），禁止任何 URL
3. `pseudo` ∈ `initial|final|choice`；`active=true` 全图最多 1 个；`type` ∈ 5 类枚举
4. `tone` ∈ 5 项枚举，禁止色值字符串；`speed` ∈ `0.5|1|2`
5. `lane` / `parent` / `group.members` 必须指向已声明 id
6. `flow` 仅 `mode: antline|pulse`
7. `nodes.length` ≤ `PRESETS[kind].limit.nodes`（上限表需后端镜像一份常量）
8. 拒绝 `__proto__`、`on*`、任意 attrs 注入
9. 边 `label` 允许 `事件[守卫]` 格式（state 场景），守卫内容做长度与转义校验

### ScenarioPreset（概要）

13 个场景各一行常量：布局引擎 + 参数、节点形态、边族、容器族、交互等级（L0–L3）、动效、节点上限、视口策略（fit/center/scroll）。完整表见 020 §4。实现上是一张前端常量表 + Resolver，**新增场景不改 schema、不改后端、不改渲染器**——这条本身是 P2.5 的验收标准。

## 增量事件协议（回放式形态下的内部表示）

事件流是**前端调度器的输入接口**，不是后端流式下发通道（见决策 13）：前端收到完整 IR 后自行展开为事件序列、经 RenderScheduler 节流播放；真流式形态下同一接口改由后端 token 级解析供给，前端零改动：

```jsonc
{ "op": "set_meta",  "data": { "kind": "flow", "title": "订单支付链路" } }
{ "op": "add_node",  "data": { "id": "user", "label": "提交订单", "role": "start" } }
{ "op": "add_edge",  "data": { "id": "e1", "source": "user", "target": "gateway", "flow": { "mode": "antline" } } }
{ "op": "done" }
```

**持久化**：`done` 后后端把完整 IR 合并存入 tool 调用结果（与 generate_chart 存 option 同模式）。历史回放从完整 IR 直接渲染终态，**不播入场动画、不自动开流动**；`demoPath` 场景在工具条提供"播放演示"按钮，由用户手动触发。

### 中断 / 失败 / 重试语义

- **用户取消**：已渲染部分保留并显示"未完成"标记；对齐现有 `_persist_partial_once` 机制——仅校验通过的完整 IR 落库，半截 IR 不落库
- **校验失败 Agent 重试**：前端按 call_id 对旧图整体 reset 后重渲染；同一 call_id 事件流带序号，乱序/重复丢弃
- **编辑已有图**：Agent 重发完整 GraphIR，按新 call_id 全量替换；`remove/update` 增量语义留给 P4

### 前端编排规则（定稿数值）

- 节点入场：opacity + scale 弹入 **280ms**，stagger **45ms**
- 边入场：`strokeDashoffset` 画线 **480ms**（必须比节点慢），随后若带 `flow` 立即开始流动
- `demoPath` 播放：按路径顺序，节点到达 → 高亮，出边流动接力，间隔固定节奏（600ms/跳），循环或单次由工具条控制
- 自环迁移标签渲染在环顶上方（X6 默认自环 label 位置 P0 验证，见 020 §10 第 12 条）

## 改造清单

### 后端 divine-server

1. `app/tools/adapters/render_graph.py`：新 adapter，套用 `generate_chart.py` 模式。接收完整 GraphIR → 按 §校验清单强校验（失败结构化报错，不降级）→ 完整 IR 作为 tool 结果。`category = "diagrams"`。
2. 工具描述分流话术：13 个 kind 各给一句典型问法 + 封闭枚举清单 + 分流规则（Mermaid / ECharts / render_graph / 拒绝），对齐 `generate_chart` 风格。
3. （仅真流式形态，P0 通过后）`core/sse.py` 增量管道：tool_call_chunks 消费 + 流式 JSON 解析，仅对 render_graph 启用。

### 前端 divine-app

1. 依赖：`@antv/x6@^3` + `@antv/layout`，均动态 import，首次出现 GraphBlock 时才加载。**不引入 elkjs、不引入 `@antv/x6-react-shape`**。
2. 新建 `GraphBlock/`（样式类名加 `gb-` 前缀或 CSS Modules——项目有过全局 `.diff-view` 冲突事故）：
   - `GraphIR.ts`：类型 + 白名单校验，拒绝 `__proto__`、`on*`、任意 attrs 注入
   - `presets.ts`：ScenarioPreset 常量表 + Resolver（布局引擎 / 形态 / 交互等级 / 动效 / 上限）
   - `graphTones.ts`：语义色常量（light/dark 双档，dark info = #61A7D0），**不复用 chartOptions.ts**
   - `nodes.ts`：形态族注册——通用 12 形态 + 富节点（dagNode / dpNode / stateNode / statePseudo / orgNode / mapRoot / mapBranch / mapLeaf / conceptNode），全部纯 SVG markup（body → tint → label 三层 + 图标内联 path），换形态不换配色逻辑
   - `GraphBlock.tsx`：消息内容器；**新增消息走增量事件 + 动效；历史消息走完整 IR 直渲染（零动画）**
   - `GraphRenderer.ts`：流式阶段占位坐标（规则网格，只增不减）→ `done` 后 `@antv/layout` 终局布局一次 + `animate` 平滑过渡（600ms）；`router: 'orth'`、`connector: 'rounded'`；双层边：静态底线 + 流动层（`connection: true` 未实测，退路手动同步 `flow.attr('d', line.attr('d'))`）
   - `RenderScheduler.ts` / `AnimationManager.ts`：80ms 批处理 + 动画池（≤20，实测后修正）
   - 视口外暂停：IntersectionObserver 挂动画与 antline（无限循环动画在长会话持续吃 CPU）
3. 消息侧接线：`MessageHelpers` 增 `graphIRFromResult()`（对齐 `chartOptionFromResult`），`ToolStatusCard` 增图标。
4. 工具条：**常驻**（opacity .72→1）。播放/暂停演示（demoPath）、重播入场、流动开关、导出 PNG/SVG。按钮按 `Preset.capabilities` 渲染（L0 场景不出现流动开关）。

## 性能与安全要点

- 流式阶段绝不调布局引擎（占位坐标），`done` 后一次 `@antv/layout`
- 动画仅 transform / opacity / dashoffset；并发动画池上限，超限置终态；视口外暂停
- IR 白名单校验，防 LLM 注入任意 SVG attrs 与外链资源（图标仅白名单枚举）
- 历史回放零动画，长列表滚动性能与普通静态图一致
- P0 实测帧率拐点 → 修正各场景节点上限与动画池大小（上限表后端镜像）
- `graphTones.ts` 独立色值源；导出链路验证 toSVG 对自定义 markup 的完整性

## 分阶段落地

| 阶段 | 内容 | 验收 |
| --- | --- | --- |
| **P0** 验证 | X6 3.x 验证 demo：`animate` API 形状、边第二条 path 复用连接数据（`connection:true` 未实测）、`@antv/layout` 各引擎 WKWebView 耗时、帧率拐点、toSVG 对自定义 markup 输出、foreignObject 反证（仅当考虑 react-shape）、**`run.messages` 能否拿到 tool_call_chunks 参数增量（定"生长"形态，见决策 13）**。清单见 020 §10（含增补第 16 条），结论写回 020 | 布局引擎与动画 API 定稿，节点上限/动画池按实测定；生长形态（回放式/真流式）定稿 |
| **P1** 骨架 | GraphIR + 白名单校验 + `render_graph` 工具 + 增量事件流 + Preset Resolver + 渲染器 + **3 个场景**（flow / dag / state） | Agent 输出 IR，聊天内出现三种正确布局的图；错误 kind 被结构化拒绝；历史回放直渲染 |
| **P2** 动效 | 入场动效（280/480/45）+ antline/pulse + demoPath 播放 + 常驻工具条（按 capabilities）+ 导出 PNG/SVG | 生成过程逐节点生长；流动可开关；导出可嵌入 PDF |
| **P2.5** 扩列 | 剩余 10 个场景（dataflow / org / mindmap / topology / er / swimlane / concept / class / fishbone / timeline） | 每个场景**表里加一行即生效，不改 schema 不改后端**（本条即验收） |
| **P3** 打磨 | hover 关联高亮 + 详情面板 + minimap + 折叠展开 + 视口外暂停 | 大图浏览流畅；长会话 CPU 无异常占用 |
| **P4** 观察 | particles 粒子模式；CoT 面板与图生长同步；kind 自动推断 | 视 P2 效果决定 |

P0–P2 达成"美观 + 交互动画 + 生长式呈现"；P2.5 场景全覆盖；P3 补全浏览与交付能力；P4 择机。

## 后续演进：架构图三增强（调研结论存档，不进 P0–P3）

> 现状：`topology`（cluster 分层）+ `dag` + `concept` + `er` + `swimlane` 已能覆盖服务拓扑类架构图的
> 大部分诉求，但离"正经的架构图"（C4 / 部署图 / 分层架构）还差三个能力。以下结论来自 2026-09-08 对
> [Archify Proof Lab](https://tt-a1i.github.io/archify/gallery.html)（MIT 开源，IR-first 同路线项目）
> `web-app.architecture` 样本的调研，存档备查，触发真实需求时直接取用。

1. **嵌套分组不用递归——重叠绘制**。IR 的 `groups` 保持平面列表（`members` 不嵌套 group），渲染器按
   包围盒面积**从大到小排序绘制**即出嵌套视觉（region 大框内套 security-group 小框）。校验只查
   `members` 指向已声明节点。比递归 groups 更轻，schema 零改动。
2. **架构节点三信息位**。`topology` 富节点化时补：`sublabel`（技术栈/端口，如 `FastAPI :8000`）+
   `tag`（可选徽标，如 `OAI protected`）+ `type` 六类架构角色封闭枚举
   （`external | security | cloud | backend | database | messagebus`，决定圆内图标）。
   复用 dag-node 的三层 markup，配色逻辑不变。
3. **`cards` 图例通道**。Preset 声明线型/色点语义（实线=同步调用 / 虚线=异步消息 / 点线=数据复制），
   渲染器在画布角落自动生成图例区，导出随 SVG 带走。IR 侧仅允许引用 Preset 已声明的语义名。

**立场（不跟 Archify 的部分）**：**禁绝对坐标**。Archify 的 IR 含 `pos` / `size` / `via` 折线 /
`fromSide` / `toSide`——手工编排的坐标制换来像素级排版，但 LLM 产坐标不可靠（重叠、出界、换主题
溢出），与本项目「禁色值、禁形态」是同一条原则。布局继续交给 `@antv/layout`；边界归属类布局意图
用 boundary 约束布局（组内成员就近）近似。

**落地路径**（触发时执行）：不新增 `arch` kind——架构图 = `topology` 换一行 Preset + 上述三增强；
C4 Context / Container 图 = topology 再换 Preset 参数。预估规模：schema 加 2 个可选字段 +
渲染器 2 个功能块（重叠 boundary、legend 区），不触碰布局引擎。
