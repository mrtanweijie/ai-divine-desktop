# 020 · X6 多场景图形渲染 UI 设计方案（2026-09-08）

> 配套可视化页：`docs/design/020-x6-multi-scenario-20260908.html`（13 个场景真实渲染样板，明暗可切、可 hover / 流动 / 重播）
> 上游文档：`docs/plan/004-interactive-flowchart-20260908.md`（执行计划）

---

## 0. 一句话结论

X6 的真实定位是**通用图渲染机**：只要输入是「节点 + 边 + 语义」，就能渲染流程图、DAG、状态机、组织架构、思维导图、拓扑、ER、泳道、知识图谱、类图、鱼骨、时间线。

**核心架构决策：把「画什么」和「怎么画」彻底拆开。**

- Agent 只输出 `kind`（场景名）+ 拓扑 + 语义意图
- 布局引擎、节点形态、连线路由、交互等级、动效策略全部收敛到前端一张 **ScenarioPreset 常量表**
- **加一个新场景 = 表里加一行**：不改 schema、不改后端、不改渲染器

---

## 1. 设计动机

把场景写进 schema、让 Agent 指定视觉形态，是图渲染链路最容易腐化的两条路：

| 反模式 | 后果 | 本方案的解法 |
| --- | --- | --- |
| **场景固化在 schema 里**（IR 写死 `direction` / `shape` / `flow`） | 每加一个场景都要改 schema + 后端校验 + 工具描述；13 个场景 = 改 13 次 | IR 只留 `kind`，形态全部进 Preset 表；加场景 = 加一行 |
| **Agent 决定视觉**（LLM 直接指定 `shape` / 色值） | 视觉一致性取决于模型心情；换主题 / 换形态要重新调 prompt | Agent 只给 `role` 语义，形态由 Preset 映射 |
| **单一布局引擎包打天下** | 13 类场景近半用不上其强约束能力，白付体积与复杂度 | `@antv/layout` 按 Preset 映射 + fishbone / timeline 两个自定义布局 |
| **规模上限一刀切** | ER 图 24 个实体已经糊了，组织架构 150 还很空 | 上限按场景分档（§4） |

## 2. 架构

```
后端 divine-server
  Agent (LangGraph)
    └─ 工具 render_graph            ← 唯一的图形渲染工具
         ├─ 入参：GraphIR（JSON Schema 强校验，kind 是唯一场景字段）
         └─ 出参：增量事件流（JSON Lines），走现有 SSE tool 通道
               add_node / add_edge / add_group / set_meta / done

前端 divine-app · src/pages/chat/components/GraphBlock/
  GraphIR.ts            类型 + 白名单校验（IR 来自 LLM，按不可信输入处理）
  presets/
    index.ts            ★ ScenarioPreset 表：kind → 布局/形态/交互/动效
    layout.ts           布局引擎映射（@antv/layout）
  shapes/
    registry.ts         节点形态注册表（纯 SVG markup，可被 toSVG 导出）
    edges.ts            边族：orth | curve | straight | selfLoop
  GraphRenderer.ts      ★ 场景无关：IR × Preset → X6 渲染
  RenderScheduler.ts    80ms 批处理
  AnimationManager.ts   动画池 + 视口外暂停（IntersectionObserver）
  GraphToolbar.tsx      按 Preset.capabilities 渲染按钮
  GraphInspector.tsx    节点/边详情面板
```

### Preset Resolver 解析产物

```ts
kind ──► PRESETS[kind] ──► {
  layout:  { engine, opts },     // dagre | compactBox | mindmap | force | custom
  shapes:  NodeFamily,           // 节点形态族
  edges:   EdgeFamily,           // 边族 + 路由 + marker
  groups:  GroupFamily | null,   // lane | cluster | combo
  level:   'L0' | 'L1' | 'L2',   // 交互等级 → 决定加载哪些 X6 插件
  motion:  MotionSpec,           // 入场 / 流动 / 播放
  limit:   { nodes, edges },
  view:    'fit' | 'center' | 'scroll',
  capabilities: ['export','flow','play','fold','minimap']
}
```

**关键约束**：`kind` 必须是封闭枚举。未知 kind → 后端校验拒绝 + 结构化报错让 Agent 自纠，**不要静默 fallback 到 `flow`**——静默降级会让错误形态被当成正确结果固化下来。

---

## 3. GraphIR 规范

```jsonc
{
  "kind": "flow",                        // 唯一场景字段，封闭枚举
  "meta": { "title": "订单支付链路", "summary": "…" },
  "nodes": [
    { "id": "start", "label": "提交订单",
      "role": "start",                   // start|end|process|decision|data|entity|state|milestone
      "tone": "info",                    // success|warning|error|info|neutral（禁止色值）
      "state": "running",                // ★ 场景特有可选字段，见 §5.5（dag/dataflow 生效）
      "icon": "flask",                   // ★ 场景特有可选字段，封闭枚举，禁止 URL
      "pseudo": "initial",               // ★ state 场景：initial|final|choice（伪状态，无 label）
      "active": true,                    // ★ state 场景：当前激活态，全图最多 1 个
      "role": "member",                  // ★ org 场景：职位/编制描述（org-node 第二行）
      "count": 4,                        // ★ org 场景：直属子节点数（画折叠角标）
      "type": "module",                  // ★ concept 场景：module|tech|data|process|concept（圆内图标）
      "lane": "order",                   // 泳道归属（kind=swimlane 时必填）
      "parent": "g1",                    // 层次归属（org / mindmap 可选）
      "note": "点击节点查看的详情",
      "badge": "P0" }
  ],
  "edges": [
    { "id": "e1", "source": "start", "target": "stock",
      "label": "校验",
      "kind": "flow",                    // flow|dep|transit|inherit|assoc|contain
      "tone": "info",
      "style": "solid",                  // solid|dashed
      "flow": { "mode": "antline", "speed": 1 } }
  ],
  "groups": [
    { "id": "g1", "label": "接入层", "type": "cluster", "members": ["cdn","waf","gw"] }
  ],
  "demoPath": ["start", "stock", "pay"]
}
```

