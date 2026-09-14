# @ 引用渲染修复（中文词误判为技能胶囊）

> 编号：003 ｜ 类型：fix ｜ 日期：2026-09-14 ｜ 状态：已实施（待用户验证）
> 取证：用户截图（会话「测试用户 09:50」，正文 `Muse spark 模型`，末尾「模型」被渲染成技能胶囊）
> 关联：[../design/025-chat-mention-files-20260913.md](../design/025-chat-mention-files-20260913.md) §1.3 / §1.4


## 1. 现象

用户气泡正文 `Muse spark 模型` 中，`模型` 二字被渲染成 `✦ 模型` 技能胶囊。用户原话：「这个消息会误判为技能」。

## 2. 根因（代码确诊 + 脚本复现）

`divine-app/src/pages/chat/chatUtils.ts` 的 `MENTION_TOKEN_RE`，第 5 组用来兜 `/技能名`，两条变体并列：

```
(\/[A-Za-z][A-Za-z0-9_.-]{2,}|[\u4e00-\u9fff][A-Za-z0-9_.\-\u4e00-\u9fff]{1,})
```

**中文分支漏写了 `\/`**，等价于「任意 ≥2 字中文词」都算技能 token。叠加区间后的「前缀须为行首或空白」判定，命中面进一步扩大。

原始正则的误判面（脚本复现，修复前）：

| 输入 | 实际解析 | 期望 |
| --- | --- | --- |
| `Muse spark 模型` | 文本 + `<skill:模型>` | 纯文本 |
| `今天天气怎么样` | 整条 `<skill:今天天气怎么样>` | 纯文本 |
| `你好，帮我看看这个` | `<skill:你好>` + 文本 | 纯文本 |
| `@src/a.tsx 改一下` | file + `<skill:改一下>` | file + 文本 |
| `用 /笔记整理 处理一下` | 文本 + `<skill:处理一下>` | skill + 文本 |
| `我喜欢 模型 这个词` | `<skill:我喜欢> <skill:模型> <skill:这个词>` | 纯文本 |

即：**只要消息里出现以空白分隔（或整条消息以中文开头）的 ≥2 字中文词，就会被标成技能引用**。与设计 §1.3「仅在行首或空白后键入 `/` 才唤起」的语义不符——输入框触发条件（`ChatInput/index.tsx:666 detectMentionTrigger`）本来就要求字面 `@` / `/`，只有气泡渲染层掉队。

## 3. 修复

```diff
-(\/[A-Za-z][A-Za-z0-9_.-]{2,}|[\u4e00-\u9fff][A-Za-z0-9_.\-\u4e00-\u9fff]{1,})
+(\/(?:[A-Za-z][A-Za-z0-9_.-]{2,}|[\u4e00-\u9fff][A-Za-z0-9_.\-\u4e00-\u9fff]{1,}))
```

把 `\/` 提到两条变体之外，中文名恢复「必须敲了斜杠」的前提；长度下限（ASCII ≥3 / 中文 ≥2）保持不变。捕获组数量与顺序未变，`parseMentionSegments` 的解构无需改动。

## 4. 验证

修复后复跑同一批用例（`node` 直跑解析函数）：

| 输入 | 结果 |
| --- | --- |
| `Muse spark 模型` | 纯文本 ✅ |
| `今天天气怎么样` / `你好，帮我看看这个` | 纯文本 ✅ |
| `@src/a.tsx 改一下` | `<file:src/a.tsx>` + 文本 ✅ |
| `用 /笔记整理 处理一下` | 文本 + `<skill:/笔记整理>` + 文本 ✅ |
| `/skill:model 说一下` | `<skill:model>` + 文本 ✅（消歧保留字形式未受影响） |
| `Muse spark 模型 /网页搜索` | 文本 + `<skill:/网页搜索>` ✅ |
| `a@b.com` / `和/或` | 纯文本 ✅（未回归） |

## 5. 跟进实施（同日，按评审意见落地）

上一节遗留的 1、2 两条已实施：

### 5.1 `/docs` 类歧义：词法命中改为「候选」，与真实技能集合比对后才渲染

