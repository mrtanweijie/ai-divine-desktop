# 视频生成模型配置与预览播放 · 设计（035）

> 日期：2026-11-03 ｜ 类型：design ｜ 状态：**P1 全部已实施**
> 已拍板（2026-11-03）：P1 只做 **MiniMax + 智谱**；图生视频支持**首帧 / 首尾帧**；比例图标**用 CSS 绘制**（见 §12.1）
> 已实施清单：`media_tasks` 表 + worker（提交/轮询/下载/旁车文件/重启恢复/并发 2）、`video_brief` 面板工具（素材来源/首尾帧/比例/分辨率/时长/字幕/口播/预估费用）、
> `video_generate` 工具（静默裁剪 + needs_media/needs_source）、`/api/files/media` Range 播放 + `videos` 下载分类、`VideoPlayer` 组件、
> 预览面板视频分支、CSP `media-src`、工具卡任务状态（`media_tasks_changed` 事件 + store）、意图 `video` 与 `_VIDEO_RULES`、
> **生成任务面板页**（侧栏入口 + 进行中/已完成 + 不再等待/播放/另存为/重试/删除 + 徽标 + toast/系统通知）、**设置「生成模型」分区**（图像/视频两组 + 单价）。
> 触发：用户提出「配置生成视频的模型的时候，需要支持生成视频，预览播放视频」
> 相关：`image_generate`（图像生成范式）、`model_providers`、`BinaryPreview`（文件预览）
> 拟新增：`app/media/`、`app/tools/adapters/video_generate.py`、`app/api/media.py`、`SettingsModal/MediaSection.tsx`

---

## 1. 现状：为什么"配好了也生成不了"

四个事实，缺一个都做不成：

| # | 事实 | 证据 |
| --- | --- | --- |
| 1 | **只有图像生成，没有视频** | `app/tools/adapters/image_generate.py` 是唯一生成类工具；全仓无 `video` 生成代码 |
| 2 | **图像模型的 key 是"借"的** | `scripts/image_generate.py::_minimax_config()` 翻 `settings.models` 里 vendor=minimax 的条目取 key；GLM 直接读 `settings.glm_api_key` |
| 3 | **预览不支持视频** | `BinaryPreview.tsx::PREVIEWABLE_EXTENSIONS` 无 mp4/webm/mov；`workspace.rs::binary_preview_mime()` 也只认图片与 PDF |
| 4 | **CSP 会直接拦掉 `<video>`** | `tauri.conf.json` 里 `default-src 'self'`，只额外放行了 `img-src` 与 `connect-src`，**没有 `media-src`** |

另外，把"视频模型"当聊天模型加进 `settings.models` 也是错的：那份列表会被输入框的模型切换器消费，等于在对话里多出一个只会报错的模型。

## 2. 目标与非目标

**目标**

1. 设置里有独立的**生成模型**配置区，视频模型可增删改、可存 key、可测连通性；
2. 参数没定全时**先弹 UI 卡片**让用户选（比例 / 分辨率 / 时长 / 字幕 / 口播），选完一键开始生成（§7）；
3. Agent 能按配置生成视频（**纯文本 / 首帧 / 首尾帧**，按 provider 能力开放），落盘到 `<workspace>/videos/`；图生视频必须在面板内选图，缺图时明确提示而不是报错（§7.8）；
4. **提交即返回**，生成过程不占住对话：随时可以继续聊、切会话（§6）；
5. 有独立的**生成任务面板**看进行中/已完成的任务，完成时能收到通知（§9）；
6. 生成完能在**应用内直接播放**：消息卡片里播一次，任务面板/文件预览里也能播（支持拖进度条）。

**非目标（本期不做）**

- 视频剪辑、拼接、**字幕烧制进画面**、批量抽帧（§7.7 说明 P1 只出 `.srt`）；
- **语音合成配音**（P1 只出旁白稿，TTS 在 P2）；
- 视频转 GIF / 封面帧提取（P2 候选，做的话用 ffmpeg，需确认 sidecar 里有没有）；
- 本地模型跑视频（显存不现实）。

## 3. 关键约束（决定架构的五条）

| 约束 | 数值 / 事实 | 影响 |
| --- | --- | --- |
| **全部是异步任务** | 提交拿 `task_id` → 轮询 → 拿临时 URL → 再下载 | 适配器要分「提交 / 查状态 / 下载」三段，不能"一次请求出结果" |
| **生成耗时 1–5 分钟** | 官方文档明确写 "typically 1 to 3 minutes" | **绝不能同步等**：工具调用 3 分钟会把对话锁死（§6），必须后台 worker + 任务表 |
| **成品体积 5–30MB** | 5s / 720P 约 3–8MB，2K 可到 20MB+ | 现有预览走 base64 data URL，`MAX_BINARY_PREVIEW_BYTES = 25MB` 且内存翻 1.33 倍 → **不可用**，改走 Range |
| **链接是临时的** | MiniMax 任务只保留 7 天、下载链接有时效 | 必须在生成成功的当次就下载落到本地，不能只存 URL |
| **用户不能干等** | 生成期间用户仍要能聊天、切会话、看别的 | 需要独立任务面板 + 完成通知（§9），进度不能只靠对话里那张卡 |

## 4. 数据契约

### 4.1 设置：`media_models`（新增，与聊天模型完全分离）

`settings` 是扁平 dict，键用 snake_case：

```jsonc
"media_models": [
  {
    "id": "media-1730...",
    "kind": "video",              // video | image（image 为 P2 迁移预留）
    "label": "MiniMax 海螺",
    "provider": "minimax",        // minimax | zhipu | dashscope | custom
    "base_url": "https://api.minimaxi.com",
    "api_key": "sk-***",          // 只在服务端存；GET 时清空并置 has_api_key
    "model": "MiniMax-H3",
    "options": {                  // 各家差异参数，键名统一后再映射
      "duration": 5,
      "resolution": "720P",
      "aspect_ratio": "16:9",
      "price_per_second": 0.07    // 每秒单价（元），选填；不填则全程不显示费用（§7.10）
    },
    "active": true
  }
]
```