### 后端强校验清单

1. `kind` ∈ 13 项枚举，未知即拒绝
2. `role` ∈ 枚举，未知即拒绝（**不能让 LLM 借 role 名注入形态**）
2b. `icon` ∈ 封闭枚举（8 个任务图标 / 6 个加工类型），**禁止任何 URL**
2c. `pseudo` ∈ `initial|final|choice`；`active=true` 全图**最多 1 个**（多个即拒绝）；`type` ∈ 5 类封闭枚举
2d. **IR 中禁止出现 `bc`（分支色索引）**——分支色由前端按分支顺序自动分配，让 LLM 选色是灾难
2e. 边 `label` 允许 `事件[守卫]` 格式（state 场景），守卫内容仍需做长度与转义校验
3. `tone` ∈ 5 项枚举，禁止任何色值字符串
4. `lane` / `parent` / `group.members` 必须指向已声明 id
5. `flow` 仅 `mode: antline|pulse`、`speed: 0.5|1|2`
6. **禁止任何 `x/y/w/h` 坐标字段**
7. `nodes.length` ≤ `PRESETS[kind].limit.nodes`（Preset 上限需后端镜像一份常量）
8. 拒绝 `__proto__`、`on*`、任意 attrs 注入（继承 004）

---

## 4. ScenarioPreset 总表

| kind | 场景 | 布局引擎 | 节点族 | 边族 | 容器 | Lv | 动效 | 上限 | 视口 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `flow` | 业务流程 / 决策流 | dagre LR | pill / rounded / diamond | orth + 实心箭头 | — | L2 | 入场 + 流动 + 播放 | 80 | fit |
| `dag` | 任务编排 DAG | dagre TB | **dag-node** 188×40（图标 + 标题 + 状态徽标） | orth + 箭头 + ports TB | cluster | L2 | 入场 + 运行态入边流动 | 120 | fit |
| `dataflow` | 数据加工 DAG | dagre LR | **dp-node** 212×48（类型图标瓦片 + 标题 + 状态） | orth + 箭头 + ports LR | — | L2 | 入场 + 运行态入边流动 | 80 | fit |
| `state` | 状态机 | dagre LR | **state-node** 152×44（tone 竖条 + 时限徽标 + active 脉冲）+ 伪状态 initial/final | curve + 箭头 + 自环 + 事件[守卫]标签 | — | L2 | 入场 + 迁移播放 + active 脉冲 | 40 | center |
| `org` | 组织架构 | compactBox TB | **org-node** 176×56（头像首字 + 姓名/职位 + 折叠角标） | orth 直角折线 | — | L1 | 逐层展开 | 150 | fit |
| `mindmap` | 思维导图 | mindmap LR | **map 三级形态**（root / branch / leaf），分支色走连线与竖条 | curve 锥形（分支色） | — | L1 | 逐层展开 + 折叠 | 120 | fit |
| `topology` | 系统 / 网络拓扑 | dagre TB + cluster | rounded + icon | orth / straight | cluster | L1 | 入场 + 心跳脉冲 | 100 | fit |
| `er` | 实体关系 | force（低斥力） | section 三段式 | straight + 基数标注 | — | L0 | 入场 | 24 | fit |
| `swimlane` | 跨职能流程 | dagre LR × lane | rounded | orth 跨 lane | lane | L2 | 入场 + 流动 | 60 | scroll |
| `concept` | 知识图谱 | force | **concept-node**（圆按度定尺寸 36–56 + 圆内类型图标 + 圆外名称） | straight 无箭头 · 线型表关系（实线包含 / 虚线依赖 / 点线引用） | — | L1 | 力导收敛 | 80 | fit |
| `class` | UML 类图 | dagre LR | section 三段式 | orth + 空心菱形 | — | L0 | 入场 | 20 | fit |
| `fishbone` | 鱼骨 / 因果 | 自定义脊柱 + 肋 | rib 标签 | straight 斜肋 | — | L0 | 按肋分组入场 | 40 | fit |
| `timeline` | 时间线 / 里程碑 | 自定义轴 + 交错 | rounded + 日期副标 | axis 短桩 | — | L0 | 从左到右入场 | 30 | fit |

### 布局引擎选型：用 `@antv/layout`，不用 elkjs

004 定 elkjs 时只考虑单一流程图。多场景下一套 `@antv/layout` 覆盖 9/13 场景（dagre / antv-dagre / force / compactBox / mindmap），**省掉 elkjs 的体积与 wasm 加载成本**。仅当 swimlane 出现多层嵌套约束时再单独评估 elkjs。

`fishbone` / `timeline` 无通用算法，各写一个 60 行自定义布局函数即可（参考设计页里的 `fishboneLayout` / `timelineLayout`）。

