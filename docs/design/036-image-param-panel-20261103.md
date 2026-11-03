# 图像生成参数面板 · 设计（036）

> 日期：2026-11-03 ｜ 类型：design ｜ 状态：**P1 已实施（设置 UI 除外）**
> 已实施：A2UI 契约扩展（`ChoicePicker.columns` / `options[].icon` / **新组件 `FilePicker`**）、
> `media_models` 契约与掩码、`image_brief` 面板工具、多图并发下载、`image_defaults` 记忆、
> 结果一行 4 张卡片缩略。
> 未实施：设置页「生成模型」分区（P1-e，配置暂可手编 `divine-model-provider.json`
> 同目录的 settings.json）；GLM 自定义尺寸（P2）。
> 复用：[035 视频生成](035-video-model-generation-20261103.md) 的 `FilePicker` / `ChoicePicker(columns, icon)` / `media_models` / A2UI 动作回流
> 触发：用户提出「文生图/图生图 工具是否能继续优化，和视频一样选择比例/数量等内容」
> 代码：`divine-server/app/tools/adapters/image_generate.py`、`scripts/image_generate.py`、`divine-app/src/pages/chat/components/MessageItem/ToolFileList.tsx`

---

## 1. 现状：能力早就有了，缺的是"让人选"

`image_generate` 的入参其实比视频还齐：

| 入参 | 支持范围 | 现状 |
| --- | --- | --- |
| `aspect_ratio` | 8 档：1:1 / 4:3 / 3:4 / 16:9 / 9:16 / 3:2 / 2:3 / 21:9 | 有，但**用户说不上话**，全靠模型从一句话里猜 |
| `n` | 1–4（GLM 固定 1） | 同上 |
| `reference_image` | MiniMax 支持图生图，GLM 不支持 | 同上，且没有选图入口 |
| `size` | GLM 专用，7 档（32 倍数，512–2048） | 同上 |
| `prompt_optimizer` | MiniMax 支持 | 同上 |

三个实际问题：

1. **参数靠猜**：用户说"生成一张图"，模型随便给个 1:1 / 1 张；想要 16:9 得自己在话里说全；
2. **key 是借的**：`scripts/image_generate.py::_minimax_config()` 翻 `settings.models` 里 vendor=minimax 的条目拿 key，与视频的 `media_models` 是两套；
3. **多图结果难看清**：4 张图现在是**4 行文件列表**，每张只有名字和一个眼睛图标，要逐个点开才知道哪张好。

## 2. 目标与非目标

**目标**

1. 生成前弹参数面板：参考图 / 数量 / 比例（+ 提示词优化），与视频同一套组件与交互；
2. 图像模型配置并入 `media_models`（`kind=image`），与视频共用一处配置；
3. 多图结果改为**缩略网格**，一眼看完，点开大图。

**非目标**

- 局部重绘 / 扩图 / 抠图（inpainting、outpainting）；
- 风格模型市场、LoRA；
- 图像也做异步任务面板——**不需要**，10–30s 的同步调用足够（见 §7）。

## 3. 复用什么（不重复造）

| 已有/035 定下的 | 这里怎么用 |
| --- | --- |
| `video_brief` 的「确定性 IR + `prepare()` 纯函数」模式 | 照抄成 `image_brief`，实时渲染与落库回放共用同一份 |
| `FilePicker`（035 新增组件） | 参考图选择，值即绝对路径 |
| `ChoicePicker` 的 `columns` + `options[].icon`（035 新增） | 比例选项 3 列网格 + CSS 比例图标 |
| A2UI 动作回流 `context[{key,value:{path}}]` | 「开始生成」带参数回传，不新造协议 |
| `media_models` 契约 | 多一个 `kind=image`，字段完全一致 |

两张卡片的构建逻辑会高度相似（分区标题 + 选项组 + 提交按钮），建议抽 `app/media/brief_common.py`，避免两份近似代码各自漂移。

## 4. 面板结构

```
Column
├ Text（小标题）参考图（选填）
├ FilePicker    → /form/reference_image   「选择图片」+ 缩略图 + 移除
├ Text（说明）不选=文生图；选了=按这张图生成（仅 MiniMax 支持）
├ Text（小标题）生成数量
├ ChoicePicker  → /form/n                 1 张 / 2 张 / 3 张 / 4 张（GLM 只有 1 张）
├ Text（小标题）画面比例
├ ChoicePicker  → /form/aspect_ratio      智能 / 1:1 / 4:3 / 3:4 / 16:9 / 9:16 / 3:2 / 2:3
├ Switch        → /form/prompt_optimizer  自动优化提示词（仅 MiniMax）
└ Row
  ├ Button primary「开始生成」 action image_create + context
  └ Button ghost  「取消」     action cancel
```

