# 009 · 代码任务期间应用整体冻结（彩虹转圈）根因诊断（2026-09-15）

> 编号：009 ｜ 类型：review ｜ 日期：2026-09-15 ｜ 状态：**已定位根因并修复（见 §四）**
> 现象：执行代码类工具任务时整个应用卡死，鼠标移入出现 macOS 彩虹转圈（beachball）

---

## 一、结论

**不是「工具卡片太多导致渲染性能问题」。** 根因在 Tauri 侧：

`get_file_tree` / `get_dir_children` 是**同步** Tauri 命令（跑在主线程），
而它们调用的 `scan_dir()` 对**每个目录条目**起一个 `git check-ignore` 子进程。
一个 24 条目的目录 = 24 次串行进程启动 ≈ **1.5 秒主线程阻塞**。

代码任务会连续写/改多个文件，触发文件监听 → 无防抖地重复整轮树刷新 → 主线程被反复长时间占用
→ 整个应用冻结 + 彩虹转圈。

**「彩虹转圈」这个细节是决定性的**：它表示主线程被阻塞。DOM 节点过多只会造成滚动掉帧，
不会让应用整体失去响应——这是两类完全不同的问题。

---

## 二、为什么可以排除「卡片太多」

### 2.1 代码类工具卡片是被合并的

`divine-app/src/pages/chat/components/MessageItem/MessageHelpers.tsx:54` 的 `GROUPABLE_TOOLS`
白名单**包含全部代码类工具**：

```
read_file, edit_files, edit_lines, apply_patch, terminal, run_tests, lint_check,
format_code, grep_files, search_files, glob_files, directory_tree, write_file,
move_file, git_status, git_diff, git_log, git_commit, ...
```

同一工具类型的多次调用合并为**一张**卡（`count` 记录次数）。
**11 次 `edit_files` 最终是一张卡，不是 11 张。**

### 2.2 渲染链路已做过系统优化，且有效

| 项 | 位置 |
| --- | --- |
| 虚拟滚动 | `MessageList/index.tsx:68` `@tanstack/react-virtual`，`overscan: 12` |
| 消息级 memo | `MessageItem/index.tsx:53` |
| 工具卡 memo | `ToolStatusCard` / `TracePanel` / `ToolFileList` / `UserMentionText` |
| 状态更新粒度 | `chatUtils.ts:129 upsertTool` 只替换命中项，其余保持对象引用（memo 不被击穿） |
| 文件列表 | 折叠时最多 6 条（`ToolFileList.tsx:34`） |
| diff | 默认折叠 + 600 行封顶（`DiffView.tsx:14,39`） |
| shiki token | rAF 攒批（`HighlightedCode.tsx:108`） |
| SSE 文本增量 | rAF 攒批（`streamBuffer.ts`） |
| 滚动状态 | rAF 合并提交（`MessageList/index.tsx:116`） |

`docs/design/016-streaming-performance-20260904.md` 列出的 B1–B6 六个瓶颈**全部已实现**
（该文档头部状态「未实施」已陈旧，应更新）。

### 2.3 后端也没有阻塞

- `tools/base.py:149` 用 `loop.run_in_executor` 执行同步 subprocess，**不阻塞事件循环**
- `terminal.py` **不发进度事件**（仅 `web_fetch_batch` 声明 `supports_progress`），
  跑 pytest / ruff / tsc 只产生 **1 个** SSE 事件，不是事件洪水
- SSE 服务端已做文本攒批（`agent/core/sse.py:262`，B6）

---

## 三、根因证据链

### 3.1 每个目录条目起一个 git 子进程

`divine-app/src-tauri/src/commands/workspace.rs:81`

```rust
fn is_git_ignored(root: &Path, path: &Path) -> bool {
    Command::new("git")
        .arg("-C").arg(root)
        .arg("check-ignore").arg("-q").arg("--").arg(path)
        .stdout(Stdio::null()).stderr(Stdio::null())
        .status()                                  // ← 一个条目一次进程启动
        .map(|status| status.success())
        .unwrap_or(false)
}
```

被 `scan_dir()`（同文件 :96）的 `filter_entry` 对**每个条目**调用（:111）：

```rust
let git_aware = run_git(root, &["rev-parse", "--is-inside-work-tree"])...;  // 每目录又一次进程
for entry in WalkDir::new(root).min_depth(1).max_depth(1).into_iter()
    .filter_entry(|entry| {
        ...
        !should_ignore(&name)
            && (!git_aware || !is_git_ignored(root, entry.path()))            // ← N 次进程
    })
```

### 3.2 这些命令是同步的 → 跑在主线程

`workspace.rs` 中全部为 `pub fn`（非 `pub async fn`）：

| 行 | 命令 |
| --- | --- |
| 239 | `get_binary_preview` |
| 260 | `get_file_tree` |
| 271 | `get_dir_children` |
| 294 | `get_file_diff` |
| 391 | `get_external_file_preview` |
| 422 | `watch_workspace` |
| 468 | `unwatch_workspace` |