---

## 5. 通用设计层（跨场景同源）

场景可以千变万化，这四层必须全局一致——否则 13 个场景就是 13 套视觉。

### 5.1 节点形态族（按 `role` 映射，Preset 可覆盖）

| role | 形态 | 尺寸 w×h |
| --- | --- | --- |
| `start` / `end` | 胶囊 pill，rx = h/2 | 112 × 38 |
| `process` | 圆角矩形，rx 8 | 136 × 46 |
| `decision` | 菱形 | 124 × 58 |
| `data` | 圆柱（数据库） | 118 × 58 |
| `state` | 圆角状态框 + 伪状态（initial 实心圆 / final 双圆 / choice 菱形） | 152 × 44 · 30 × 30 |
| `entity` / `class` | 三段式（标题 / 属性 / 方法） | 176 × 自适应 |
| `milestone` | 圆角矩形 + 日期副标 | 132 × 52 |

**统一三层 markup**：`body`（底 + 描边）→ `tint`（语义微染 10%）→ `label`（文本）。**换形态不换配色逻辑。**

**禁用 HTML 节点**——X6 的 HTML 节点无法被 `toSVG/toPNG` 导出，而导出是硬需求。全部走纯 SVG markup。

### 5.2 边族（静态底线 + 流动层双层叠加）

| 边族 | 路由 | marker | 场景 |
| --- | --- | --- | --- |
| `flow` | orth 圆角折线 | 实心箭头 | flow / dag / swimlane |
| `transit` | curve 贝塞尔（含自环） | 实心箭头 | state |
| `dep` | orth | 空心箭头 | dag / class |
| `assoc` | straight | 无 | concept |
| `inherit` | orth | 空心三角 | class |
| `contain` | 直角折线 | 无 | org / mindmap |

底线讲拓扑（中性色，常驻），流动层讲动态（tone 色，可关）。**职责分离后，关动画 / 历史回放 / 导出时图都完整可读——这条不能因为 X6 API 不通就砍掉。**

线宽 1.25（选中 1.75）；流动层 `dasharray 6 7`，speed 0.5 / 1 / 2 → 2.2s / 1.1s / 0.58s。

### 5.3 语义 tone（定稿）

- **`neutral` 与 `info` 视觉等同**（中性灰描边）
- 只有 `success` / `warning` / `error` 上语义色，底色仅 10% 微染
- `info` 的蓝**只出现在流动线上**

这样默认态是干净的黑白图，只有异常/成功节点跳出来——语义反而更强，也不会把极简黑白体系染成"彩色流程图"。

**dark 档 `info = #61A7D0`**，不复用图表色 `#036EAD`（暗底 1px 描边不可见）。**单独建 `graphTones.ts`，不要复用 `chartOptions.ts` 常量**——避免图表改色误伤图形。

### 5.4 容器族（group）

- **lane**：横向泳道带，标签左置，底色 1.6% 中性
- **cluster**：虚线圆角包围盒，标签左上，底色 2.2%
- **combo**：可折叠分组（org / mindmap），首期用「折叠角标」替代真 combo

---

## 5.5 DAG 自定义节点（对照 X6 showcase `dag` / `dataProcessingDag`）

通用矩形节点在 DAG 场景信息密度太低——看不出「跑到哪一步」「这步是干嘛的」。X6 官方这两个 showcase 用**自定义富节点**解决：节点内嵌**类型图标 + 标题 + 状态徽标**。适配到 Divine 设计体系后的规格：

### 形态 A：`dag-node` · 任务编排型（对应 X6 `dag` 的 `AlgoNode`）

```
┌────────────────────────────────────────────┐  ▲
│ ①      ②                              ③   │  │ 40
│ ⟦⟧     单元测试                       ●    │  ▼
└────────────────────────────────────────────┘
   ▲      ▲                             ▲
 16px   36px                        距右 16px
├──────────────── 188 ────────────────────────┤
```

| 槽位 | 内容 | 规格 |
| --- | --- | --- |
| ① 类型图标 | 8 个内联 path：`code / box / check / flask / stack / layers / upload / gear` | 16×16，距左 16px，`stroke-width 1.5`，**不吃 tone 色**（保持中性，避免整张图变花） |
| ② 标题 | `node.label` | 12.5px，距左 36px，超长省略号截断 |
| ③ 状态徽标 | 4 态，见下 | 14×14，距右 16px |
| ④ 端口 | `ports: 'tb'` | r 3.4，TB 布局时上/下各一 |
| 容器 | `rect rx 6` | 188 × 40 |

### 形态 B：`dp-node` · 数据加工型（对应 X6 `dataProcessingDag`）

| 槽位 | 内容 | 规格 |
| --- | --- | --- |
| ① 类型图标瓦片 | 6 类：`INPUT / FILTER / JOIN / UNION / AGG / OUTPUT` | 图标 24×24 置于 28×28 圆角块（rx 7）内，块底色 `surface-2` |
| ② 标题 | `node.label` | 12.5px，距左 62px |
| ③ 状态徽标 | 同形态 A | 距右 18px |
| ④ 端口 | `ports: 'lr'` | 左 in / 右 out |
| 容器 | `rect rx 8` | 212 × 48 |

### 状态徽标 4 态