- 截图的「商品图 必填」在这里是**选填**——我们的工具本来就支持纯文生图，强制上传会砍掉一半用法；
- 「生成数量」用 `ChoicePicker` 而不是下拉：4 个档位，胶囊比下拉少一次点击；
- **没有折叠区**：A2UI 没有条件渲染、也没有折叠容器，所以"高级选项"只能平铺（就一个 Switch，平铺不占地方）。

## 5. 能力矩阵（面板按当前生效模型渲染，不出现不支持的项）

| | MiniMax `image-01` | GLM `glm-image` |
| --- | --- | --- |
| 文生图 | ✅ | ✅ |
| 图生图（参考图） | ✅ `subject_reference` | ❌ → **参考图这一整行不渲染** |
| 数量 | 1–4 | **固定 1** → 只出「1 张」，不出选择器 |
| 比例 | 8 档原样传 | 映射到 7 档尺寸，**21:9 会静默降到 16:9** → 面板不显示 21:9 |
| 尺寸 | 由比例决定 | 显式 `size`（32 倍数）→ P2 再给自定义尺寸 |
| 提示词优化 | ✅ | ❌ → 不渲染该 Switch |

**"不渲染"比"渲染了再报错"重要**：GLM 下显示一个可选 21:9 的按钮，点完发现出的是 16:9，比没有这个按钮更糟。

## 6. 什么时候弹（与视频的差别）

图像便宜、快（10–30s），**每次都弹会烦**。所以：

| 情况 | 行为 |
| --- | --- |
| 用户只说了画面内容（"生成一张海边日落的图"） | 弹卡（第一次），默认值取 `image_defaults` |
| 用户已说清（"要 4 张 16:9 的"） | 不弹，直接生成 |
| 用户说了"按这张图改"且已有附件 | 不弹，参考图用附件路径 |
| 说了"按这张图"但没图 | 弹卡（带选图控件），与视频同一套 `needs_media` |

`image_defaults`：把上次成功生成用的 `n / aspect_ratio` 存进 settings（`image_defaults: {n, aspect_ratio}`）。**第二次开始，面板基本只需点一下确认**，这是"既要可选、又别每次都配"的折中。

## 7. 执行：保持同步，不引入任务面板

| | 视频 | 图像 |
| --- | --- | --- |
| 耗时 | 1–5 分钟 | 10–30s |
| 执行 | 后台 worker + `media_tasks` 表 | **工具内同步**（现有 `timeout=150` 够用） |
| 进度 | 任务面板 + 事件广播 | 工具卡转圈即可 |
| 中断 | 云端继续跑、可恢复 | 直接失败重跑，成本低 |

多图下载是唯一要动的地方：现在 1–4 张是**逐张顺序下载**，改成并发（`asyncio.gather`），4 张的总耗时从 4× 降到 ~1×。

## 8. 结果展示：卡片缩略图，一行 4 张

现在（`ToolFileList`）是 4 行文件条目：

```
🖼 image-1730…-1.jpeg  [👁]
🖼 image-1730…-2.jpeg  [👁]
🖼 image-1730…-3.jpeg  [👁]
🖼 image-1730…-4.jpeg  [👁]
```

改成**一行 4 张的卡片缩略图**：一眼看完 4 张，选中哪张直接点开大图。

### 8.1 布局

```less
.image-result-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));  /* 固定 4 列，不 auto-fit */
  gap: 8px;
}
@media (max-width: 480px) {                          /* 窗口窄了降 2 列，否则卡片小到看不清 */
  .image-result-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
```

| 张数 | 排布 |
| --- | --- |
| 1 张 | 单张大卡（`max-width: 320px`），不拉满整行 |
| 2–4 张 | 仍按 4 列左对齐，**不**拉伸成 2 列巨图（每张宽度一致，便于横向比较） |

用 `grid` 而不是 `flex-wrap`：4 张必须严格排在一行，flex 在窄容器里会悄悄换行成 3+1，视觉上像"少了一张"。

### 8.2 卡片本身