Tauri 2 的同步命令在主线程执行（异步命令才走线程池）。**递归/遍历型 I/O 命令同步化 = 主线程阻塞。**

### 3.3 文件监听无防抖，把单次阻塞放大成连续阻塞

`divine-app/src/pages/chat/components/FilePreviewPanel/FileTree.tsx:192`

```tsx
void listenWorkspaceChanges((payload) => {
  ...
  if (segments.includes(".git")) return;
  if (changed.endsWith(".DS_Store")) return;
  ...
  treeCache.delete(repoPath);
  dirCache.clear();          // ← 清空全部目录缓存
  load();                    // ← 立即重载整棵树，无防抖
});
```

代码注释显示已踩过同类坑（`.git/index` 被 git status 刷新导致文件树误刷新、页面跳动），
但当时只加了 `.git` / `.DS_Store` 过滤，**没有加防抖**。

### 3.4 实测数据（本机）

| 项 | 耗时 |
| --- | --- |
| 单次 `git check-ignore` | **64 ms** |
| 30 次串行 `git check-ignore` | **1.920 s** |
| `git check-ignore --stdin` 批量 30 条 | **0.062 s**（约 **31×**） |
| 仓库根目录条目数 | 24 → 单次 `scan_dir` ≈ **1.5 s 主线程阻塞** |

**放大效应**：代码任务改 11 个文件 → 十余轮树刷新 → 每轮阻塞主线程 1–3 s。

---

## 四、修复（已实施）

### 4.1 批量 `git check-ignore`（收益最大）✅

`divine-app/src-tauri/src/commands/workspace.rs`

- 删除 `is_git_ignored(root, path)`（每条目一次进程），新增 `git_ignored_set(root, rel_paths)`：
  走 `git check-ignore --stdin`，一次进程处理整个目录的条目，读 stdout 得到被忽略集合。
  （批量模式不能用 `-q`，那会吞掉 stdout；写完 stdin 必须显式 drop 才能让 git 读到 EOF。）
- `scan_dir()` 由「边遍历边过滤」改为两趟：第一趟只做本地名称过滤并收集条目（零进程开销），
  第二趟整目录一次性问 git。

**实测（真实项目根目录，19 个条目）**：

| 实现 | 耗时 |
| --- | --- |
| 旧（逐条目） | **150.7 ms** |
| 新（批量） | **6.5 ms** |
| 提速 | **23.2×**，每次目录扫描省 144 ms |

**等价性验证**：在临时 git 仓库（覆盖被忽略文件 / 被忽略目录 / 未忽略文件 / 含空格文件名 /
子目录自有忽略规则）上，对**根目录、子目录、被忽略目录**三层分别跑新旧两种实现，结果**逐项完全一致**。

### 4.2 命令移出主线程 ✅

以下命令由同步 `pub fn` 改为 `pub async fn` + `tauri::async_runtime::spawn_blocking`：

| 命令 | 说明 |
| --- | --- |
| `get_file_tree` | 目录遍历 + git 忽略查询 |
| `get_dir_children` | 同上（展开目录） |
| `get_file_diff` | 读文件 + `git show`/`git diff`（抽出 `build_file_diff` 同步体） |
| `get_binary_preview` | 读整文件 + base64 编码 |
| `get_external_file_preview` | 读外部文件 |

Tauri 的同步命令在主线程执行，异步命令走运行时线程池；重 I/O 一律用 `spawn_blocking`
落到阻塞线程池，既不占主线程也不占 tokio worker。

> `watch_workspace` / `unwatch_workspace` 保持同步——它们只是注册/注销 watcher，开销可忽略。

### 4.3 文件监听加防抖 ✅

`divine-app/src/pages/chat/components/FilePreviewPanel/FileTree.tsx`

新增模块常量 `WORKSPACE_RELOAD_DEBOUNCE_MS = 200`，`workspace:changed` 处理改为：
命中过滤条件后不立刻重载，而是重置一个 200ms 定时器；窗口内的连续变更合并为**一次**
`treeCache.delete()` + `dirCache.clear()` + `load()`。组件卸载时清理定时器。

### 4.4 验证结果

| 项 | 结果 |
| --- | --- |
| `cargo check` | **通过**（`Checking ai-divine-desktop` → `Finished`，无 error/warning） |
| 批量 vs 逐条目等价性 | 三层目录逐项一致 ✓ |
| 实测提速 | 150.7 ms → 6.5 ms（23.2×） |
| 前端 `eslint`（改动文件） | 0 错误 |
| 前端 `prettier --check` | 通过 |
| 前端 `tsc -b` | 报 2 个错误，**均在 `src/services/skills.ts`**（未被本次改动触及，属既有问题） |

> 修复只影响**文件树刷新路径**，不改任何面向用户的行为：同一份忽略规则、同一份树结构、
> 同一份缓存失效语义，只是不再逐条目起进程、不再占主线程、不再一变更就全量重载。

### 4.5 遗留（未处理）