| state | 视觉 | tone 映射 |
| --- | --- | --- |
| `pending` 待执行 | 空心圆环 r 3.6 | neutral |
| `running` 进行中 | 实心点 + 1.5s 脉冲（opacity 1↔.32，scale 1↔.68） | info |
| `success` 已完成 | 对勾 | success |
| `failed` 失败 | 叉 | error |

**联动规则**：目标节点 `state = running` 时，其**入边**自动开 antline（与 X6 示例的 `running-line` dash 动画同效果，但走我们既有的双层边机制，可关可导）。

### 与 X6 原版的三处取舍（必须改）

| X6 原版 | 我们的决定 | 理由 |
| --- | --- | --- |
| `@antv/x6-react-shape` 注册 React 组件节点 | **改用等价的纯 SVG markup** | React 节点渲染进 `foreignObject`：① WKWebView 下 `toPNG` 极易失败 ② 样式是外联 CSS，导出即丢。**与「导出 PNG/SVG 是硬需求」直接冲突**。通用设计层的「禁用 HTML 节点」原则继续有效 |
| 图标用 `gw.alipayobjects.com` 外链图 | **全部内联 path，禁止 URL** | 本地优先 + 隐私可控；外链既泄隐私，导出后又失效 |
| 「+ 添加下游节点」下拉菜单、节点「更多操作」菜单、antd Tooltip/Dropdown | **砍掉** | 都是 L3 画布编辑器能力，首期不做（见 §6） |

### IR 侧的字段约定

- **`state` 映射到 tone，不引入第二套语义色**：running→info、success→success、failed→error、pending→neutral。通用设计层定稿的「neutral≡info 不上色」原则不变。
- **`state` / `icon` 是「场景特有可选字段」**——Preset 可声明自己支持哪些额外字段，这是 Preset 架构的应有之义。`flow` / `state` 场景也可逐步开放 `state`，其余场景忽略。
- **`icon` 必须白名单校验**，防 LLM 注入外链资源。
- 保留 `tone` 用于非状态语义（如「这个节点是重点」）。`state` 与 `tone` 同时出现时，**`state` 优先**决定徽标表现。

---

## 5.6 状态机 / 组织树 / 思维导图 / 知识图谱 · 四类富节点

这四个场景的通用节点最撑不住：状态机看不出初态终态、组织树没有身份信息、思维导图分不清层级、知识图谱既挤又无类型。各用一个富节点形态解决一个具体的信息缺口（设计页 §4.2 有带尺寸标注的解剖图）。

### 形态 C：`state-node` + 伪状态（state）

| 槽位 | 规格 |
| --- | --- |
| 容器 | UML 圆角状态框 152×44，rx 10 |
| ① tone 竖条 | 3.5px 圆角竖条，距左 1.5px——状态类型一眼可辨，底色仅 8% 微染 |
| ② 状态名 | 12.5px，距左 18px，超长省略号 |
| ③ 时限徽标 | `node.badge`（如 `30m`），右对齐 10.5px |
| ④ active 态 | 外扩 4px 描边环 + 2.2s 脉冲，**全图最多 1 个** |
| 伪状态 | `initial` 实心圆 r7 / `final` 同心圆（外环 r9.5 + 内实心 r4.2）/ `choice` 菱形 22×22 |

**UML 语义修正**：圆形是伪状态专用，普通状态必须是圆角矩形——020 初版全用 circle 是语义错误，已废弃。

**迁移标签**：支持 UML 标准写法 `事件[守卫条件]`（如 `超时 [未支付]`），守卫段渲染为等宽淡色 tspan。**自环迁移标签渲染在环顶上方**——状态机的超时迁移是典型自环，此前自环标签会被静默丢弃。

### 形态 D：`org-node`（org）

| 槽位 | 规格 |
| --- | --- |
| 容器 | 176×56，rx 10 |
| ① 头像 | 36×36 圆角 10，`surface-2` 底 + 描边，内放**姓名/部门首字**（13px/600） |
| ② 姓名 | 12.5px/500 |
| ③ 职位/编制 | `node.role`，10.5px，text-3 |
| ④ 折叠角标 | `node.count`（直属子节点数），r9.5 圆挂下边缘中点 |

**头像用首字而非图片**：外链头像泄隐私 + 导出后失效，与两条硬约束冲突。首字是零依赖、导出安全的身份表达。

### 形态 E：`map` 三级形态（mindmap）

| 层级 | 形态 | 规格 |
| --- | --- | --- |
| root | 圆角 12，**描边加粗 2px**，标题 13.5px/600 | 140 × 46 |
| branch | 圆角 8，左侧 3.5px **分支色竖条** | 118 × 34 |
| leaf | 退化为「文字 + 2px 分支色底线」——经典思维导图的「文字挂线上」 | 96 × 26 |

**分支色只染结构性元素（连线 + 竖条 + 底线），不染节点本体**——分支识别力不减，黑白基底不动。分支色 5 档（`--bc-0..4`）取自图表定性色板：light `#F3962F #036EAD #DD656D #506AAA #728DC1`，dark `#FACC8F #61A7D0 #E17692 #F3962F #728DC1`。**`bc` 由前端按分支顺序自动分配，IR 里不写**——让 LLM 选颜色是灾难。

### 形态 F：`concept-node`（concept）

| 通道 | 承载信息 | 规格 |
| --- | --- | --- |
| 圆直径 | 重要性（度数） | 36–56px，hub（≥52px）名称加粗提亮；归一化画幅按节点数量放大（fw/fh 随 n 调整），保证圆间距 ≥ 40px |
| 圆内图标 | 实体类型 | 5 类封闭枚举 `module / tech / data / process / concept`，内联 path |
| 圆外文字 | 名称 | **外置**到圆下方 10.5px——圆内不写字 |