| 层 | 改动 |
| --- | --- |
| 后端 | 新增 `GET /api/workspace/skill-names`（`app/api/workspace_files.py`）：复用 `_get_skills` 的无副作用扫描 + TTL 缓存，返回**不截断**的技能名全集 + 工作区。候选接口的 `SKILL_LIMIT=8` 只能保证「弹层前 8 条」，不能当全集用。 |
| API 客户端 | `services/api.ts::listSkillNames(sessionId)`。 |
| 集合服务 | 新增 `services/skillNames.ts`：`normalizeSkillName()`（去前导 `/` 与 `skill:` 前缀、统一小写）、`peekSessionSkillNames()`、`getSessionSkillNames()`（按会话缓存 TTL 60s + in-flight 去重，失败不写缓存）、`invalidateSessionSkillNames()`。 |
| 失效联动 | `services/skills.ts::reloadSkills` / `uninstallSkill` 成功后调用 `invalidateSessionSkillNames()`——刚装/刚删的技能不必等 TTL 到期。 |
| 解析器 | `parseMentionSegments(text, knownSkills?)`：词法命中只是候选，`knownSkills` 命中才产出 `skill` 片段，否则把 token **原样还原为文本**（游标照常前进，拼接结果与原文逐字一致）。 |
| React 绑定 | 新增 `pages/chat/hooks/useSessionSkillNames.ts`：首帧直接读缓存，未就绪返回 `undefined`；会话切换的同一帧不拿旧会话集合做判定。 |
| 消费 | `MessageList` 调 hook → `MessageItem` → `UserMentionText`（新增 `knownSkills` 透传）。 |

**降级策略**：集合拿不到（请求失败 / 尚未就绪 / 会话刚切换）时传 `undefined`，退回纯词法判断——宁可多标一个胶囊，也不要把真技能误降级成普通文本。

### 5.2 胶囊内不再显示前导 `/`

`normalizeSkillName` 的输出即胶囊展示文本，`/网页搜索` → `✦ 网页搜索`，与 `/skill:model` 消歧形式（本就显示 `model`）口径统一。文件胶囊同理只显示路径（不带 `@`）。tooltip 的 `{{name}}` 也随之变为裸名。

消息原文、复制内容、后端落库仍是带前缀的原始文本（纯展示层改动，`message.content` 未动）。

### 5.3 验证

| 用例 | 传入技能集合 | 结果 |
| --- | --- | --- |
| `Muse spark 模型` | 任意 | 纯文本 ✅ |
| `Muse spark 模型 /网页搜索` | 含 `网页搜索` | 文本 + `<skill:网页搜索>` ✅ |
| `/笔记整理 帮我把 @assets/a.jpg 压一下` | 含 `笔记整理` | `<skill:笔记整理>` + 文本 + `<file:assets/a.jpg>` ✅ |
| `/skill:photo-editorial 处理` | 含 `photo-editorial` | `<skill:photo-editorial>` + 文本 ✅ |
| `见 /docs 目录` | 不含 `docs` | `见 /docs 目录`（还原为普通文本）✅ |
| `见 /docs 目录` | `undefined` | 退回词法，仍多标（已知降级行为） |
| `a@b.com` / `和/或` / `@src/a.tsx 改一下` | 任意 | 未回归 ✅ |

另有 10 例 × 3 种集合态的**无损性校验**（片段拼接逐字还原原文，覆盖「校验失败→还原文本」新分支）；后端 `pytest tests/test_workspace_mentions_skills.py tests/test_workspace_files.py tests/test_mention_skills.py tests/test_chat_mentions.py` → 40 passed（新增 4 例：全集不截断、无工作区、与候选接口共用缓存、路由可用）。

全量 `pytest tests`：**1315 passed / 3 skipped**，另有 2 例失败（`test_code_review.py::test_not_a_git_repo_raises`、`test_git_tools.py::test_not_a_repo`）——两者断言"临时目录不在 git 仓库内"，而 `--basetemp` 落在本仓库里，属既有环境假阴性（`--basetemp=/tmp/...` 后 2 passed），与本次改动无关。

前端验证脚本用 `--experimental-strip-types` 直跑**真实源文件**（剥掉跨模块 import），不是手抄正则的副本，避免验证与实现漂移。

### 5.4 仍未处理（超出本次范围）