`scan_dir` 里每个目录还会跑一次 `run_git(root, ["rev-parse", "--is-inside-work-tree"])`。
单次开销远小于原先的 N 次 `check-ignore`，暂未合并；若后续要再压，可在 `get_file_tree` /
`get_dir_children` 入口算一次 `git_aware` 后向下传递。

---

## 五、另一处独立发现：工具进程启动开销（已修复）

工具每次调用新起 Python 进程（`tools/base.py:154` → `[sys.executable, script]`）。
实测 `read_file.py` 端到端 **3.518 s**（三次 3.75 / 3.46 / 3.34），而裸 Python 启动只要 0.034 s。

`-X importtime` 定位到唯一元凶：

```
import time:  4028 | 3473811 | app.document_reader
import time:    8 | 2954207 |   langchain_core.load.serializable   ← 单模块 2.95s
```

`app/document_reader.py:6` 把 `langchain_community.document_loaders`（`CSVLoader` / `PyPDFLoader` /
`TextLoader`）放在**模块顶层**导入，而文件里其他重依赖（`anydoc` / `docx` / `openpyxl` / `pptx`）
都已经是函数内延迟导入——它是唯一的例外。

### 修复

`divine-server/app/document_reader.py`

1. **删掉顶层 langchain 导入**，改为在 `_read_file_text_legacy` 内延迟导入。
2. **纯文本类不再走 langchain**：原 `else: TextLoader(...)` 分支改为直接 `path.read_text("utf-8")`。
   `TextLoader` 只是「读文件 + 包成 Document」的薄封装，而它拖来的整条 langchain 依赖要 ~3s。
   覆盖 `.txt` / `.md` / 代码文件等**读文件最常用的场景**。
3. `.csv` / `.pdf` 仍走 `CSVLoader` / `PyPDFLoader`（延迟导入），行为不变。

### 验证

| 项 | 结果 |
| --- | --- |
| `read_file.py` 启动 | **3.518 s → 0.044 s（80×）** |
| 内容正确性 | `requirements.txt` / `run.py` / `app/document_reader.py` / `read_file.py` 四个文件，去掉行号前缀后与原文**逐字符一致** |
| `.csv`（langchain `CSVLoader`） | 正常返回 `name: Alice / score: 90 …` |
| `.txt` / 无扩展名 | 正常返回原文 |
| 其他常用工具启动 | `search_files` 0.054s、`glob_files` 0.144s、`terminal` 0.152s、`directory_tree` 0.162s、`grep_files` 0.180s —— `read_file` 此前是**唯一**的异类 |

> 影响面：一次代码任务若有 20 次 `read_file`，此前要白付约 **69 秒**启动开销。
> 这只影响任务速度，与 §一 的界面冻结无关（后者是主线程被 Tauri 同步命令阻塞）。

---

## 六、环境备注（含一个会阻断测试的环境问题）

### 6.1 Xcode 许可未同步升级 → `/usr/bin/git` 拒跑（需你处理）

排查中发现 `/usr/bin/git` 直接报错：

```
You have not agreed to the Xcode license agreements.
```

根因不是权限问题，而是**版本不匹配**：

| 项 | 值 |
| --- | --- |
| 已安装 Xcode | **27.0**（Build 27A266a） |
| 许可已同意的版本 | **26.6**（`/Library/Preferences/com.apple.dt.Xcode.plist` 的 `IDEXcodeVersionForAgreedToGMLicense`） |

Xcode 从 26.6 升到 27.0 后，macOS 要求重新同意许可；Apple 自带的 `/usr/bin/git` 会检查该许可，于是全部 git 调用被拒。

**影响**：`pytest tests/` 里有 **13 个 git 相关用例**因此报错（`test_git_tools.py` 11 个、`test_code_review.py` 2 个），
另加 `test_git_tools.py::test_not_a_repo` 因为拿到的是许可报错而非「不是 git 仓库」而断言失败。

**修复**（需要你执行，需 sudo）：

```bash
sudo xcodebuild -license accept
```

**绕过**（命令行临时用）：`/opt/homebrew/bin/git`（本机已装，2.54.0，不受 Xcode 许可影响）。

### 6.2 其他

- Rust 工具链**已安装**在 `~/.cargo/bin`（cargo 1.97.1 / rustc 1.97.1），只是不在默认 PATH 中；
  `src-tauri/target/` 有约 27 GB 预热缓存，`cargo check` 增量检查约 1–2 秒。修复即在此环境下验证通过。
- 前端 `tsc` / `eslint` / `prettier` 可用（`divine-app/node_modules/.bin/`）。

### 6.3 本次全量测试结果

```
1305 passed, 4 failed, 12 errors, 3 skipped
```

**16 个失败/报错全部为环境因素，与本次改动无关**：

| 类别 | 数量 | 原因 |
| --- | --- | --- |
| git 相关（`test_git_tools` / `test_code_review`） | 13 | Xcode 许可（见 6.1） |
| `test_react.py` | 3 | 沙箱 `PermissionError: EEXIST ... mkdir .../workspace` |

文件读取 / 工具相关用例**全部通过**（通过数由修改前的 1274 升至 1305）。