**边线型表关系**：实线=包含/组成、虚线=依赖、点线=引用/派生。关系网的关系类型必须可读，否则只是「一堆连线」。

### 四个设计判断（取舍，非照抄）

1. **分支色不上节点本体**——保住极简黑白体系（同 §5.3 的 tone 收敛逻辑）
2. **知识图谱圆内不写字**——「LangGraph」塞 78px 圆里字被压到 10px 还换行；圆点 + 外置标签是图谱工具的通行做法
3. **状态机补伪状态**——初态/终态/choice 是 UML 语义，不能省
4. **组织树头像用首字**——外链图片与「本地优先 + 可导出」正面冲突

### IR 侧新增（均为场景特有可选字段）

| kind | 字段 | 约束 |
| --- | --- | --- |
| `state` | `node.pseudo` | ∈ `initial\|final\|choice`；`active` 全图最多 1 个 |
| `state` | 边 `label` | 支持 `事件[守卫]`，守卫由前端解析渲染 |
| `org` | `node.role` / `node.count` | count 为整数，缺失则不画角标 |
| `mindmap` | `bc`（**前端分配**） | 整数 0–4，**不出现在 IR 中** |
| `concept` | `node.type` | 5 类封闭枚举；边 `style` ∈ `solid\|dashed\|dotted` |

---

## 6. 交互分级 L0–L3

等级由 Preset 决定，直接决定**加载哪些 X6 插件**——避免一张静态 ER 图背上 Selection + Transform + History 一整套。

| Lv | 能力 | 加载的插件 | 适用 kind |
| --- | --- | --- | --- |
| **L0** | 渲染 · hover tooltip · 点击详情 · 导出 | 核心包 | er · class · fishbone · timeline |
| **L1** | L0 + 缩放平移 · hover 关联高亮 · 折叠展开 · minimap | Scroller · Minimap | org · mindmap · topology · concept |
| **L2** | L1 + 数据流动画 · demoPath 播放 · 工具条 | Scroller · Minimap · Selection | flow · dag · state · swimlane |
| **L3** | L2 + 拖拽建边 · 编辑标签 · 撤销重做 · 吸附对齐 | + Transform · History · Snapline · Clipboard · Keyboard · Stencil | **首期不做** |

**为什么 L3 不做**：拖拽编辑意味着「AI 生成的图是草稿，用户要自己改」，与产品定位（AI 直接产出可用结果）冲突，且会引入持久化、冲突合并、撤销栈一整套问题。**X6 支持 ≠ 该做。** 将来若要，应是独立的「画布页」而非聊天消息内组件。

---

## 7. 动效策略矩阵

定稿节奏（节点 280ms / 边 480ms / stagger 45ms），按场景族微调。所有动画只碰 `transform` / `opacity` / `stroke-dashoffset`。

| 场景族 | 入场 | 持续动效 | 播放编排 | 历史回放 |
| --- | --- | --- | --- | --- |
| 线性流程（flow / dag / swimlane） | 按拓扑序 pop 弹入，stagger 45ms | antline 双向流动（仅标记 flow 的边） | demoPath 600ms/跳 | 直渲染终态，工具条手动播放 |
| 状态迁移（state） | 按层级 pop | 无（静态更清晰） | 迁移路径逐段点亮 | 同上 |
| 层次结构（org / mindmap） | 自上而下逐层展开，stagger 35ms | 无 | 无播放；折叠展开 220ms 位移 | 直渲染，保留折叠状态 |
| 自由图（concept / er） | 力导收敛 600ms 或 pop | 心跳脉冲（topology） | 无 | 直渲染（**力导结果需固化坐标**） |
| 静态版式（class / fishbone / timeline） | 按版式顺序 pop | 无 | 无 | 直渲染 |

### 性能硬约束（通用规则）

1. 动画池上限 20，超限直接置终态
1b. **会话内同时开启流动的块上限 3 个，超出自动关闭最早的**（流动是无限循环动画，长会话持续吃 CPU）
2. **视口外暂停**——antline 是无限循环动画，长会话里滚出视口不暂停会持续吃 CPU，用 `IntersectionObserver` 统一控制
3. 尊重 `prefers-reduced-motion`
4. 力导布局结果在 `done` 后**固化坐标**，历史回放不再跑力导

---

## 8. 能力边界：什么不进这条链路

方案 004 的收敛条件写的是「X6 稳定后评估把 Mermaid 迁过来，避免三套体系并行」。方向对，但要写清边界，否则多场景会无限扩张。

| 图形类型 | 归属 | 理由 |
| --- | --- | --- |
| 本文 13 类「节点 + 边」图 | `render_graph` | X6 原生强项 |
| 时序图 sequence | Mermaid | 语法成熟、LLM 生成准确率高；X6 需自建生命线版式，投入产出比差 |
| 甘特图 gantt | Mermaid | 本质是时间刻度条，非拓扑图 |
| 类图 classDiagram | Mermaid（默认）/ X6（需交互时） | **双轨**：快速看走 Mermaid，要点击详情走 X6 |
| 统计图表（折线/柱/饼/K线） | `generate_chart` | ECharts 已有完整体系与配色规范 |
| 地图 / 平面图 / 电路图 | 不做 | 非「节点 + 边」抽象 |
| 在线编辑画布（拖拽编排） | 不做 | L3，见 §6 |