1. 技能名集合的**真实来源一致性**由「与候选接口同源」保证——输入框能选到的技能，气泡一定能识别；但若日后 agent 侧技能集合与 `_get_skills` 扫描范围分叉，两边会同时错，需在 025 的「硬问题 ①」里持续守住。
2. `@张三` 这类以 `@` 开头的非文件 token 仍会渲染成文件胶囊（本次未做文件存在性校验，无对应后端端点）。
3. 前端仍无测试基建，上述前端验证未固化为仓库内测试。

### 5.5 附：`normalizeSkillName` 的归属

放在 `services/skillNames.ts` 而非 `pages/chat/chatUtils.ts`：解析器与集合缓存必须共用同一把"键"，而 `chatUtils → services` 是既有依赖方向（`toWorkspaceRelative` 同理）；反之会让 service 层反向依赖页面层。


## 6. 附带调整：候选浮层标题合并（同日，视觉评审）

**现象**：`/` 候选浮层顶部叠了两级标题——浮层标题「指定技能」+ 首节标题「知识技能」，层级冗余、观感差。

**改动**：

| 位置 | 改动 |
| --- | --- |
| `MentionPopup/index.tsx` | 删掉 `PopupRow` 分节行模型、`buildRows()`、`sectionLabel()`；列表改为直接 `items.map`（下标仍是 `items` 真实下标，键盘导航与高亮语义不变）。浮层标题：`指定技能` → **`选择技能`**（英文 `mentionSkillHint` 维持 `Pick a skill`）。 |
| `MentionPopup/index.less` | 删除 `.mention-section` 规则。 |
| i18n ×3 | `mentionSkillHint`：`选择技能` / `選擇技能`；删除随之失效的 `mentionSectionKnowledge` / `mentionSectionExecutable`（`知识技能` / `能力技能` / `Knowledge skills` / `Executable skills`）。 |

**信息未丢失**：技能类型仍由行内徽标承载（`mention-kind--knowledge` 显示「知识」、`--executable` 显示「能力」），后端排序也仍按类型分节（knowledge 在前），只是不再额外画一条节标题。

**与 025 的偏差**：设计 §1.3 写的是「候选按类型分节：知识技能 / 能力技能」。本次按评审改为"单一标题 + 行内类型徽标"，**025 正文该行需同步修订**（025 是未提交的 WIP，本次刻意未改，避免与在途编辑冲突）。

**验证**：三份语言包 JSON 解析通过、无残留 `Section` 键；全仓无 `mention-section` / `mentionSection` / `buildRows` 引用残留（grep 为空）。视觉确认待真机。


## 7. 附带调整：气泡内 `@文件` 引用去掉底块（同日，视觉评审）

`.user-mention-file` 原来带 `background: var(--color-accent-soft)`，在用户气泡（本身已有底色）上又叠一层色块，观感脏。改为**只靠强调色 + 等宽字形区分**：

```diff
 .user-mention-file {
-  border-radius: var(--radius-sm);
-  background: var(--color-accent-soft);
   color: var(--color-accent);
   font-family: var(--font-mono);
   font-size: 0.88em;
 }
 .user-mention-file--link {
   cursor: pointer;
-  transition: background 120ms ease;
 }
 .user-mention-file--link:hover {
-  background: var(--color-surface-2);
   text-decoration: underline;
 }
```

同时清掉随底色一起失效的 `border-radius`、`transition: background` 与 hover 底色——现在**任何状态都不出现背景色**，hover 只给下划线（链接语义），`focus-visible` 的描边保留。技能胶囊（`.user-mention-skill`，描边 + `surface-2` 底）按原样保留：两类 token 的"形状/颜色不同"正是设计 §1.4 要的一眼区分，去掉文件侧底块后差异反而更干净。


## 8. 文件图标按后缀区分：两套映射合并为唯一真源（同日，两轮）

### 8.1 第一轮：把文件树的映射抽出来（**未解决用户问题**）

**诉求**：`@` 候选浮层里所有条目都是同一个文档图标（`.pptx`、`.xlsx` 也不例外），要求与右侧文件树一致，按后缀显示对应图标。