- 读取：`GET /api/settings` 返回 `media_models`，`api_key` 一律置空 + `has_api_key: true`；
- 保存：`SettingsUpdate.media_models: list[MediaModelUpdate] | None`，复用 `merge_model_updates()` 的"空 key 保留旧值"语义（抽成通用函数，图像/视频共用）；
- 兼容：`media_models` 为空时，视频工具直接报「未配置视频模型」并给出设置入口提示，**不回退到聊天模型 key**（避免拿对话 key 去调视频接口报 401 的迷惑错误）。

### 4.2 工具入参

```jsonc
video_generate({
  "prompt": "...",              // 必填
  "model_id": "media-xxx",      // 可选；只有多个视频模型时用，缺省取 active
  "mode": "text",               // text | first_frame | first_last；缺省按传了几张图推断
  "source": "custom",           // custom | article（资讯视频，§7.9；article 时 prompt 为提炼稿）
  "source_url": "https://…",    // article 时的原文 URL，落任务表供溯源
  "duration": 5,                // 秒；按 provider 支持区间就近取整
  "resolution": "720P",         // 480P/720P/1080P/2K，按 provider 合法集裁剪
  "aspect_ratio": "16:9",
  "first_frame": "/abs/a.png",  // 图生视频：首帧（用户附件路径，需 allow_external_paths）
  "last_frame": "/abs/b.png",   // 首尾帧：尾帧（仅 MiniMax H3 支持，智谱不支持）
  "subtitles": false,           // 可选：true 时同步产出同名 .srt（P1 不烧制，见 §7.7）
  "voiceover": "……",            // 可选：口播/旁白文案，落 .txt 并写进 prompt 的音频提示
  "filename": "海边日落"         // 可选；落盘名
})
```

**没有 `wait_seconds`**：工具不再等待（§6），提交后立刻返回 `task_id`。

`mode` / `first_frame` / `last_frame` / `subtitles` / `voiceover` 与面板的 `/form/*` 一一对应——**面板收集的键就是工具入参的键**，回流时不需要再做一次字段映射（少一层就可能错位）。

**图生视频的失败语义**：推断为图生视频但 `first_frame` 为空 / 文件不存在 / 不是图片 → **不提交任务**，返回 `needs_media`：正文说清「还差一张首帧图」，并**重新弹一次带选图控件的卡**（不要只丢一句文字，让用户自己找回旧面板）。

返回值沿用图像工具的形态，前端零新协议：

```jsonc
{ "success": true, "message": "已提交生成任务（MiniMax-H3，5s/720P），预计 1–3 分钟",
  "data": {
    "task_id": "mt_8f3a…",
    "status": "running",
    "provider": "minimax",
    "params": { "duration": 5, "resolution": "720P", "aspect_ratio": "16:9" }
  } }
```

生成完成后，任务面板/卡片从 `media_tasks` 拿到 `file_path` 再展示 `file_name` 与播放器——**工具调用本身不返回文件**。

### 4.3 产物落地：**不把云端 URL 交给用户**

生成成功后 provider 给的是**临时地址**（MiniMax 任务只保留 7 天，`content.url` 有时效），所以：

```
provider 返回 content.url（临时、会过期）
  → 立刻下载到 <output_dir>/videos/（重试 2 次）
  → 之后一切以本地文件为准：播放、预览、导出
  → 云端 URL 只做一次性中转，不写进消息、不给用户
```

理由很实际：把临时链接贴给用户，三天后点开就是 404，而文件其实早就可以存到本地。

**三条导出出口**（用户说的"下载"通常指这三件事里的某一件）：

| 出口 | 做法 |
| --- | --- |
| 打开所在目录 | 复用现有 `openFileLocation(filepath)`（卡片上的文件名已经是这个行为） |
| 另存为… | Tauri `save` 对话框 + 复制文件（PNG/PDF 那边没有，视频更需要——用户要发微信/上传时最直接） |
| HTTP 下载 | `download_url = /files/videos/<name>`（`ToolAdapter` 在文件位于 `<output_root>/<category>/` 时自动生成） |

两个必改点：

1. `files.py::ALLOWED_CATEGORIES` 要加 `videos`，否则 `/files/videos/<name>` 直接 400；
2. **播放走** `/files/media?path=`（不加 `Content-Disposition`，支持 Range 拖动），**下载才走** `/files/videos/<name>`（带 `attachment`）。两者别混用——`download_file` 现在会给 `Content-Disposition: attachment`，拿它当 `<video src>` 在某些环境下会被强制下载而不是播放。

### 4.4 任务表（P2 必需，P1 可先只记日志）

```sql
CREATE TABLE IF NOT EXISTS media_tasks (
  id             TEXT PRIMARY KEY,
  session_id     TEXT,
  call_id        TEXT,
  kind           TEXT NOT NULL,        -- video
  provider       TEXT NOT NULL,
  model          TEXT,
  prompt         TEXT,
  params_json    TEXT,
  remote_task_id TEXT,
  status         TEXT NOT NULL,        -- queued | running | succeeded | failed | expired
  file_path      TEXT,
  error          TEXT,
  created_at     TEXT,
  updated_at     TEXT
);
```

建表走 `app/db/migrations.py` 既有的 `CREATE TABLE IF NOT EXISTS`，不需要单独迁移脚本。

## 5. 后端选型与接口形态

**P1 只做 MiniMax + 智谱**（已定）。DashScope 万相保留接口位，不实现——三家一起上，测试与错误映射成本翻倍，而前两家已经覆盖"贵但强"和"便宜快"两档。

| 后端 | 提交 | 查询 | 成功取值 | 模型示例 | 图生视频 |
| --- | --- | --- | --- | --- | --- |
| **MiniMax** | `POST {host}/v2/video_generation` | `GET {host}/v2/query/video_generation/{id}` | `task.content.url` | `MiniMax-H3` / `MiniMax-H3-Max` | 首帧 / 首尾帧（`content[]` 里 `role=first_frame` / `last_frame`） |
| **智谱** | `POST {host}/api/paas/v4/videos/generations` | `GET {host}/api/paas/v4/async-result/{id}` | `video_result[0].url`（`task_status=SUCCESS`） | `cogvideox-flash` | 仅首帧 |
| ~~DashScope 万相~~ | 留接口位，P1 不实现 | — | — | — | — |