### 分流话术（写进工具描述，对齐 `generate_chart` 风格）

> 需要**交互、数据流向动画、生长式呈现**的节点关系图 → `render_graph`；仅需静态展示的流程图 / 时序图 / 甘特图 → Mermaid 代码块；数据图表 → `generate_chart`。

工具描述里同时列出 13 个 `kind` 及**典型问法**（见设计页每张卡片底部），让 Agent 一次选对，减少自纠轮次。

---

## 9. 分期落地

| 阶段 | 内容 | 验收 |
| --- | --- | --- |
| **P0** 验证 | 50 行 X6 3.x demo：① `animate` API 真实形状 ② 边的第二条 path 能否复用连接数据（`connection:true` **未实测**）③ `@antv/layout` 各引擎在 WKWebView 的真实耗时 ④ 帧率拐点实测 ⑤ `toSVG` 对自定义 markup 的输出 | 布局引擎选型定稿、动画 API 定稿、帧率拐点写回本文档 |
| **P1** 骨架 | GraphIR + 白名单校验 + `render_graph` 工具 + 增量事件流 + Preset Resolver + 渲染器 + **3 个场景**（flow / dag / state） | Agent 输出 IR，聊天内出现三种正确布局的图；历史回放直渲染 |
| **P2** 动效 | 入场动效 + antline/pulse + demoPath 播放 + 工具条（按 `Preset.capabilities` 渲染）+ 导出 PNG/SVG | 生成过程逐节点生长；流动可开关；导出可嵌入 PDF |
| **P2.5** 扩列 | 剩余 10 个场景 | 每个场景**表里加一行即生效，不改 schema 不改后端**（这条本身就是验收） |
| **P3** 打磨 | hover 关联高亮 + 详情面板 + minimap + 折叠展开 + 视口外暂停 | 大图浏览流畅；长会话 CPU 无异常占用 |
| **P4** 观察 | particles 粒子模式；CoT 思考面板与图生长同步；kind 自动推断 | 视 P2 效果决定 |

---

## 10. P0 验收清单（16 条，结论写回本文档）

1. `graph.animate` 的真实 API 形状（是 `node.animate` 还是 `transition`？回调如何拿？）
2. **边的第二条 path 能否拿到连接数据**（`connection: true` 是二手结论，未实测）。退路：手动同步 `flow.attr('d', line.attr('d'))`
3. `attrs` 里能否直接用 CSS 变量实现主题切换，还是必须在 JS 层读主题再注入色值
4. `@antv/layout` 各引擎在 WKWebView 上的真实耗时（dagre 100 节点 / force 80 节点各多少 ms）
5. 帧率拐点：SVG 节点数在多少时掉到 50fps 以下 → 定各场景 `limit`
6. 动画池上限：并发多少条 antline 开始掉帧 → 定 `AnimationManager` 池大小
7. `toSVG` 对自定义 markup 的输出是否完整（尤其 `marker` 与 `foreignObject`）
8. `toPNG` 是否需要剔除流动层（避免导出的静态图里有半截虚线）
9. 视口外暂停：`IntersectionObserver` 在虚拟滚动的消息列表里是否可靠触发
10. WKWebView 下 `stroke-dashoffset` 动画的合成层表现（是否会触发全图重绘）
11. **若考虑 `@antv/x6-react-shape`**：先实测 `foreignObject` 在 WKWebView 下的 `toPNG` 是否产出内容、外联 CSS 是否丢失。**实测通过才可能推翻「纯 SVG markup」的决定**；未通过则结论写死
12. **自环迁移标签**：X6 `edge` 默认自环 label 位置是否可用；若不可用则按本文 §5.6 方案手动定位到环顶上方
13. **`active` 脉冲环**：外扩描边环 + scale 动画在缩放（zoom < 0.5）下的渲染开销；必要时降级为静态高亮描边
14. **`textWrap.ellipsis` 在中文下是否按字符截断**——决定是否需要前端自算文本宽度
15. **主题切换**：不重建 graph、只更新 attrs 是否可行（避免滚动位置丢失）
16. **真流式可行性**：`_stream_agent_run` 的 `run.messages`（`app/agent/core/sse.py`）能否稳定拿到 tool_call 参数的 token 级增量（`tool_call_chunks`）。可行 → 真流式生长（token 流 + 流式 JSON 解析提前下发节点）；不可行 → 回放式生长（完整 IR 到达后前端节流播放，见 plan 004 决策 13）

---

## 11. 附录：详细视觉规范

> 本附录是前端落地所需的**完整视觉规格**：色值、字号、状态、容器尺寸、动效降级与 X6 初始化代码。
> 正文的 §5 / §7 只定原则，本附录给到可照抄的实现精度。
### 11.1 Token

**语义 tone 双主题全表**：

| tone | dark | light | 节点描边 | 节点底染 |
| --- | --- | --- | --- | --- |
| `neutral` | `#8A94A6` | `#7A8494` | `--color-border-strong` | 0% |
| `info` | `#61A7D0` | `#036EAD` | `--color-border-strong` | 0% |
| `success` | `#3FB98A` | `#2F9E6E` | tone 色 · 1px | 8% |
| `warning` | `#F3962F` | `#C77F1E` | tone 色 · 1px | 8% |
| `error` | `#E07A82` | `#C9525B` | tone 色 · 1px | 8% |