```
┌──────────────┐
│              │  ← 缩略图区：高度 120px，object-fit: contain，中性底色
│   (整图)      │     不裁切：用户选 16:9 就是为了看构图，cover 会切掉两侧
│              │
├──────────────┤
│ 1/4 · 1024×576 │  ← 一行元信息（数量序号 + 实际尺寸）
└──────────────┘
```

- **点击卡片** → 打开现有预览面板看大图（`onPreviewFile({relPath})`，`toWorkspaceRelative` 已有）；
- hover 时右上角浮出「另存为」（单个导出），不占常态空间；
- 底部保留「另存为全部」与**「文件列表」折叠入口**——需要按文件名/路径找图的用户仍然拿得到。

### 8.3 三个实现细节

1. 缩略图走**已有**的 `/api/files/image?path=`（允许 output_dir 根，天然支持），不需要新端点；
2. `<img loading="lazy" decoding="async">`：一次 4 张 base64 化是浪费，这里直接走 HTTP；
3. 只在 `tool.tool === "image_generate"` 且 `files.length >= 1` 时启用网格；**其他工具的文件行一行都不动**（`edit_files` 那种几十行的列表不能变成卡片墙）。

## 9. 设置：并入 `media_models`（`kind=image`）

035 已经定义了 `media_models` 的字段与掩码规则，这里只是多一类：

```jsonc
{ "id": "media-img-1", "kind": "image", "label": "MiniMax 图像",
  "provider": "minimax", "base_url": "https://api.minimaxi.com",
  "api_key": "sk-***", "model": "image-01",
  "options": { "n": 1, "aspect_ratio": "1:1" }, "active": true }
```

设置页「生成模型」分区里分成**图像 / 视频**两组（035 §10 已经预留了这个结构）。

**迁移**：`_minimax_config()` 现在会翻 `settings.models` 找 key，改为**先读 `media_models[kind=image]`，读不到再回落旧路径**，保留一个版本周期，避免升级后图像生成突然报"缺 key"。

## 10. 实施拆解

| 阶段 | 内容 | 涉及文件 |
| --- | --- | --- |
| **P1-a 配置** | `media_models` 支持 `kind=image` + 迁移回落 | `config.py`、`api/settings.py`、`scripts/image_generate.py` |
| **P1-b 工具** | `image_brief`（确定性 IR）+ 动作 `image_create` + 意图 `image` 已存在 | `tools/adapters/image_brief.py`（新）、`tools/adapters/__init__.py`、`agent/tools/tools.py` |
| **P1-c 面板契约** | 复用 035 的 `FilePicker` / `ChoicePicker`，**不新增组件** | 依赖 035 的 P1-c2 先落地 |
| **P1-d 结果** | 一行 4 张卡片缩略（单张降级大卡）+ 另存为全部 / 文件列表入口 | `MessageItem/ToolFileList.tsx`、`ToolStatusCard.tsx`、样式 |
| **P1-e 性能** | 多图并发下载 | `scripts/image_generate.py` |
| **P2** | 自定义尺寸（GLM `size`）、局部重绘、风格预设 | — |

**验收标准**

1. 说「生成一张海边日落」→ 弹卡（参考图 / 数量 / 比例 / 提示词优化），默认值来自 `image_defaults`；
2. 说「生成 4 张 16:9 的海边日落」→ **不弹卡**，直接出 4 张；
3. GLM 图像模型下：**没有参考图那一行**、数量只有 1 张、比例里没有 21:9；
4. 选了参考图 → 生成结果确实基于该图（MiniMax），且面板显示的就是那张缩略图；
5. 4 张结果**排在同一行**（4 列等宽卡片），点任意一张能看大图；窗口收窄到 480px 以下降为 2 列；单张时为一张大卡而不是 1/4 宽的缩略图；
6. 总下载耗时明显低于顺序下载（4 张 < 2 倍单张）；
7. 参数与上次一致时，面板默认已选中，点一次即可；生成后 `image_defaults` 被更新。

## 11. 待定

1. **「另存为全部」**：是打包成 zip，还是逐张另存到所选目录？我倾向逐张写入所选目录（用户能直接看到文件），zip 需要额外依赖。
2. **比例是否包含 3:2 / 2:3**：截图只有 6 项（智能 + 5 个），但工具支持 8 档。我倾向**全给 8 档**——横版配图常用 3:2，砍掉反而要用户绕回对话里说。
3. **图像要不要也进「生成任务」面板**：我建议**不进**（10–30s，同步更直观）。如果后续接更慢的模型（如 4K 放大），再并入。