三个"坑"要写进代码，不靠记性：

1. **`base_url` 是主机级，不是 API 根级**：MiniMax 图像走 `/v1`、视频走 `/v2`；智谱是 `/api/paas/v4`。所以每条 `media_model` 存的是主机（或完整根），路径由 provider 适配器拼。
2. **状态字段名各不相同**：`task.status` / `task_status`，枚举也各写各的（`succeeded` / `SUCCESS`）→ 适配器统一归一成 `queued|running|succeeded|failed|expired`。
3. **国内站 / 国际站是两套域名**：MiniMax `api.minimaxi.com` 与 `api.minimax.io`，用户填哪个就用哪个，不硬编码。

## 6. 生成链路：提交即返回，绝不占住对话

视频要 1–5 分钟。**任何"工具调用里同步等"的方案都不成立**——不是慢，是把用户的对话锁死了：

- 工具卡只有一个转圈，用户分不清卡死还是在跑；
- 中途点「停止」→ 云端还在跑、钱已经扣了，本地却什么都拿不到；
- 这 3 分钟里用户既不能发新消息，也不能切问题，只能干等。

**P1 就做成异步任务**（原方案"同步等 300s"已废弃）：

```
video_generate(prompt, ...)                 ← 工具调用只做两件事：建任务 + 提交上游
  ├─ 写 media_tasks 一行（queued）
  ├─ POST provider（拿 remote_task_id）→ 更新为 running
  └─ 立刻返回 { task_id, status: "running" }   ← 毫秒级，对话马上继续

后台 worker（进程内 asyncio，不占对话流）
  └─ 每 10s 轮询上游 → 成功则下载落盘 → 写 file_path、状态 succeeded
       → events.broadcast("media_tasks_changed", {task_id, status})
       → 前端面板/卡片收到事件，就地变成播放器
```

三条护栏：

1. **幂等**：同一会话 60s 内相同 `prompt + params` 直接复用上一个 `task_id`（视频是最贵的生成能力，误触发一次就是真金白银）；**「重试」按钮显式放行**这条限制，否则用户点了重试还是拿到旧任务；
2. **并发上限 2**：超出的留在 `queued`，worker 有空位再拉起。一次提交 5 条不该同时打 5 个任务；
3. **重启可恢复**：启动时把 `queued|running` 的行重新挂上轮询（云端任务保留 7 天，本地丢了还能捞回来）。

**任务表从 P2 提前到 P1**——面板要列进行中的任务，没有表就没有真相。表结构见 §4.4。

**工具返回什么给模型**：一句"已提交"+ `task_id` + 预计时长。模型据此告诉用户"生成中，可以在生成任务里看"，**不许说已完成**（提示词里明确写：拿到 `running` 就别说"已生成"）。

## 7. 生成前的参数确认卡片（A2UI 面板）

用户说「帮我生成一段海边日落的视频」时，时长、比例、分辨率、字幕、口播都没定——**不能拿默认值偷偷生成**（视频按秒计费，且一条 1–3 分钟）。这一节定的是"缺信息时先弹卡"的形态。

### 7.1 什么时候弹、什么时候不弹

| 输入情况 | 行为 |
| --- | --- |
| 关键参数缺失（时长 / 比例 / 分辨率任一未指定） | **弹卡**，预填该模型配置里的默认值 |
| 用户已明确（"5 秒、16:9、1080P"） | **不弹卡**，直接生成（多弹一次等于把一句话的事变成两步） |
| 提到字幕 / 口播 | 弹卡（因为这两项的能力语义要先讲清，见 §7.7） |
| **要图生视频但还没图** | 弹卡，且卡里**自带选图控件**（§7.8）；不要指望用户"先去别处上传再回来点" |

判据写进两处并共用一份常量：`video_brief` 的工具描述 + `_VIDEO_RULES` 提示节。**只写提示词不写工具描述会漏**——模型在工具选择时才读描述。

### 7.2 卡片结构（确定性 IR，不让模型手搓）

新增工具 `video_brief`：只出面板、不生成。面板由服务端按当前**生效视频模型**的能力拼出来，所以**不会出现该模型不支持的选项**（比如不支持 2K 的就不显示 2K、不支持尾帧的就不显示尾帧）。

```
Column
├ Text（小标题）素材来源
├ ChoicePicker  → /form/source         自定义 / 网络抓取（资讯视频，§7.9）
├ TextField     → /form/source_url     资讯页面 URL（选「网络抓取」时必填）
├ Text（说明，muted）单篇文章完整 URL；首页 / 栏目列表 / 搜索结果页不支持
├ Text（小标题）首帧图（选填）
├ FilePicker    → /form/first_frame   「选择图片」+ 已选文件名/缩略图 + 清除
├ Text（小标题）尾帧图（选填，仅 MiniMax 渲染）
├ FilePicker    → /form/last_frame
├ Text（说明，muted）留空=纯文本；只填首帧=图生视频；两张都填=首尾帧
├ Text（小标题）画面比例
├ ChoicePicker  → /form/aspect_ratio   智能 / 1:1 / 4:3 / 3:4 / 16:9 / 9:16 / 21:9
├ Text（小标题）分辨率
├ ChoicePicker  → /form/resolution     480P / 720P / 1080P（按 provider 合法集）
├ Text（小标题）视频时长
├ ChoicePicker  → /form/duration       5s / 10s / 智能
├ Switch        → /form/subtitles      需要字幕（生成 .srt）
├ TextArea      → /form/script         口播文案（可留空）
└ Row
  ├ Button primary「开始生成」 action video_create + context 各项
  └ Button ghost  「取消」     action cancel
```

三个刻意的设计选择：

1. **没有「生成方式」单选框**——A2UI 没有条件渲染（一个字段变化没法让另一块显示/隐藏），加了它就会和下面的上传槽位对不上。改为**按填了几张图推断**：0 张=纯文本、1 张=图生视频、2 张=首尾帧。少一个字段，也少一处状态不一致。
2. **图生视频入口就是 FilePicker 本身**：用户不用先切换模式再找上传框，选图这一步既表达了意图又提供了素材。
3. `data.form` 初值来自 `media_models[active].options`（默认时长/分辨率/比例）；如果用户在本轮之前已经用输入框上传过图片，`video_brief` 会把该附件路径**预填进 `/form/first_frame`**（§7.8 的兜底）。

