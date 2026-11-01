# 008 · options 选项卡退化成裸 JSON，且位置夹在面板之上

- 日期：2026-11-01
- 影响面：前端聊天消息渲染（`ChoiceBlock` / `MessageItem`）
- 状态：已修复（未提交）

## 现象

汇率面板那一轮结束后，正文末尾的「还需要我做什么」选项**没有渲染成可点卡片**，
而是显示成一块代码块，标题栏写着 `TEXT`，里面是原始 JSON：

```
TEXT
{"title": "还需要我做什么", "options": [{"label": "算一笔换汇金额", ...
```

同时这块「文本」排在汇率面板**上方**，用户预期选项卡应在面板之后（消息最后）。

## 根因

### 一、JSON 括号写错，解析失败后静默降级

从应用库取该回合落库的原文，`options` 围栏内容为：

```json
{"label": "生成汇率换算表", "desc": "输出 Excel，覆盖常用金额档位与多币种"),
```

第二个选项对象应以 `}` 收尾，模型写成了 `)`。`JSON.parse` 直接抛
`Expected ',' or '}' after property value`。

`parseOptionsBlock()` 原有两级尝试：原样解析 → `sanitizeJsonQuotes()`（修未转义引号）。
两者都只处理**引号**，不管**括号形态**，于是返回 `null`。此时 `MarkdownView` 的
`language === "options"` 分支走到 fallback：

```tsx
if (language === "options") {
  const data = parseOptionsBlockCached(code);
  if (data) return <ChoiceBlock ... />;
  if (streaming) return null;
  return <CodeBlock code={code} language={language} streaming={streaming} />;  // ← 走这里
}
```

而 `languageLabel("options")` 查表未命中 → `normalizeLanguage()` 归一到 `plaintext`
→ 标签显示 **Text**，这就是截图里的 "TEXT" 来源。

### 二、选项卡位置由正文顺序决定

原结构是「MarkdownView（正文，含 options 围栏）→ UISurfaceBlock（面板）」，
所以卡片只要在正文里，就必然排在面板**上方**。

## 修法

| 文件 | 改动 |
|---|---|
| `ChoiceBlock/index.tsx` | 新增 `repairJsonShape()`：按栈配平，闭括号与栈顶不符时替换成期望符号，末尾补齐缺失括号，丢弃尾逗号；`parseOptionsBlock()` 改为四级候选（原样 → 修引号 → 修括号 → 两者都修），顺序固定保证合法 JSON 不被改写 |
| `ChoiceBlock/index.tsx` | `splitNoteOptions()` 返回值增加 `fenced`，区分「命中 ```options 围栏」与「裸 JSON 兜底」 |
| `MessageItem/index.tsx` | 非用户消息把 `options` 围栏从正文拆出，`MarkdownView` 只渲染散文；卡片改在 `message.surfaces` **之后**渲染（正文 → 面板 → 选项卡） |

两个防退化约束：

- **解析失败保留原样**：只有 `fenced && data` 才把围栏从正文摘走。若 JSON 烂到修不回来，
  仍显示原始代码块（可见、可复制），而不是静默吞掉内容。
- **流式不跳动**：围栏未闭合时 `OPTIONS_FENCE_RE` 不匹配 → `fenced=false` → 交回
  `MarkdownView`（它对未闭合 options 返回 `null`）。闭合瞬间直接在末尾出现卡片，
  不会「先在正文里闪一下再跳走」。

## 验证

用脚本从源码直接抽取 `repairJsonShape`（非复制逻辑）跑真实用例：

| 用例 | 结果 |
|---|---|
| 落库那段畸形 JSON | 原始解析失败 → 修复后成功，3 个选项与 `action: "decline"` 全部保留 |
| 合法 JSON | 修复前后字节一致（幂等） |
| 尾逗号 `[{"a":1},]` | 正常解析 |
| 缺右括号 `{"options":[{...}` | 自动补齐 |
| 字符串内含 `)`（`"总价 (含税) 100 元"`） | 原样保留，未被误改 |

`tsc -b`、`eslint`、`prettier --check` 均通过。

## 教训

1. **模型产出的 JSON 不能按「合法」假设处理**。这类小错（`}` 写成 `)`、尾逗号、缺闭合）
   在 LLM 输出里是常态，渲染侧必须有形态级兜底，而不是只修引号。
2. **渲染失败要留退路**。降级成代码块虽然丑，但比丢弃内容好；本次修完仍保留这条退路。
3. **「谁在最后」应由语义决定，不由 markdown 顺序决定**。选项卡表达「下一步动作」，
   结构上就该固定在消息末尾，和面板是否出现无关。