- dark `info = #61A7D0`（图表 `#036EAD` 暗底亮度仅 35%，1px 描边不可见）——色值写进 `graphTones.ts`
- 对比度：文字始终用 `--color-text`（对 surface ≥ 12:1）；tone 色属非文本图形元素（WCAG 1.4.11 需 ≥3:1）——light 档五档对 `#ffffff` 为 3.4 / 5.6 / 3.5 / 3.6 / 4.6，dark 档对 `#121517` 为 5.5 / 6.4 / 7.3 / 7.9 / 6.0，全部达标

**形状与排版 token**：

```
--radius-md    8px    容器圆角、rounded 节点圆角
--radius-sm    6px    工具条容器
--radius-xs    4px    工具条按钮、边标签底衬
节点标签       13px / 500 / --color-text，超宽省略
节点副标       11px / 400 / --color-text-muted
边标签         11px / 400 / --color-text-muted，带 surface 底衬
--ease-out     cubic-bezier(.22,1,.36,1)   入场 / 弹入
--ease-move    cubic-bezier(.4,0,.2,1)     重布局位移
```

**尺寸自适应与高度规则**（§5.1 形态族通用约束）：

- 宽度自适应：`W = clamp(120, ceil(文本宽) + 32, 240)`
- **高度固定，不随文本换行**——一旦允许两行，布局引擎层高不可预测，生长式入场会跳
- 非圆角形态的"视觉圆角"靠 `stroke-linejoin: round` + 1px 描边实现，不切多边形圆角（判定节点就该是尖的）

### 11.2 节点六态

| 状态 | 视觉 | 触发 |
| --- | --- | --- |
| default | surface 底 + border-strong 1px | — |
| hover | tint → 14%，stroke → 1.5px，200ms | 指针进入 |
| selected | tone 色 stroke 2px + 同色 16% 外光晕（+3px 扩边） | 点击 |
| active | success 描边 2px + 16% 底染 + 一次性 scale 1.035 弹入 | demoPath 到达 |
| dimmed | opacity .38，220ms | 其他节点 hover / 演示聚焦 |
| error | danger 描边 1.5px + 右上 4px 角标 | 节点级校验失败 |

- **hover 用低饱和背景偏移，不用强调色描边**（项目既定微交互偏好）
- **关联高亮**：hover 节点时，其直接入边与出边底线从 `--line` 提亮到 `--color-text-secondary`，非关联节点与边 `opacity .38`——成本极低，不必等 P3

### 11.3 容器与工具条

```css
.graph-block     border 1px · radius 8 · bg surface · overflow hidden
.graph-header    min-h 34 · padding 5/8/5/12 · mono 11px 600 大写
.graph-canvas    padding 20 · min-h 200 · max-h 520 · 溢出横向滚动（不缩放）
.graph-tools     gap 4 · padding 3 · 常驻 opacity .72 → hover/focus-within 1
.graph-btn       24×24 · radius 4 · icon 13px
```

- 头部与 MermaidBlock **完全对齐**；工具按钮规格与 ECharts 导出条一致
- 差异：ECharts 导出条 hover 才出现（纯瞬时操作）；播放/流动开关是**持续状态**，必须常驻可见
- 画布**不缩放**——缩放会让 13px 字变小不可读，宁可横向滚动
- 空 / 加载 / 错误态复用 MermaidBlock 的 `LoadingOrb` 与 ECharts 的 `danger 6%` 覆盖层

**工具条按钮**：`播放演示`（仅 IR 含 demoPath 时显示）· `重播入场` · `流动开关` · `导出 PNG` · `导出 SVG`

导出前必须：暂停所有 CSS 动画 → 移除 antline/pulse 层 → 取终态。底色用当前主题 `--color-surface`（与 ECharts 的 `backgroundColor` 处理一致），PNG `pixelRatio 2`。

### 11.4 详情面板与 demoPath 播放

点击节点 → 详情在**容器底部内联展开**，不用浮层（浮层在横向滚动容器里定位会漂，且遮图）：

```
max-height 0 → 220px，220ms ease；超 220px 内部滚动
标题  13px / 600 / --color-text
正文  12px / 1.65 / --color-text-secondary
左色条 3px · radius 2 · 节点 tone 色
底色   --color-surface-2
关闭   再次点击同节点 / 点空白 / Esc
互斥   同时只展开一个，切换时替换内容不收起
```

**demoPath 播放**：

- 600ms / 跳；节点到达 → active 态 420ms 弹入，出边立即开始流动
- 当前节点外全部 dimmed；已走过的节点保持 success 描边
- 单次播放后停在终态；暂停保留进度；重播入场清空进度
- 历史回放**不自动播放**（既定决策）

### 11.5 无障碍与降级

| 项 | 要求 |
| --- | --- |
| 容器语义 | `role="group"` + `aria-label="{kind 中文}：{title}"` |
| 节点语义 | `role="button"` + `tabindex=0` + `aria-label="{label}，{tone 中文语义}"` |
| 键盘 | Tab 进入 → ←→↑↓ 按布局顺序移动 → Enter 展开 → Esc 关闭退出 |
| 焦点环 | 节点 focus 时 stroke 2px `--color-accent`，与 hover 的 1.5px 明确区分 |
| reduced-motion | 关闭全部动画：入场直接终态、流动线转静态虚线、演示改为瞬时跳步 |
| 缩放 | 画布不跟浏览器字号；滚轮 + `Ctrl/⌘` 缩放 0.4–2.0 |
| 触摸目标 | 按钮视觉 24px，命中区扩展到 32px |
| 动画池 | 并发 ≤ 20（P0 实测调整），超限直接置终态不排队 |