动作名 `video_create` 登记在 `surface.actions`，按钮的 `context` 用 `[{key, value:{path}}]` 指到 `/form/*`（与 `flight_board` 的「重新查价」同一套写法，不新造协议）。

### 7.3 为什么不用正文选项卡片

`parseOptionsBlock` 那套正文卡片是**单选、单字段、无按钮**的。这里是 4 个字段 + 一个提交动作，只能走 A2UI。

### 7.4 回流闭环

```
用户点「开始生成」
  → POST /api/chat/surface-action（action_id 幂等 60s）
  → context 五个值拼进可见正文：画面比例（16:9）分辨率（1080P）时长（5s）字幕（需要）…
  → 新回合 → 模型直接调 video_generate，**不再弹卡**
```

两条硬规则写进提示词：

1. 收到 `video_create` 回流 → **直接生成**，不许二次确认（用户刚点过）；
2. 生成参数**以面板值为准**，模型不得按自己的偏好改写；只有非法值被适配器裁剪时才在返回里说明"实际用了 720P"。

### 7.5 契约扩展（本方案唯一的前端组件改动）

现有 `ChoicePicker` 是 flex-wrap 胶囊、只有 `label/desc`，做不到截图里"3 列等宽 + 比例图标"的观感；而图生视频需要的**文件选择器在 22 个组件里根本没有**。所以本期要动两处契约：

| 位置 | 改动 |
| --- | --- |
| `app/tools/ui/catalog.py` | ① `ChoicePicker` 增 `columns: int`（默认 0=自动换行）、`options[].icon`；② **新增组件 `FilePicker`**（group=input），props：`label`(必填) / `value`(bindable，绝对路径字符串) / `accept`(枚举 `image｜any`，默认 `image`) / `placeholder` |
| `app/tools/ui/validator.py` | ① `_check_options` 允许的键从 `value/label/desc` 扩到 `+icon`（现在**硬报错**）；② `FilePicker` 的 props 走既有的属性表校验 |
| `divine_catalog.json` | 生成物重跑，漂移守卫会断言 |
| `types.ts` / `parseUISurface.ts` / `registry.tsx` | 三处手工镜像（目录是唯一真源，前端不引 @a2ui）。`parseUISurface.ts::REQUIRED_PROPS` 必须补 `FilePicker: ["label","value"]`——那个 `Record` 是**穷尽**的，漏了 tsc 直接报 |

`icon` 用**封闭枚举**而不是 lucide 名称字符串：`ratio-1-1｜ratio-4-3｜ratio-3-4｜ratio-16-9｜ratio-9-16｜ratio-21-9｜ratio-auto`，前端用 CSS 画矩形（宽度固定、按比例设高度，或反之），不引入任意图标注入。

`FilePicker` 的前端实现要点：按钮触发 `open()` 对话框 → 路径写回绑定 → 组件自己用 `getBinaryPreview` 渲染缩略图（**不复用 `Image` 组件**，它的 url 规则会拒绝绝对路径）。组件保持"值即路径"的单一职责，不负责上传。`accept` 只影响对话框过滤器，真正的类型校验仍在后端（`is_image_path`），前端不做安全判断。

### 7.6 与截图的差异（有意为之）

| 截图 | 本方案 | 原因 |
| --- | --- | --- |
| 选中项蓝紫渐变 | `--color-accent` 14% 混合 + 1px accent 描边 | 项目已收敛为极简黑白，不新引品牌色 |
| 选中有明显外发光 | 不加 | 与现有 `.uis-choice-item.is-active` 保持一致 |
| 3 列固定网格 | `columns: 3`（本面板指定） | 通用组件保持自动换行，按面板按需指定 |

### 7.7 ⚠️ 能力缺口：字幕与口播（必须先说清）

全仓**没有 ffmpeg、没有 TTS**（`grep -rn "ffmpeg|tts"` 只命中本文档）。所以这两项现在只能做到下面这个程度：

| 选项 | P1 真实行为 | 用户看到 |
| --- | --- | --- |
| 字幕 = 需要 | 生成同名 `.srt` 字幕文件（按口播文案/提示词切句），**不烧进画面** | 开关下方小字：「P1 只出 .srt 字幕文件，暂不烧制进画面」 |
| 口播文案 = 有值 | 存同名 `.txt` 旁白稿，并把"需要旁白/对白"写进视频 prompt（H3 原生带音轨） | 输入框 placeholder：「P1 作为旁白稿与生成提示，语音合成在 P2」 |

P2 才做真能力：打包 `ffmpeg-static`（烧字幕 + 混音轨）+ 接 MiniMax `t2a` 合成配音。**不要在 UI 上给一个点了没反应的开关**——这比不做更伤。

**为什么放 P2（2026-11-03 拍板维持，决策 7）**：真正的门槛是 **ffmpeg**，不是 t2a——

1. `ffmpeg-static` 二进制 +30–70MB，且 macOS hardened runtime 下要**重新签名 + 公证**（`publish-macos.sh` 的公证链路要多养一个二进制），不是塞进包就能跑；
2. 真配音 = **t2a + ffmpeg 两件都要**（t2a 出 mp3、视频是 mp4，没 ffmpeg 就 mux 不了）；t2a 按字符计费，一篇资讯文章的配音成本可能超过视频本身，单价还得进配置面；
3. 拉进 P1 的连带改动：`kind=tts` 配置、任务"部分成功"态（视频成了但配音败了）、任务时长 +30–60s——工作量不比任务面板小。

P1 的目标是把「配置 → 生成 → 播放」主干先跑通；字幕/配音是主干之上的增强，主干没验证过就背上双 provider 链路和签名公证，排查面太大。

### 7.8 图生视频：面板必须自带选图控件（原"先去输入框上传"的方案已废弃）

**先认一个错。** 初版写的是「请先在输入框上传首帧图片，上传后再点开始生成」——这句话**做不到**，因为：