做法是把 `FileTree.tsx` 里那段 80 行 `fileIcon()` 抽成 `components/FileTypeIcon/`（`kinds.ts` 纯判定 + `index.tsx` 渲染）。**但这是照搬参照物，参照物本身不覆盖用户的文件**：文件树那份映射里没有 `pdf`/`docx`，而用户工作区里全是被 docgen 产出、以 `.pdf`/`.md` 命名的报告——它们在抽取前后**都是**兜底文档图标，所以用户截图看下来「还是不行」。抽取本身是对的（88 例回归全过、零行为变更），但**没有解决用户看到的问题**。

### 8.2 第二轮：真正的原因是仓里并存两份映射

`MessageHelpers.tsx::fileIcon()` 里藏着**第二份**更全的映射（`pdf → FileStack`、`docx → BookMarked`、`numbers → FileSpreadsheet`…），只服务消息列表里**工具产物的文件列表**（`ToolFileList`）。于是同一个 `.pdf`：

- 在右侧文件树、`@` 候选浮层、气泡内引用 → 兜底文档图标（因为那份映射没有 pdf）
- 在消息列表的工具产物列表 → `FileStack`

**修法**：合并两份为一份并集，作为唯一真源，全部消费方切过来。

| 文件 | 改动 |
| --- | --- |
| `components/FileTypeIcon/kinds.ts` | 判定表扩到 **15 档**：新增 `pdf`（pdf）、`word`（doc/docx/odt/pages）、`sheet` 补 `numbers`、`doc` 补 `rst`。顺序即优先级，`.key` 归 slides 的历史顺序保留。 |
| `components/FileTypeIcon/index.tsx` | 补 `pdf → FileStack`、`word → BookMarked` 两个图标绑定（沿用仓里原有选型，非新发明）。 |
| `MessageHelpers.tsx` | **删除**那份重复的 `fileIcon()` 与 7 个随之无用的图标 import。 |
| `ToolFileList.tsx` | 改用 `<FileTypeIcon name={file.path \|\| file.name} />`（消息列表的工具产物文件列表）。 |
| `FileTree.tsx` / `MentionPopup` / `UserMentionText` / `MessageItem` 附件 chip / `ChatInput` 附件 chip | 第一轮已切到共享组件，本轮自动获得 pdf/word 等新档。 |

**有意为之的行为变更**（合并的取舍，非疏漏）：`sh` 归 `terminal`（沿文件树的分档，而非 helpers 的 code）；`Image` 图标的图片条目统一成 `FileImage`（同一个文件在任何位置长相一致）。图标映射中**唯一可能不一致**的只剩目录——文件树有 `node.isDir` 可用 `Folder/FolderOpen`，其余场景拿不到类型信息。

**未动的同类位置**：`ChatHeader` 导出格式菜单（按导出格式而非文件类型）、`SkillDetailModal` 的 `SKILL.md` 小节标题、`DiffView`/`FileContentView` 空状态图标、`ToolStatusIcon` 的工具图标。

### 8.3 验证

- 直跑真实 `kinds.ts`（Node `--experimental-strip-types`）：**99 例全过**——15 档全部后缀 + `Dockerfile/Makefile` + `.env`/`.gitignore`/无后缀边界 + 8 例带目录路径，其中含用户截图里的真实文件名（`长鑫存储财务分析报告.pdf` → pdf、`notes/PDF报告生成完成.md` → doc、`presentations/长鑫存储投资分析.pptx` → slides、`spreadsheets/模型成本测算_示例量.xlsx` → sheet）。
- 通过**已在运行的 dev server**（8010）按模块拉取转译结果：6 个改动模块全部 HTTP 200，无 Vite 转译错误。
- **排障记录（供下次参考）**：`divine-app/dist` 与 `/Applications/Divine.app`、`src-tauri/target/release/bundle/macos/Divine.app` 都是 **2026-09-13 18:19** 的构建产物；若界面看不到当天改动，先确认窗口是 dev（`lsof -nP -iTCP:8010` 应能看到 ESTABLISHED 连接）而不是那个打包版。


## 9. 候选浮层被消息列表压暗（同日，浮层观感修复）

**现象**：`/` 与 `@` 候选浮层的内容整体发暗——标题、行文字、徽标都比正常暗一档；用户初判为「对话框上方的阴影遮挡」。

**取证方式**：不再靠猜。用 headless Chrome + CDP 直连**真实 dev app**（8010 + 后端 8019）复现：输入 `/po` 唤起浮层 → ① `elementFromPoint` 采样 ② 列出所有与浮层矩形相交的元素及其计算样式 ③ `Page.captureScreenshot` 的 `clip + scale:3` 出放大对比图。