⚠️ **硬性**：流动动画是无限循环的，长会话里多个 GraphBlock 并存会持续吃 CPU。必须做：
① `IntersectionObserver` 在块滚出视口时暂停动画（§7 已列）；② **会话内同时开启流动的块上限 3 个，超出自动关闭最早的**。

### 11.6 X6 落地代码参考

**Graph 初始化**：

```ts
const graph = new Graph({
  container,
  background: { color: 'transparent' },   // 底色由 .graph-canvas 提供
  grid: false,                            // 极简体系不加网格
  panning: { enabled: true, eventTypes: ['leftMouseDown'] },
  mousewheel: { enabled: true, modifiers: ['ctrl', 'meta'], minScale: 0.4, maxScale: 2 },
  interacting: { nodeMovable: false, edgeMovable: false, arrowheadMovable: false },
  connecting: {
    router: { name: 'orth' },
    connector: { name: 'rounded', args: { radius: 8 } },
  },
  async: true,
})
```

**节点注册（三层 SVG markup，以通用 rounded 为例，富节点同理扩展）**：

```ts
Graph.registerNode('graph-rounded', {
  inherit: 'rect',
  width: 136, height: 46,                 // 尺寸以 §5.1 形态族表为准
  markup: [
    { tagName: 'rect', selector: 'body' },
    { tagName: 'rect', selector: 'tint' },
    { tagName: 'text', selector: 'label' },
  ],
  attrs: {
    body: { rx: 8, ry: 8, strokeWidth: 1, fill: C.surface, stroke: C.borderStrong },
    // tint 仅在 success/warning/error 时给 fill 与 fillOpacity = .08
    tint: { refWidth: '100%', refHeight: '100%', rx: 8, ry: 8, strokeWidth: 0, fillOpacity: 0 },
    label: {
      fontSize: 13, fontWeight: 500, fill: C.text, fontFamily: FONT,
      textAnchor: 'middle', textVerticalAnchor: 'middle',
      textWrap: { width: -32, height: -16, ellipsis: true },
    },
  },
}, true)
```

**antline（双 path 边）**：

```ts
// 1) 模块加载时一次性注入 keyframes
if (!document.getElementById('graph-keyframes')) {
  const s = document.createElement('style')
  s.id = 'graph-keyframes'
  s.textContent = '@keyframes graph-dash{to{stroke-dashoffset:-13}}'
  document.head.appendChild(s)
}

// 2) 边 markup：line(底线) + flow(流动层)
Edge.config({
  markup: [
    { tagName: 'path', selector: 'line', attrs: { fill: 'none' } },
    { tagName: 'path', selector: 'flow', attrs: { fill: 'none' } },
  ],
})

edge.attr({
  line: {
    stroke: C.line, strokeWidth: 1.5,
    targetMarker: { name: 'block', width: 8, height: 7 },
  },
  flow: {
    connection: true,                  // ← P0 必验（§10 第 2 条）
    stroke: TONE[tone], strokeWidth: 1.5, strokeDasharray: '6 7',
    style: { animation: `graph-dash ${1.1 / speed}s linear infinite` },
  },
})
```

**建议文件结构**：

```
pages/chat/components/GraphBlock/
  ├─ graphTones.ts       # 语义色双主题常量（独立，不复用 chartOptions.ts）
  ├─ graphTheme.ts       # C.surface / C.line / C.text 等从 UI_COLORS 派生
  ├─ GraphIR.ts          # 类型 + 白名单校验
  ├─ presets.ts          # ScenarioPreset 常量表 + Resolver
  ├─ nodes.ts            # 形态族 registerNode（§5.1 + §5.5/§5.6 富节点）
  ├─ edges.ts            # Edge.config + antline/pulse attrs 构造
  ├─ GraphRenderer.ts    # graph 生命周期 + 占位布局 → @antv/layout → 渲染
  ├─ RenderScheduler.ts  # 80ms 批处理
  ├─ AnimationManager.ts # 动画池 + 视口暂停 + 流动块上限
  ├─ GraphBlock.tsx      # 容器 + 工具条 + 详情面板
  └─ index.less          # CSS Modules 或 gb- 前缀（2026-09-04 冲突事故教训）
```

**入场边路径降级**：`done` 后全局布局产生大幅位移时**不重播入场**，只做 600ms `--ease-move` 位移过渡；边路径若 X6 无法插值，退化为淡出 120ms → 直接重绘 → 淡入 180ms。

---

## 12. 实施提醒

- **样式隔离**：`GraphBlock/index.less` 的类名加 `gb-` 前缀或直接用 CSS Modules。项目已出过一次全局 `.diff-view` 类名冲突事故（见 MEMORY.md 2026-09-04）。
- **不要复用 `chartOptions.ts` 的色值常量**，建独立的 `graphTones.ts`。
- **前端改动不做编译验证**（用户既定约定：AI 只改代码，不跑 `tsc`/`vite build`）；后端 pytest 照旧。
- 工具输出路径必须落在 workspace 或 output_dir 内（项目既有安全约束）。