```
面板按钮的 context 读的是面板自己的 data（/form/first_frame）
用户在输入框上传图片，只会新增一条消息 + 一个附件
→ 面板的 /form/first_frame 仍然是空
→ 点「开始生成」→ first_frame 为空 → needs_media → 又让用户上传
```

这是一个**死循环**，而且"上传后再回来点"还要求用户滚回去找那块面板。方案作废。

**正确做法：面板内自带文件选择器**（新增 A2UI 组件 `FilePicker`）。

```
Column
├ Text「首帧图（选填）」
├ FilePicker → /form/first_frame    [选择图片]
└ Text「尾帧图（选填，仅 MiniMax 渲染）」
  FilePicker → /form.last_frame
```

| 交互 | 行为 |
| --- | --- |
| 点「选择图片」 | 调 `@tauri-apps/plugin-dialog` 的 `open()`（**依赖已装**：`@tauri-apps/plugin-dialog@^2.7.2` + `tauri-plugin-dialog`；`ChatInput` 的附件选择用的就是它），过滤 png/jpg/jpeg/webp |
| 选完 | 绝对路径写进 `/form/first_frame`；控件下方显示缩略图 + 文件名 + 「移除」 |
| 缩略图怎么来 | 组件内部用 `getBinaryPreview`（Tauri，base64）渲染，**不走 `Image` 组件**——`Image` 的 `url` 明确拒绝绝对路径 / `data:` / `file:`，走它会直接被校验拦下 |
| 只填首帧 | 图生视频 |
| 首尾都填 | 首尾帧（智谱不支持 → 面板根本不渲染尾帧这一行） |
| 都不填 | 纯文本 |

**兜底两条**（覆盖用户就是习惯先在输入框传图的场景）：

1. 若本轮之前用户已用输入框上传过图片，`video_brief` 把它**预填进 `/form/first_frame`**，面板上直接显示那一张，用户只差一个「开始生成」；
2. 仍然保留 `needs_media` 作为最后一道闸：真没图就提交时**不扣费**，正文说「还差一张首帧图」，并**重新弹一次卡**（带同一个附件路径），别让用户自己去翻旧面板。

**provider 能力差异**（面板据此决定渲染哪些行，实现时按各家官方文档复核一次）：

| 后端 | 纯文本 | 首帧 | 首尾帧 |
| --- | --- | --- | --- |
| MiniMax H3 系 | ✅ | ✅ | ✅（`role=first_frame` / `last_frame`） |
| 智谱 CogVideoX | ✅ | ✅ | ❌（只接首帧） |

**四个实现约束**（写进代码注释，别靠记性）：

1. `video_generate` 必须声明 `allow_external_paths = True`，否则用户从桌面选进来的绝对路径会被路径守卫拦掉（`image_generate` 的 `reference_image` 是同一处理）；
2. `FilePicker` 的值是**绝对路径**，落库后回放仍然可用；但换机器/删文件会失效 → 面板回放时若文件不存在，显示「图片已失效，请重新选择」，不要画一个碎图；
3. 传图前压缩到 provider 上限（MiniMax 单文件 ≤ 30MB），超大图先缩到长边 1920 再转 base64——**直接抛"文件过大"不如自动缩一次**；
4. 传图前校验存在且是图片（`is_image_path`），否则报「首帧必须是图片」。

### 7.9 素材来源：资讯视频（网络抓取 / 自定义）

用户给一篇资讯文章的 URL，让 AI 抓取正文、提炼要点、生成一条讲解视频。截图参考（资讯视频创作：网络抓取 / 自定义两个 tab）的交互意图保留，**形态改掉**——A2UI 没有 tab 容器、也没有条件渲染（§7.2 同一个教训），所以面板上是**两个常驻字段 + 校验兜底**：

| 字段 | 说明 |
| --- | --- |
| 素材来源 `ChoicePicker` | 自定义（默认）/ 网络抓取 |
| 资讯页面 URL `TextField` | 选「网络抓取」时必填；提示条写明**单篇文章完整 URL，首页 / 栏目列表 / 搜索结果页不支持** |

**抓取不新造工具**：回流 `source=article` 后，模型先调**既有的 `web_fetch`** 提正文，再提炼成 prompt + 口播稿，然后 `video_generate`。整条链路：

```
用户贴 URL → 点「开始生成」
  → video_create 回流（source=article, source_url=…）
  → 模型 web_fetch(url) 提正文
      ├─ 拿到文章 → 提炼 15s 内讲得完的要点 → prompt + voiceover → video_generate
      └─ 抓不到 / 不是单篇文章 → 不提交任务（未扣费），正文说明原因，
         建议改「自定义」把正文直接粘进来
```

**四条硬规则**（写进 `_VIDEO_RULES` 与工具描述）：

1. **URL 有效性在抓取后判定**，不在面板上假装校验：判据是"取到标题 + 正文 ≥ 200 字"；正文极短、链接密度高（首页/栏目页/搜索页特征）→ 按"不是单篇文章"处理；
2. **时长红线**：单条视频上限 15s（MiniMax H3 4–15s / 智谱 5s·10s）。所以资讯视频是**摘要式短视频**——只提炼 3–5 个要点讲完，"把整篇报道做成视频"需要多段生成 + 剪辑管线，明确告知 P2 之前不做；
3. **提炼改写，不逐句复制**：提示词里约束"用自己的话讲"，原文进旁白稿仅作事实来源；
4. **失败语义**：`source=article` 但 URL 为空 → `needs_source`（重新弹卡）；`web_fetch` 失败 → 不提交生成任务，说明原因并建议改「自定义」。

**能力边界（对用户如实说）**：P1 没有 TTS（§7.7），资讯视频产出的是**带 .srt 字幕与旁白稿的短视频**，声音来自 provider 原生音轨（H3 支持音频提示）而非朗读旁白；真"新闻播报腔"要等 P2 接配音。字幕与抓取没有默认联动（A2UI 无条件渲染），面板提示条写「资讯视频建议勾选字幕」。

### 7.10 预估费用（2026-11-03 拍板：要显示）

难点是**价格从哪来**：三家按模型/档位计价且随时调价，硬编码价格表必然过期。所以单价**由用户填**，不内置：