**定位结果**（可复现的数据）：

| 候选嫌疑 | 结论 |
| --- | --- |
| 浮层自身阴影 | ❌ 不是（用户已排除，实测也不影响内容亮度） |
| `.composer` 的 `box-shadow` 上沿 | ❌ 关掉后浮层**依旧暗**（A/B 图证） |
| 浮层 `z-index: 30` 太低 / 缺 GPU 分层 | ❌ `z-index:100`、`transform:translateZ(0)` 均无效 |
| **`.composer-wrap` 的 `backdrop-filter`** | ✅ 唯一变量：置 `none` 后浮层立刻变亮 |

**根因**：`.composer-wrap` 是 `position: static` 但带 `backdrop-filter: blur(10px)` → **backdrop-filter 创建层叠上下文**，于是整个内部子树（含绝对定位的候选浮层）被钉在该元素「静态块级」的绘制阶段；而消息列表里的气泡是 `.timeline-inner > .virtual-message-item{position:absolute}`，在**之后**的定位元素阶段绘制。实测两者矩形重叠 858×93（`div.user-content` 就落在浮层区域内）→ 消息气泡与列表元素盖在浮层上，把它压暗。

**修法**（保留模糊，只抬层级，与既有约定一致）：

```diff
 .composer-wrap {
   background: rgba(11, 13, 15, 0.72);
   backdrop-filter: blur(10px);
+  position: relative;
+  z-index: 30;
 }
```

`pages/chat/components/ChatHeader/index.less` 里早有一条同源注释与同样的处理（「backdrop-filter 会创建层叠上下文；抬高层级让 header 内的 tooltip 不被下方消息列表遮挡」，值也是 30）——本次是同一坑的第二次踩，已把原因写进 `.composer-wrap` 注释。

**受益范围**：同一个 wrap 内的**所有**浮层一并修好——`/`·`@` 候选浮层、模型/档位菜单（`ModelEffortControl`）、审批模式下拉、项目选择器。

**未改动的备选方案**：把浮层 portal 到 `body`（改动大、需自己管定位与滚动同步）；去掉 wrap 的 `backdrop-filter`（会丢掉底栏毛玻璃，且该项目 8 处都在用 blur）。

**验证**：注入 `.composer-wrap{position:relative;z-index:30}` 后放大截图恢复清晰（`blur(10px)` 仍在）；改源码后重新加载真实 app 复核，`wrap.pos=relative / z=30 / blur=blur(10px)`，浮层截图与注入版一致；全页截图无其它回归（底栏、消息列表、滚动按钮位置不变）。


## 10. 气泡内 `@文件` 引用改为胶囊形态（同日，视觉评审）

**诉求**：文件引用加上圆角胶囊边框，与技能胶囊形态一致。

```diff
 .user-mention-file {
+  border: 1px solid var(--color-border-strong);
+  border-radius: 999px;
   color: var(--color-accent);
   font-family: var(--font-mono);
-  font-size: 0.88em;
+  font-size: 0.86em;
 }
```

与 `.user-mention-skill` 对齐的：`border` / `border-radius: 999px` / `font-size: 0.86em` / 等宽字形 / 由 `.user-mention` 统一提供的 `padding: 4px 8px`、`gap: 4px`。**刻意保留的差异**（两类 token 仍需一眼可分）：

| | 文字色 | 底色 |
| --- | --- | --- |
| `@文件` | `--color-accent`（暗色主题下为 `#ffffff`，极简黑白主题里 accent 就是白） | 无（§7 的评审结论：不叠填充） |
| `/技能` | `--color-text-secondary` | `--color-surface-2` |

**验证**：CDP 注入两个胶囊并排（不发送任何消息，零副作用），读计算样式确认 `border / radius / font-size / padding / gap` 四项完全一致、色值按上表区分；`clip+scale:3` 放大截图核对观感。

**与 025 的偏差（第二处，需同步修订）**：设计 §1.4 写的是「两类 token 颜色与**形状**不同」。现在形状统一为胶囊，区分解耦到「文字色 + 是否有填充」。025 是未提交的 WIP，本次仍未改。

**待定**：hover 目前仍是 `text-decoration: underline`（链接语义）。形态变成胶囊后，改成描边提亮（`border-color`）可能更贴；需产品确认，保守起见未动。


## 11. 胶囊与同行文字不居中（同日，§10 的回归）

**现象**：§10 给 `@文件` 加上边框后，胶囊与同行文字不再居中（用户截图：胶囊整体偏低）。

**测量**（CDP 在真实页面注入复刻气泡，`Range.getBoundingClientRect()` 取文字 em 盒，与胶囊 border-box 比中心）：

| 变量 | 胶囊高 | 内部（图标/文件名）中心偏差 | 胶囊中心 − 文字 em 中心 |
| --- | --- | --- | --- |
| `vertical-align: -2px`（改前） | 28.1px | 0 / 0 | **+2.0px（偏低）** |
| `0` | 28.1px | 0 / 0 | 0 |
| `baseline` | 28.1px | 0 / 0 | 0 |
| `middle` | 28.1px | 0 / 0 | +1.8px |
| `1px` ~ `3px` | 28.1px | 0 / 0 | −1 / −2 / −3 |

即：胶囊**内部**（图标 + 文件名）一直是居中的，问题出在胶囊作为整体相对**同行文字**偏低 2px。

**根因**：`.user-mention { vertical-align: -2px }` 是为更早的「无边框、`padding: 0 5px` 小胶囊」手调的魔法值；§10 加上 `border` + `padding: 4px 8px` 后盒高从 ~22px 变成 28.1px，同一个 -2px 不再成立。

**修法**：

```diff
 .user-mention {
   padding: 4px 8px;
   line-height: 1.5;
-  vertical-align: -2px;
+  vertical-align: baseline;   /* 实测：胶囊中心与同行文字 em 中心差 0 */
 }
```

选 `baseline` 而非 `middle` 是因为实测 `middle` 仍偏低 1.8px（`middle` 对齐的是「基线 + x-height/2」，对以中文为主的正文偏低）；也不用固定 px，避免下次改尺寸再产生同类回归。

**注意（写进代码注释了）**：inline-flex 首子元素是图标（原子元素）时，其基线取该图标的**下边缘**，所以这个 0 偏差依赖图标尺寸（当前 11px）。**若日后调整图标尺寸，需按本文方法重新实测**，不要回退到固定 px。

**验证**：改源码后重新加载真实 app 复测，`va=baseline`、胶囊高 28.1px、中心差 `0 / 0`（两种文件名长度），放大截图观感一致。


## 12. 文件胶囊 hover 改为「图标 + 文字变色」（同日，视觉评审）

**诉求**：hover 不要下划线，只要图标和字体变色。

```diff
 .user-mention-file--link {
   cursor: pointer;
+  transition: color 0.15s ease;
 }
 .user-mention-file--link:hover {
-  text-decoration: underline;
+  color: var(--color-accent-hover);
 }
```

- 用项目现成的 `--color-accent-hover` token（暗色 `#d1d5db`，浅色 `#374151`），不新造色值。
- **图标自动跟随**：`FileTypeIcon` 渲染的 lucide svg 是 `stroke="currentColor"`，颜色随父级 `color` 变，无需单独处理（`iconStroke` 实测为 `currentColor`）；`transition` 加 0.15s 让变化不至于突兀。
- 胶囊已带描边，下划线会与边框打架，故去掉。

**验证**（真实 hover，不是读源码猜的）：CDP 注入复刻气泡 → `Input.dispatchMouseEvent({type:'mouseMoved'})` 悬停到胶囊中心 → 读计算样式：

| 状态 | color | text-decoration | svg 颜色 |
| --- | --- | --- | --- |
| 悬停前 | `rgb(255,255,255)` | `none` | `rgb(255,255,255)`（currentColor） |
| 悬停后 | `rgb(209,213,219)` | `none` | `rgb(209,213,219)` |

**方向说明**：因为极简黑白主题里 `--color-accent` 就是纯白（最亮），hover 只能是**变暗**（白 → `#d1d5db`）。若期望相反的强调方向（默认次级灰、hover 提亮），需要把默认色改成 `--color-text-secondary` 再 hover 到 `--color-accent`——这会让文件胶囊与技能胶囊的默认文字色一致、只剩底色差异，需产品定调。