```
media_models[video].options.price_per_second: number   // 每秒单价（元），选填
```

| 位置 | 显示 |
| --- | --- |
| 参数卡片：时长选项 | 每个时长档的 `desc` 带预估（`5s ≈ ¥0.35`）——ChoicePicker 原生支持 desc，改时长即看对应档位的价格 |
| 参数卡片底部 | caption：「单价来自生成模型配置，实际以账单为准」 |
| 工具卡 / 任务面板 | 提交后显示「预估 ¥x.x」（duration × 单价，worker 算好随任务下发） |

三条规则：

1. **未配置单价 → 整套费用展示静默缺席**（面板 desc 不带价格、任务行不显示金额），正文只提"按时长计费"——空值不能显示成 `¥0`，那是在撒谎；
2. 预估**只算时长**：分辨率/比例是否加价各家不同，不猜，caption 说明"实际以账单为准"；
3. 价格变动**不自动同步**：用户自己改配置里的单价；设置页该项旁边给一句"单价请按服务商最新价格表填写"。

## 8. 预览播放（本方案的技术核心）

### 8.1 后端：加一个支持 Range 的媒体端点

```python
# app/api/files.py
@router.get("/media")
def media_file(path: str):
    target = _resolve_allowed_path(path)   # 复用 /files/image 的白名单根校验
    return FileResponse(target, headers={"Cache-Control": "private, max-age=0"})
```

已验证本机 `starlette 1.6.0` 的 `FileResponse` **原生支持 Range**（源码含 range 处理），所以 `<video>` 能拖进度条、能边下边播，不需要自己写分片。

为什么不复用 `tauri get_binary_preview`：它把整个文件 base64 进内存，25MB 上限 + 无法流式，视频这条路走不通。

### 8.2 前端：两处播放器，一个组件

```
ToolStatusCard（消息内联）           FilePreviewPanel（侧栏预览）
   video_generate 成功后              点击 .mp4 / 视频文件
        ↓                                    ↓
        └──────── <VideoPlayer src=...> ─────┘
```

- 新增 `components/VideoPlayer`：`<video controls preload="metadata" playsInline>`，容器按比例自适应（9:16 竖屏限高 420px）；
- `BinaryPreview.tsx`：`PREVIEWABLE_EXTENSIONS` 加 `mp4/webm/mov/m4v`，并**先于** base64 分支判断 —— 视频分支走 `/files/media?path=`，不读 base64；
- `ToolStatusCard` 里对 `tool.tool === "video_generate"` 的卡片：**提交后显示任务进度**（从全局 store 按 `task_id` 取），完成后再换成播放器——注意结果不是工具返回值里带的，是任务完成后才有的（§6/§9.3）；
- 切文件 / 关闭面板时 `video.pause()` 并置 `src=""`，否则会出现"关了预览还在响"；
- `FileTypeIcon` 已支持 `video` 档（`kinds.ts` 已有 mp4/mov/webm），无需改。

### 8.3 CSP 必改（否则页面里根本播不了）

```jsonc
"csp": "default-src 'self'; script-src 'self' 'unsafe-inline';
        connect-src http://127.0.0.1:8019 https://api.deepseek.com;
        style-src 'self' 'unsafe-inline';
        img-src 'self' data: http://127.0.0.1:8019;
        media-src 'self' blob: data: http://127.0.0.1:8019;
        object-src 'none'"
```

`blob:` 留给"内存里刚生成、还没落盘"的临时预览；`data:` 留给历史消息里的短片段。这条不加，`<video>` 会静默失败（控制台一条 CSP 报错，界面一片黑）。

## 9. 生成任务面板（用户在等，但不能干等）

### 9.1 入口与位置

左侧导航新增一项「生成任务」，与「任务」「技能」同级——现有实现就是 `tasksOpen` / `skillsOpen` 这类状态切换主区域（`pages/chat/index.tsx`），加一个 `mediaOpen` 即可，**不需要新增路由**（`app/router.tsx` 里只有 `/chat` 一条）。

- 入口右侧带**进行中数量徽标**，0 时不显示；面板没打开时，这个徽标就是"有新东西"的唯一提示；
- 备选方案是右侧抽屉，否决：抽屉和文件预览面板抢同一块空间，而"等视频"恰恰应该允许用户同时看别的。

### 9.2 面板结构

```
生成任务                              进行中 2 · 今日完成 5
├ 进行中
│  ├ 海边日落…        生成中 01:23 · 预估 ¥0.35 · 5s/720P/16:9     [不再等待]
│  └ 城市夜景…        排队中（并发 2/2）· 5s/720P/9:16             [不再等待]
└ 已完成（今天）
   ├ 山间晨雾.mp4     5s/1080P · 10:42 完成     [播放] [在对话中查看] [另存为]
   └ 猫.mp4           失败：内容审核拒绝          [重试] [删除]
```

每行三块：**缩略/占位**、**prompt 摘要（单行截断）+ 参数 chips**、**状态与操作**。操作按状态给，不给一堆永远灰着的按钮：

| 状态 | 操作 |
| --- | --- |
| 排队中 | 不再等待 |
| 生成中 | 不再等待（**确认文案：云端仍会跑完、费用已产生，稍后可以回来取**——说"已取消"是撒谎，任务无法真正中止） |
| 已完成 | 播放 / 在对话中查看（跳到那次会话）/ 另存为 / 删除 |
| 失败 | 重试（同参数重提，**显式绕过 60s 幂等**）/ 看原因 / 删除 |
| 已过期 | 重试 |

### 9.3 数据与刷新

- `GET /api/media/tasks?status=active|done&limit=`，默认返回「进行中 + 今日完成」；
- 状态变化由后端广播：`events.broadcast("media_tasks_changed", {task_id, status})`——与 `scheduled_tasks` 用的同一条全局事件流（`app/api/events.py`，15s 心跳）；
- 兜底：事件断线时 20s 轮询一次；重新进入页面直接全量拉。

**一份 store 供三处消费**：任务面板、对话里的工具卡、侧栏徽标。三处各自拉数据必然打架（面板显示完成、卡片还在转圈）。

### 9.4 完成时怎么让用户知道

1. 面板条目就地变为可播放（缩略图 + 时长）；
2. 全局 toast：「视频已生成」+ 一个「查看」；
3. 系统通知（复用 `@tauri-apps/plugin-notification`，与定时任务同一套权限流程）——用户切到别的应用时也能知道；
4. 对话里的卡片**同步**变播放器（同一个 store），切回来就能看，不用回面板找。

### 9.5 与对话的关系

- 工具卡不再等结果：提交后显示「已提交生成任务」+ 实时进度（从 store 取），该回合立刻结束；
- 历史回放：卡片按 `task_id` 从 `media_tasks` 取 `file_path` → 文件在就地播，文件被删则显示「文件已删除」；
- **刻意不做**「完成后往会话里插一条消息」：那会让对话出现用户没说过、模型没答过的内容。状态变化由卡片自己表达就够了。

### 9.6 并发与清理

- 并发上限 2（设置项 `video_concurrency`，默认 2），超出的排队。一次提交 5 条不该同时打 5 个任务；
- 面板保留最近 30 天，更早的折叠起来（不是删）；
- 视频文件**不自动删**——删用户文件比占磁盘更糟。给「打开所在目录」，P2 再讨论过期清理提示。

## 10. 设置 UI

**新增独立分区「生成模型」**（左侧导航 `Film` 图标），而不是塞进「模型」页——理由：聊天模型与生成模型的字段语义不同（前者要比价、切默认、算 token；后者要选时长/分辨率/比例），混在一起会让"视频模型出现在对话切换器里"这个错误再次发生。

页面结构：

```
生成模型
├─ 视频   [ + 添加 ]
│   ├─ MiniMax 海螺          默认   ✓ 已连通
│   │   供应商 [MiniMax ▾]  模型 [MiniMax-H3]
│   │   API Key [••••••]  默认时长 [5s]  分辨率 [720P]  比例 [16:9]
│   │   每秒单价 [¥0.07]（选填；用于预估费用，请按服务商最新价格表填写）
│   └─ ...
└─ 图像   （P2：把 image_generate 的 key 从聊天模型中迁出）
```

- 供应商下拉内置三家 + 自定义；选中后自动回填 `base_url` 与模型候选；
- 这里配的**默认时长/分辨率/比例会预填到参数卡片**（§7.2），所以用户点一次「开始生成」就能跑；
- 分辨率候选按 provider 的合法集裁剪，面板里不会出现该模型不支持的档位；
- 「测试连通性」按钮只在服务端做一次 `GET /api/media/health`（发一个不存在的最小查询），**不实际提交生成任务**——测试按钮扣费是不可接受的；
- 每个 kind 只允许一个 `active`；只有一个时工具不需要 `model_id`。

## 11. 错误、成本与安全

**错误映射**（沿用 006 的原则：界面只给人话，原文进日志）：

| 上游 | 用户看到 |
| --- | --- |
| 401 / invalid api key | 视频模型的 API Key 无效，请在「设置 → 生成模型」检查 |
| 429 / quota | 视频生成额度不足或触发限流，请稍后再试 |
| 内容审核拒绝 | 这个描述被内容审核拒绝，换个说法再试 |
| 任务过期 / expired | 生成任务已过期（云端只保留 7 天），请重新生成 |
| 超时 | 视频还在云端生成，请稍后重试（不要重复提交） |

**成本护栏（P1 必做三条）**

1. 幂等：同会话 60s 内相同参数不重复提交（§6）；
2. 默认参数封顶：`duration` 上限取 provider 支持的最大值，但**默认取最短档**（MiniMax 4s / 智谱 5s / 万相 5s），不让模型"顺手"生成 15s；
3. **预估费用可见**（§7.10）：单价由用户在生成模型配置里填（`price_per_second`），面板时长档 desc / 任务面板 / 工具卡三处显示「预估 ¥x」；未配置单价则整套费用展示静默缺席，**空值绝不显示成 ¥0**。

P2 可加"提交前确认"（复用 `confirm_type` 机制），但本期先不做——一次确认弹窗会把"让它帮我生成个视频"的多轮体验切碎。

**安全**：key 与现有 `models[].api_key` 同等处理（存 `settings.json` 明文、GET 掩码、不写日志）。不新增加密方案，避免出现"图像加密、视频不加密"的割裂。

## 12. 实施拆解

| 阶段 | 内容 | 涉及文件 |
| --- | --- | --- |
| **P1-a 契约** | `media_models` 读写 + 掩码 + 合并 | `config.py`、`schemas.py`、`api/settings.py` |
| **P1-b 适配层** | **两家** provider 归一（提交/轮询/下载/图生视频参数） | `app/media/providers/{minimax,zhipu}.py`（新）、`app/media/service.py`（新） |
| **P1-c 工具** | `video_generate` 适配器（含 `mode/first_frame/last_frame` + `needs_media` 校验）+ 意图 `video` + 提示词节 | `tools/adapters/video_generate.py`（新）、`agent/intent/intent.py`、`agent/tools/tools.py`、`agent/core/prompt_sections.py` |
| **P1-c2 参数卡片** | `video_brief` 工具（确定性 IR）+ `video_create` 动作回流 + 契约扩展：`ChoicePicker` 加 `columns/icon`、**新增 `FilePicker`** | `tools/adapters/video_brief.py`（新）、`tools/ui/catalog.py`、`tools/ui/validator.py`、`divine_catalog.json`、`types.ts`、`parseUISurface.ts`、`registry.tsx` |
| **P1-d 预览** | `/api/files/media`（Range，无 attachment）+ `videos` 加入 `ALLOWED_CATEGORIES`（下载出口）+ `VideoPlayer` + `BinaryPreview` 分支 + CSP | `api/files.py`、`components/VideoPlayer/*`（新）、`FilePreviewPanel/BinaryPreview.tsx`、`tauri.conf.json` |
| **P1-e 设置 UI** | 「生成模型」分区 | `SettingsModal/MediaSection.tsx`（新）、`index.tsx`、`types.ts`、i18n ×3 |
| **P1-f 任务表与 worker** | `media_tasks` 建表 + 提交/查状态/下载 + 后台轮询（并发 2）+ 重启恢复 + `events.broadcast("media_tasks_changed")` + `GET /api/media/tasks` | `db/migrations.py`、`db/media_tasks.py`（新）、`app/media/service.py`（新）、`api/media.py`（新）✅ 已实施 |
| **P1-g 任务面板** | 侧栏新增「生成任务」（`mediaOpen`）+ 列表/状态/操作 + 全局 store + 侧栏徽标 + 完成 toast/系统通知 | `pages/media/index.tsx`（新）、`pages/chat/index.tsx`、`services/mediaTasks.ts`（新）、i18n ×3 |
| **P2** | 图像模型迁移到 `media_models` + 过期清理提示 + 队列排序 | `api/settings.py`、设置 UI 图像组 |

**验收标准（P1）**

1. 设置里配一个视频模型 → 保存后重开设置，key 显示为掩码且能测出"已连通"；
2. 对话里说「帮我生成一段海边日落的视频」（不带参数）→ **先出参数卡片**，默认值已按配置预填；点「开始生成」→ 不再二次确认，直接进入生成；
3. 说「生成一段 5 秒 16:9 1080P 的海边日落视频」（参数齐全）→ **不弹卡**，直接生成；
4. **提交后 1 秒内该回合结束**：工具卡显示「已提交」，用户可以立刻发下一条消息，不被阻塞；
5. 侧栏「生成任务」出现该任务（生成中 + 已用时）→ 完成后条目变为可播放，toast 提示，对话里的卡片同步变播放器；
6. 该文件出现在文件树 `videos/` 下，点击后侧栏预览同样能播；需要字幕时会同时出现同名 `.srt`；
7. **图生视频在面板内完成**：点「选择图片」弹出系统对话框 → 选中后显示缩略图与文件名 → 点「开始生成」一次成功；全程不需要去输入框传图、不需要回来点第二次；
8. 智谱模型的面板里**没有尾帧这一行**（能力差异反映在面板上，不是点了才报错）；
9. 选中的图片被删掉后再打开该面板 → 显示「图片已失效，请重新选择」，不是碎图；
10. 把 key 改错 → 报"API Key 无效"，**不出现**上游原始 JSON；
11. 产物是本地文件：点「打开所在目录」能定位到 `videos/` 下的 mp4；「另存为」能存到桌面并正常播放；**消息里不出现 provider 的临时 URL**；
12. 生成中重启 app → 任务仍在面板里（状态从库里读），完成后仍能取回视频；
13. **资讯视频**：面板选「网络抓取」贴一篇单篇文章 URL → 回流后先抓正文再提交任务，`.srt` 与旁白稿同时落盘；贴首页或搜索结果页 → 不提交任务，正文说明"不是单篇文章"并建议改「自定义」；
14. 生成模型配置了 `price_per_second` → 时长档位 desc 显示「≈¥x」、任务面板行显示预估金额；**未配置单价 → 三处费用展示全部缺席**，不出现 ¥0；
15. 未配置任何视频模型时，工具返回明确引导，不崩、不静默。

**已知风险**

| 风险 | 说明 | 应对 |
| --- | --- | --- |
| worker 与对话流抢事件循环 | 轮询是 IO 密集（httpx await），但下载 20MB 文件会占带宽/CPU | 下载走 `asyncio.to_thread` 或流式写盘；并发限 2 |
| 后台任务丢了没人管 | app 在生成中途退出 | `queued|running` 的行在启动时重新挂轮询（§6 护栏 3），状态从库里恢复 |
| 视频体积顶到磁盘 | 2K 单条可 20MB+，不做清理会越积越多 | 落盘命名带日期；面板给「打开所在目录」；P2 加过期提示 |
| 模型乱填参数 | 各家时长/分辨率合法集不同，模型不一定知道 | 适配器做**静默裁剪**（就近取合法值）并在返回 message 里写明实际参数 |
| sidecar 需重建 | 后端改动是 Python 二进制，不热更 | 与既有流程一致：`./build-sidecar.sh` + 重启 |

---

## 13. 决策记录与剩余待定

### 13.1 已定（2026-11-03）

| # | 决策 | 影响 |
| --- | --- | --- |
| 1 | **P1 只做 MiniMax + 智谱**，DashScope 留接口位不实现 | §5 只写两家；`providers/` 目录先建两个文件 |
| 2 | **图生视频要做**：首帧 / 尾帧，纯文本也要 | 面板多两行「首帧图 / 尾帧图」`FilePicker`（**新增组件**，§7.5）；`video_generate` 多 `first_frame/last_frame`，`mode` 按填了几张推断；缺图走 `needs_media` 并重新弹卡（§7.8） |
| 3 | **比例图标要，用 CSS 绘制** | `ChoicePicker` 的 `icon` 枚举由前端画矩形（不引 lucide、不接任意图标名），契约改动见 §7.5 |
| 4 | **生成不能占住对话**：提交即返回，另做「生成任务」面板 | §6 全节改为异步任务（原「同步等 300s」废弃）；`media_tasks` 表从 P2 提前到 P1；新增 §9 面板与 worker；侧栏多一个入口 |
| 5 | **资讯视频**：面板加「素材来源」（网络抓取 / 自定义），抓取用既有 `web_fetch` | §7.9；`video_generate` 多 `source/source_url`；单条 ≤15s 的摘要式短视频；抓取失败不扣费并建议改自定义 |
| 6 | **取消措辞按建议**：按钮写「不再等待」，确认说明云端仍会跑完 | §9.2 进行中行操作改「不再等待」；确认文案含「云端仍会跑完，稍后可以回来取」 |
| 7 | **字幕 / 口播按 §7.7 边界**：P1 只出 `.srt` + 旁白稿 | 不打包 `ffmpeg-static`；真烧制/真配音留到 P2 再议 |
| 8 | **显示预估费用** | §7.10 新增：单价来自生成模型配置（`options.price_per_second`，用户自填），面板时长选项 desc 带预估、任务面板与工具卡显示「预估 ¥x」；未配置单价则不显示，正文只提「按时长计费」 |

### 13.2 剩余待定

全部已拍板，无遗留。（历史：本节曾列取消措辞 / 字幕口播边界 / 预估费用三项，2026-11-03 已分别落为上表 6 / 7 / 8。）
