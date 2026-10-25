# Divine

[简体中文](README.md) · **English**

Divine: a local-first, privacy-controllable desktop AI assistant. FastAPI sidecar backend, Vite + React + TypeScript frontend, Tauri 2 + Rust desktop shell.

Default ports:

| Service                 | Port   | Notes                                                              |
| ----------------------- | ------ | ------------------------------------------------------------------ |
| FastAPI sidecar         | `8019` | Agent, SSE, SQLite, tool system                                    |
| Vite dev server         | `8010` | Frontend dev server; proxies `/api` to the sidecar                 |
| llama-server (optional) | `8016` | Local small model, managed by the backend once enabled in Settings |

## Features

### Chat & Models

- Multi-model chat: DeepSeek streaming (deep thinking + reasoning-effort levels), multiple model profiles switchable per session; automatically falls back to a local demo agent when no API key is present
- Model provider catalog is externalized: adding or editing providers and their model lists writes to an editable `divine-model-provider.json`, maintainable from the Settings page or via the `manage_model_providers` tool
- Selectable tool-calling paradigm per model: `tool_mode` = `auto` (default, auto-parsed) / `native` (force native function calling) / `react`
- Local model (optional): llama-server–driven intent detection, long-text pre-processing and local Q&A; data never leaves the machine

### Sessions & Memory

- Sessions: history, auto-generated titles, session search (including pinyin search), project organization (project workspaces/icons), context usage inspection with manual compaction, session export
- In-chat references: `@` for workspace files, `/` for skills (candidate popover plus pill rendering inside bubbles; skill names are validated against the session's skill set, so paths such as `see /docs folder` are not mislabeled as skills)
- Multi-layer long-term memory: L0 working memory (messages within the window) → L1 episodic memory (conclusions and process of each session, searchable across sessions) → L2 semantic memory (user profile / preferences / stable facts, scoped per project via `project_id`) → L3 procedural memory (how-to methods and successful trajectories). Three write paths — explicit, implicit extraction, and explicit override; automatic overwriting only guards against high duplication (same polarity + high similarity), while semantic updates must name the target being overwritten; on a polarity conflict the new memory lands in `pending` for the user to confirm or reject, and overwritten memories are soft-deleted with a `superseded_by` trace. The settings modal has a memory management page, and the `remember` / `recall_memories` / `forget_memory` tools let the model read and write proactively
- History backtracking: questions outside the current window automatically retrieve earlier conversations and inject them into context

### Interaction & Execution

- Proactive questions: when a request is ambiguous or a decision is needed, `ask_user` asks with candidate options and waits for the answer
- Quick local actions (macOS): say 截屏/截图 (screenshot) and it executes locally without a cloud call — `screencapture` silently captures the full screen into the session workspace `screenshots/` (timestamped names), ready for workspace browsing or `@`-mention into GLM vision recognition; "打开截图文件夹" opens that folder directly; sibling local actions include opening apps, locking the screen, and searching files
- Plans & approvals: complex tasks start with a to-do plan; high-risk operations (terminal commands, git commits, file edits, etc.) require user confirmation, with the wait bounded by `approval_timeout`
- Steering during execution, and turns that can be cancelled at any time
- Background tasks & subagents: dev servers / long-running tasks run in the background with status checks; large tasks are split across parallel subagents
- Interactive terminal, Markdown rendering with Shiki code highlighting, and per-message response time in the message list

### General Web Task Engine (Browser Automation)

- Give it a URL plus one sentence, and the agent completes web tasks in a dedicated tab of a real browser: collecting/organizing page information, filling forms, publishing content, auto-shopping — any site
- CDP attach to a dedicated browser profile (the only viable path on Chrome 136+): one-time login persisted and reused, random-port discovery, two-level self-healing (guided relaunch when the endpoint is missing or half-dead), zero system permissions throughout
- ARIA snapshot with monotonic refs instead of raw CSS selectors; contenteditable rich-text editors, framework-delegated clickable controls (cursor:pointer), and mixed text nodes are all addressable; tabs opened by clicks / Enter are adopted automatically; role-less text cards on mobile H5 fall back to clicking by visible text
- Four-tier risk gates: read-only / reversible actions run automatically; irreversible actions (submit / delete / pay) force the flow "extract → action confirmation card → user confirms → confirmed delegation"; password / captcha / API-key inputs are always rejected; a high-risk lexicon, submit idempotency lock, 40-step cap, and old-snapshot trimming back it up
- Site recipes: `data/browser/recipes/*.json` inject flow knowledge by URL pattern; a broken recipe degrades to the generic loop automatically
- Single delegation entry `web_task`: 19 browser operation primitives register only inside the browser subagent, never in the main agent tool table (protecting the prefix cache); every step emits an SSE heartbeat driving the persisted "Browser actions" timeline, and multi-segment delegations merge into one tool card
- Design doc: `docs/design/031-generic-web-task-20261024.md` (shopping policy pack, domain policy settings, and the phased plan live in the same document)

### Generation & Editing (docgen)

- Document and visualization generation: Word, PPT, Excel, PDF (report / business analysis / travel / roadmap / book / slide-deck recipes, plus five paginated templates: academic report / paper submission / data analysis report / research report / hand-drawn quote interpretation), Markdown, SVG vector graphics, ECharts charts, Mermaid diagrams, full UX-interactive HTML, general HTML pages, and editable résumé HTML (19 templates)
- Local document editing: modify existing Word/Excel/PPT files (run-level style preservation, template placeholder filling, table-row expansion, formulas and charts preserved losslessly); editing an external file produces a copy and never touches the original; automatic backup before editing, with `undo_last_turn` to roll back
- PDF forms: read and fill AcroForm fields, and generate fillable form PDFs with real widgets
- PPT: 15 layouts × 19 themes; per-page PNG preview (no LibreOffice needed); supports editing the text and titles of existing decks
- Interactive diagrams: GraphIR contract plus frontend X6 rendering, covering 15 scenarios — process/decision flow, task DAG, data pipeline, state machine, org chart, mind map, topology, architecture, ER, swimlane, sequence, knowledge graph, UML class diagram, fishbone, and timeline; supports node details, data-flow animation and PNG/SVG export
- Interactive panels (A2UI): `render_ui` composes "text + badges + table + progress + stepper + input controls" into a single panel where the user can change parameters and click buttons, and the interaction carries the panel's current state back into the conversation — closing the "see → adjust → see again" loop. Master switch: `ui_a2ui_enabled`

### Data & Retrieval

- Local file analysis: Word, Excel, Markdown, PDF, image recognition (GLM vision), web scraping (automatic browser fallback for JS-driven pages), batch scraping, web search
- Local RAG: a self-built SQLite inverted index over workspace documents (term frequency + `doc_freq`, no embedding model required)
- Read-only SQLite queries

### Extensibility & Automation

- Skills system: install / migrate / preview third-party SKILL.md skills (GitHub, Gitee), with a built-in skill hub. Knowledge skills inject their content directly into the current turn's messages; executable skills inject a tool-calling contract — so "referencing a skill with `/`" actually does something
- MCP connectors: configure and connect external MCP servers, whose tools are merged into the agent automatically (privacy: a connection must be explicitly trusted)
- Scheduled tasks & calendar: reminders, scheduled tasks (each run gets a dedicated session, run records are kept, webhook delivery is supported, and a notification pops when a run finishes), calendar events, with system Calendar sync on macOS; messages written in the background are pushed to the frontend in real time over the always-on event stream `GET /api/events`
- Offline evaluation & auto-debugging: `divine-server/evals` is a standalone evaluation harness (fake_model + scenarios, for offline agent verification); the agent side implements a failure-driven auto-debugging loop (diagnosis parsing + convergence brake)

### Desktop & Experience

- Three UI languages: Simplified Chinese / Traditional Chinese / English (`divine-app/src/i18n`, with matching `pnpm i18n:*` scripts)
- Dark / light themes; a self-built React UI component library, no AntD
- Virtual scrolling for long lists; streaming rendering and session rebuild have redundant-scan / redundant-parse elimination
- Shortcuts: a unified in-app keymap (⌘ on macOS / Ctrl elsewhere) plus a system-wide global shortcut to show or hide the window
- Local SQLite storage; data stays on the machine by default and requires no cloud account
- Tauri 2 + Rust desktop shell: launches and supervises the FastAPI sidecar on startup (restarts it if it dies)
- Workspace file browsing with multi-format preview (PDF / PPTX / documents)

## Tech Stack

| Layer         | Technology                                                                                                                                                                                                                       |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Backend       | FastAPI, Uvicorn, SQLite (self-built inverted-index retrieval), LangChain + LangGraph (SQLite checkpointer), multiple model providers (DeepSeek / GLM / MiniMax), llama-server local models, WeasyPrint + reportlab, PyInstaller |
| Frontend      | Vite, React 19, TypeScript, Less, react-i18next (zh-CN / zh-TW / en), @tanstack/react-virtual, react-markdown, Shiki, ECharts, @antv/x6 + @antv/layout, self-built components                                                    |
| Desktop shell | Tauri 2 + Rust, sidecar lifecycle management, tray, macOS Calendar bridge                                                                                                                                                        |

## Project Layout

| Directory                          | Description                                                                                                                                               |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `divine-server`                    | FastAPI sidecar: API, agent, SSE, SQLite, tool system                                                                                                     |
| `divine-server/app/agent`          | Agent orchestration (LangGraph), prompts, tool execution, intent pruning and SSE splitting, memory extraction                                             |
| `divine-server/app/api`            | HTTP / SSE / WebSocket routes (chat, sessions, settings, mcp, skills, local_llm, etc.)                                                                    |
| `divine-server/app/db`             | SQLite connection, migrations and domain-split repositories (including self-built retrieval primitives and long-term memory)                              |
| `divine-server/app/docgen`         | Document generation (renderers for PDF / Word / PPT / Excel / charts / résumés, including the paginated templates in `ppt/renderer` and `pdf/pdf_themes`) |
| `divine-server/app/llm`            | LLM providers, DSML stream parsing and the LangChain adapter                                                                                              |
| `divine-server/app/mcp`            | MCP server connection management (stdio / SSE)                                                                                                            |
| `divine-server/app/skills`         | SKILL.md skill registration and execution                                                                                                                 |
| `divine-server/app/tools/adapters` | Tool registration and parameter definitions                                                                                                               |
| `divine-server/app/tools/browser_engine` | General web task engine (CDP sessions, ARIA snapshot + refs, risk tiers, shopping policy hooks)                                                     |
| `divine-server/app/tools/scripts`  | Tool subprocess scripts                                                                                                                                   |
| `divine-server/app/tools/graph`    | GraphIR contract (closed-enum schema + validator + checked-in `graph_ir.schema.json`)                                                                     |
| `divine-server/app/tools/ui`       | A2UI panels: component catalog (checked-in `divine_catalog.json`), IR validation, v0.9.1 envelope                                                         |
| `divine-server/tests`              | pytest suite (including contract drift guards)                                                                                                            |
| `divine-server/evals`              | Standalone evaluation harness (fake_model + scenarios, for offline agent verification)                                                                    |
| `divine-app`                       | Vite + React + TypeScript frontend with self-built components                                                                                             |
| `divine-app/src-tauri`             | Tauri 2 + Rust desktop shell                                                                                                                              |
| `docs`                             | Project design documents (plan / design / fix / review / templates; see the index in `docs/README.md`)                                                    |
| `screenshots`                      | UI screenshots used by this README (see "Screenshots" at the end)                                                                                         |
| `scripts`                          | macOS packaging, signing, notarization and release scripts                                                                                                |

## Getting Started

### 1. Start the Backend

Requires Python 3.12+ (the code uses 3.12 f-string syntax); the development environment currently runs Python 3.14.

```bash
cd divine-server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

Once the backend is up, check its health at <http://127.0.0.1:8019/api/health>. Without a `DEEPSEEK_API_KEY`, `AI_PROVIDER=auto` uses the local demo agent; add a key and it switches to real DeepSeek streaming automatically.

During development use `python run.py`; `python entry.py` mimics how the packaged sidecar starts and writes logs to `divine-server.log` inside the data directory — PyInstaller also uses `entry.py` as its entry point.

To run tests (in a sandbox or CI you must point `--basetemp` at a writable directory, otherwise the fixtures fail):

```bash
cd divine-server
source .venv/bin/activate
pytest --basetemp=.pytest_tmp
```

### 2. Start the Frontend

Requires Node.js 20+ and pnpm 9+.

```bash
cd divine-app
pnpm install
pnpm dev
```

Open <http://localhost:8010> in a browser; Vite proxies `/api` requests to `http://127.0.0.1:8019`.

Common scripts:

| Command                                            | Description                                      |
| -------------------------------------------------- | ------------------------------------------------ |
| `pnpm dev`                                         | Local development (port 8010)                    |
| `pnpm typecheck`                                   | Type check with `tsc -b`                         |
| `pnpm lint` / `pnpm lint:fix`                      | ESLint                                           |
| `pnpm build` / `pnpm build:test`                   | `tsc -b` plus a production / test-mode build     |
| `pnpm i18n:extract` / `i18n:status` / `i18n:check` | Extract and validate the three-language strings  |
| `pnpm i18n:tw`                                     | Generate the Traditional Chinese (zh-TW) strings |

### 3. Desktop Development

Tauri launches and supervises the sidecar on its own, but you must first build a sidecar executable for your platform:

```bash
cd divine-server
pip install -r requirements.txt pyinstaller
bash build-sidecar.sh        # auto-detects the current platform

cd ../divine-app
pnpm install
pnpm tauri:dev
```

## Environment Variables

### divine-server

The config file is `divine-server/.env`; see [.env.example](divine-server/.env.example).

| Variable                    | Default                                | Description                                                                                                                             |
| --------------------------- | -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `DEEPSEEK_BASE_URL`         | `https://api.deepseek.com`             | DeepSeek OpenAI-compatible endpoint                                                                                                     |
| `DEEPSEEK_API_KEY`          | empty                                  | DeepSeek API key                                                                                                                        |
| `DEEPSEEK_MODEL`            | `deepseek-flash`                       | DeepSeek model name (code default; `.env.example` ships `deepseek-v4-flash`, which overrides the code default once copied to `.env`)    |
| `DEEPSEEK_REASONING_EFFORT` | `high`                                 | Deep-thinking effort: `low` / `medium` / `high` / `xhigh` / `max` (`medium` and `xhigh` are mapped to `high` by the API)                |
| `AI_PROVIDER`               | `auto`                                 | `auto` uses DeepSeek when a key is present, otherwise the local demo; `mock` forces the local demo; `langchain` uses LangChain DeepSeek |
| `GLM_BASE_URL`              | `https://open.bigmodel.cn/api/paas/v4` | GLM vision model endpoint                                                                                                               |
| `GLM_API_KEY`               | empty                                  | GLM API key, used by `read_image`                                                                                                       |
| `GLM_MODEL`                 | `glm-4.6v-flash`                       | GLM vision model name                                                                                                                   |
| `HOST`                      | `127.0.0.1`                            | Sidecar bind address                                                                                                                    |
| `PORT`                      | `8019`                                 | Sidecar port                                                                                                                            |
| `CORS_ORIGINS`              | `http://localhost:8010,...`            | Comma-separated allowed origins (includes desktop-shell origins such as `tauri://localhost`)                                            |
| `DIVINE_DATA_DIR`           | `divine-server/data`                   | Data directory: database, `settings.json`, logs                                                                                         |
| `DIVINE_WORKSPACE_DIR`      | `divine-server/workspace`              | Workspace root (**only this variable is honored**; the leftover `WORKSPACE_DIR` in `.env.example` is never read)                        |
| `DIVINE_PROJECTS_DIR`       | empty                                  | Reserved project-root variable; currently unused by the code                                                                            |
| `DB_PATH`                   | `<data_dir>/ai_workspace.db`           | SQLite database path                                                                                                                    |

#### Multi-Model Configuration

`settings.json` supports multiple models (maintained under Settings → Models, or by editing the file directly):

```json
{
  "models": [
    {
      "id": "default",
      "name": "DeepSeek V4 Flash",
      "provider": "auto",
      "model": "deepseek-flash",
      "base_url": "https://api.deepseek.com",
      "api_key": "sk-...",
      "active": true,
      "tool_mode": "auto"
    }
  ]
}
```

- The entry with `active: true` is the default model, and is mirrored to the top-level `provider` / `model` / `base_url` / `api_key` fields for backward compatibility.
- During a conversation you can switch models per session from the model selector to the left of the send button (each session remembers its own choice and falls back to the default). The same entry point controls deep thinking and reasoning effort.
- `provider`: `auto` (DeepSeek when a key is present, otherwise the local demo), `langchain` (LangChain DeepSeek), `mock` (local demo).
- `tool_mode`: `auto` (default) / `native` (force native function calling) / `react` (ReAct text protocol) — pick according to model capability.
- The model provider catalog (provider names, `base_url`, optional model lists) lives separately in `divine-model-provider.json`, maintainable from the Settings page or via the `manage_model_providers` tool.

#### Other Flat Settings

`settings.json` is a **flat dict**; new switches are plain top-level keys (no dotted paths). Commonly used entries:

| Key                                                                                                   | Default                 | Description                                                                                                                        |
| ----------------------------------------------------------------------------------------------------- | ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `username`                                                                                            | `用户`                  | How the UI addresses you                                                                                                           |
| `think_default`                                                                                       | `false`                 | Whether deep thinking is on by default                                                                                             |
| `reasoning_effort`                                                                                    | `high`                  | Deep-thinking effort level                                                                                                         |
| `context_limit`                                                                                       | `30`                    | Max number of historical messages injected as context                                                                              |
| `approval_timeout`                                                                                    | `180`                   | Seconds to wait for high-risk-operation confirmation / proactive questions (minimum 30)                                            |
| `global_shortcut_enabled`                                                                             | `true`                  | Whether the system-wide global shortcut is enabled                                                                                 |
| `ui_a2ui_enabled`                                                                                     | `true`                  | Master switch for A2UI interactive panels (`render_ui`); when off, the tool is not injected and the frontend ignores `a2ui` events |
| `local_llm_enabled` / `local_llm_mode` / `local_llm_port` / `local_llm_model` / `local_llm_threshold` | —                       | Local model switch and parameters                                                                                                  |
| `local_llm_preprocess_*`                                                                              | —                       | Local pre-processing (input-side) switch and thresholds                                                                            |
| `installed_models`                                                                                    | `[]`                    | Installed local model list                                                                                                         |
| `browser_cdp_port` | empty | Manual browser debug port (usually unnecessary: the engine discovers or launches it) |
| `browser_blocked_domains` | empty | Domains forbidden for navigation (comma-separated substrings) |
| `browser_confirm_domains` | empty | Domains where mutations require per-action confirmation (comma-separated) |
| `shopping_per_order_cap` / `shopping_monthly_cap` | `200` / empty | Per-order / monthly shopping amount guards (checked on checkout pages) |
| `shopping_policy_domains` | four major platforms | Domain list for the shopping policy pack |
| `shopping_default_address` | empty | Default delivery address (warning on the confirmation card when checkout differs) |
| `max_retries` / `timeout`                                                                             | edit manually if needed | Request retry count and timeout; can be set at the top level or inside a model entry                                               |

When launching the sidecar, the desktop app injects `DIVINE_DATA_DIR` and `DIVINE_WORKSPACE_DIR`, pointing at the system application data directory — so a packaged build does not depend on the repository's `data/` or `workspace/`.

Plain fields are read from `data/settings.json` first and fall back to environment variables or defaults when unsaved; `HOST` and `PORT` always follow the environment. Settings made in the UI are written to `settings.json`, and `DIVINE_WORKSPACE_DIR` only takes effect when no workspace has been set in Settings.

### divine-app

The frontend uses a mode-specific env file:

| File        | Mode   | Used by                                    |
| ----------- | ------ | ------------------------------------------ |
| `.env.dev`  | `dev`  | `pnpm dev`, `pnpm tauri:dev`               |
| `.env.test` | `test` | `pnpm build:test`, `pnpm tauri:build:test` |
| `.env.prod` | `prod` | `pnpm build`, `pnpm tauri:build:prod`      |

| Variable                    | Description                                              |
| --------------------------- | -------------------------------------------------------- |
| `VITE_SERVICE_API_URL`      | Sidecar API address, default `http://127.0.0.1:8019/api` |
| `VITE_DISABLE_CONTEXT_MENU` | Disables the WebView context menu in release builds      |

## Tool System

100 tools are registered at present (growing and shrinking with MCP servers and skills), sorted by name:

| Tool                                  | Purpose                                                                                                                                                                                                      |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `apply_patch`                         | Apply unified diff patches (multi-file / new files), tolerant of line drift and whitespace                                                                                                                   |
| `ask_user`                            | Ask a question and wait for the answer when a request is vague or needs a decision (prefers offering candidate options)                                                                                      |
| `bg_kill` / `bg_output` / `bg_status` | Background tasks: stop, read recent output, check status                                                                                                                                                     |
| `calculator`                          | Safely evaluate math expressions                                                                                                                                                                             |
| `clipboard`                           | Read, write and clear the system clipboard                                                                                                                                                                   |
| `create_plan`                         | Create a to-do plan for a complex task                                                                                                                                                                       |
| `describe_svg`                        | Read an existing SVG and return its canvas, elements, key ids and a structural summary                                                                                                                       |
| `directory_tree`                      | Show the directory tree (ignoring .gitignore / node_modules)                                                                                                                                                 |
| `discover_importable_skills`          | Scan skills already installed by other AI tools on this machine and list migration candidates                                                                                                                |
| `document_outline`                    | Show the structural outline of a Word/Excel/PPT document (paragraphs / tables / sheets / pages) with editable coordinates                                                                                    |
| `draw_svg`                            | Generate SVG vector art, icons and illustrations from scratch                                                                                                                                                |
| `edit_docx`                           | Edit an existing Word document: replace text (run-level style preservation), change table cells, append sections, delete paragraphs                                                                          |
| `edit_files`                          | Batch modify / create files with SEARCH/REPLACE blocks (SEARCH must match exactly)                                                                                                                           |
| `edit_lines`                          | Precisely edit a single file by line-number range                                                                                                                                                            |
| `edit_pptx`                           | Edit text in an existing deck: replace text (including grouped shapes and tables), change a given slide's title                                                                                              |
| `edit_svg`                            | Make local modifications to an existing SVG, touching only the elements the user mentioned                                                                                                                   |
| `edit_xlsx`                           | Edit an existing Excel workbook: change cells and styles, append rows, add or remove worksheets, write formulas, insert charts and images                                                                    |
| `fill_template`                       | Fill `{{placeholders}}` in Word/Excel templates; Word supports whole-table-row expansion (contracts, notices, and similar template scenarios)                                                                |
| `forget_memory`                       | Delete a long-term memory (when the user corrects a wrong one)                                                                                                                                               |
| `format_code`                         | Format code (auto-detects `ruff format` / `prettier`)                                                                                                                                                        |
| `generate_chart`                      | Generate an ECharts chart and render it inline in the conversation                                                                                                                                           |
| `git_commit` / `git_revert`           | Commit changes / revert uncommitted changes (both require confirmation)                                                                                                                                      |
| `git_diff` / `git_log` / `git_status` | Show the uncommitted diff / commit history / repository status                                                                                                                                               |
| `glob_files`                          | Match files by glob pattern (`**` recurses), newest → oldest                                                                                                                                                 |
| `grep_files`                          | Search text files by content (regex), returning line-level hits                                                                                                                                              |
| `html_common`                         | Save user-provided complete HTML as-is (no base injection, content untouched)                                                                                                                                |
| `html_generate`                       | Generate a complete HTML page (report / dashboard / landing page and more), injecting a design-token base and running static validation                                                                      |
| `html_resume`                         | Editable HTML résumé output (19 templates; edit text in the browser, then download or print to PDF)                                                                                                          |
| `image_generate`                      | Text-to-image / image-to-image (MiniMax and GLM-Image backends)                                                                                                                                              |
| `image_resize`                        | Resize local images                                                                                                                                                                                          |
| `install_skill`                       | Install a SKILL.md skill from GitHub or Gitee                                                                                                                                                                |
| `lint_check`                          | Static checks (auto-detects ruff / mypy / eslint / tsc), returning structured issues                                                                                                                         |
| `list_definitions`                    | Outline of a code file's structure (classes / functions plus start line numbers)                                                                                                                             |
| `manage_model_providers`              | Maintain the model provider catalog (providers, their model lists and `base_url`)                                                                                                                            |
| `mermaid_export`                      | Save Mermaid source to a `.mmd` file                                                                                                                                                                         |
| `migrate_skill` / `migrate_skills`    | Migrate locally discovered skills into AI Divine (single / batch)                                                                                                                                            |
| `move_file`                           | Move or rename a file or directory inside the workspace                                                                                                                                                      |
| `notes`                               | Generate Markdown notes                                                                                                                                                                                      |
| `pdf_form_fields`                     | List the fields of an interactive PDF form (AcroForm): name / type / optional state / page                                                                                                                   |
| `pdf_form_fill`                       | Fill an interactive PDF form by field name (checkbox true/false semantics; aborts the whole operation on failure; supports backup and undo)                                                                  |
| `pdf_form_generate`                   | Generate a **fillable** form PDF with real AcroForm widgets (text boxes / checkboxes / radio buttons / dropdowns, from a declarative field list)                                                             |
| `pdf_generate`                        | Unified PDF generation entry point (report / business / travel / roadmap / book / slide-deck recipes, plus academic report / paper / data analysis / research report / hand-drawn quote paginated templates) |
| `pdf_render`                          | Render Markdown into a typeset PDF (WeasyPrint, automatically falling back to the reportlab rich renderer on failure)                                                                                        |
| `pdf_to_word`                         | Convert PDF text content into an editable Word document (headings / tables / lists preserved; scanned pages unsupported)                                                                                     |
| `pdf_split_merge`                     | Split and merge PDFs                                                                                                                                                                                         |
| `pptx_to_png`                         | Render each slide of a deck to PNG (no LibreOffice needed); scale, single page or output directory can be specified                                                                                          |
| `presentation`                        | Generate a PPT deck (15 layouts; simple charts are embedded as native, editable PowerPoint charts)                                                                                                           |
| `preview_skill_repo`                  | Read-only preview of the SKILL.md in a remote repository before deciding to install                                                                                                                          |
| `rag_index`                           | Scan workspace text and build the local index                                                                                                                                                                |
| `rag_search`                          | Search the workspace local index for relevant content (self-built inverted index, not a vector store)                                                                                                        |
| `read_file`                           | Read text / Office / PDF / spreadsheets and more; supports line-number paging                                                                                                                                |
| `read_image`                          | Recognize an image with the GLM vision model (local path or URL)                                                                                                                                             |
| `recall_memories`                     | Proactively search long-term memory (when injected information is insufficient, or to look up old memory ids before correcting one)                                                                          |
| `remember`                            | Save a user's stable preferences / facts / events to long-term memory (with automatic dedup and expiry)                                                                                                      |
| `render_graph`                        | Redraw a confirmed "nodes + edges" topology as an interactive diagram (15 scenarios; click for details, play the flow, export)                                                                               |
| `render_ui`                           | Render a set of components into an interactive panel (data table + input controls + buttons); actions return to the conversation with the panel state                                                        |
| `review_changes`                      | Run an automatic code review over uncommitted workspace changes and output a list of issues                                                                                                                  |
| `run_subagents`                       | Split a large task into independent subtasks, delegate them to subagents in parallel and summarize the results                                                                                               |
| `run_tests`                           | Run automated tests (auto-detects pytest / jest / vitest) and return the failure list                                                                                                                        |
| `schedule_task`                       | Create a scheduled reminder or task                                                                                                                                                                          |
| `search_files`                        | Search workspace files by filename or path keyword                                                                                                                                                           |
| `spreadsheet`                         | Generate professionally styled Excel (themes / zebra striping / frozen header / auto-filter)                                                                                                                 |
| `sqlite_query`                        | Read-only queries against local SQLite (SELECT / PRAGMA / WITH only)                                                                                                                                         |
| `svg_to_png` / `svg_to_png_batch`     | Export SVG to PNG / batch-export multiple sizes (iOS / Android icons)                                                                                                                                        |
| `terminal`                            | Run terminal commands; high-risk commands require confirmation; the working directory persists within a session                                                                                              |
| `undo_last_turn`                      | Undo the agent's most recent file changes (restore the snapshot)                                                                                                                                             |
| `ux_html`                             | Save a complete UX-interactive HTML page designed by the agent, previewable in the file panel                                                                                                                |
| `web_fetch` / `web_fetch_batch`       | Fetch a page / batch-fetch, with automatic browser fallback for JS-driven pages; can listen to data APIs and take JSON                                                                                       |
| `web_search`                          | Web search returning titles / links / snippets                                                                                                                                                               |
| `web_task`                            | General web task engine: delegate "URL + request" to the browser subagent running in a real browser (navigate / snapshot / fill / click / extract); irreversible actions require a confirmation card                          |
| `word_document`                       | Generate a Word document (headings / tables / images / code blocks and more), optionally using the user's docx as the style base                                                                             |
| `write_calendar`                      | Write a schedule or calendar event                                                                                                                                                                           |
| `write_file`                          | Create or write a text file inside the workspace                                                                                                                                                             |

Two tool defaults: output paths must stay inside the workspace (anything outside is rejected), and high-risk operations (terminal, git commit / revert, file edits, etc.) always ask the user first.

Nineteen browser operation primitives — `browser_navigate` / `browser_snapshot` / `browser_click` / `browser_fill` / `browser_select` / `browser_scroll` / `browser_extract` / `browser_wait` / `browser_press_key` / `browser_read_captcha` / `browser_solve_slider` / `browser_solve_click_captcha` / `browser_geometry` / `browser_capture` / `browser_sniff_start` / `browser_sniff_stop` / `browser_api_login` / `browser_api_call` / `browser_track_order` / `browser_read_page` — register only inside the browser subagent, never in the main agent tool table (protecting the system prompt and prefix cache); the main agent delegates exclusively through `web_task`.

`render_ui` and `render_graph` are both "do not call by default" tools: for a plain conclusion use Markdown prose, for a single chart use `generate_chart`, for a single table use a Markdown table, and for static diagrams use Mermaid first. Call them only when you need **composed presentation**, **in-UI manipulation**, or the user explicitly asks for something **interactive / exportable** — avoiding the token and rendering cost of form for its own sake.

## API

| Route                            | Description                                                                                                      |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `POST /api/stream_chat`          | SSE streaming chat (including custom events such as `a2ui`)                                                      |
| `POST /api/chat/answer`          | Answer an agent confirmation or question                                                                         |
| `POST /api/chat/surface-action`  | A2UI panel action feedback (`action_id` is idempotent; returns 409 while the session is streaming)               |
| `POST /api/chat/retry_cloud`     | Retry with a cloud model when the local answer is unsatisfactory                                                 |
| `POST /api/sessions/{id}/cancel` | Cancel the current turn                                                                                          |
| `POST /api/sessions/{id}/inject` | Steering — interject mid-execution to correct course                                                             |
| `GET /api/health`                | Health check, returning provider, model and tool count                                                           |
| `/api/sessions`                  | Session management (search, export, clear, context usage, compaction, option state, panel edit-state read/write) |
| `/api/projects`                  | Project management (ordering, pinning)                                                                           |
| `/api/scheduled-tasks`           | Scheduled task management (including run records and confirmation)                                               |
| `/api/calendar-events`           | Calendar event management                                                                                        |
| `/api/events`                    | Always-on SSE event stream (background change pushes, e.g. `sessions_changed`)                                   |
| `/api/files`                     | Workspace file listing and download, including PDF / PPTX / document preview                                     |
| `/api/workspace/mentions`        | `@` reference candidates (workspace files)                                                                       |
| `/api/workspace/skill-names`     | Set of skill names available to the session (the frontend uses it to verify that a `/skill` actually exists)     |
| `/api/memories`                  | Long-term memory read/write, including the `pending` list and confirm/reject                                     |
| `/api/settings`                  | Runtime settings (including multi-model and MCP configuration) and balance query                                 |
| `/api/model-providers`           | Model provider catalog read/write                                                                                |
| `/api/mcp`                       | MCP server status queries and connection tests                                                                   |
| `/api/skills`                    | Skill (SKILL.md) installation and management                                                                     |
| `/api/local_llm`                 | Local model (llama-server) status, start/stop, download and model management                                     |
| `/api/pdf/themes`                | PDF theme management and preview                                                                                 |
| `/api/git`                       | Git operation entry point                                                                                        |
| `WS /api/terminal`               | Interactive terminal                                                                                             |
| `POST /api/terminal/decide`      | Approve a pending terminal command                                                                               |

Error responses are uniformly `{"detail": ...}`: business validation errors are 4xx (`HTTPException`), and uncaught exceptions become 500 (caught by a global exception handler that truncates `detail` to something readable).

## Data Directory

In development mode:

- Database: `divine-server/data/ai_workspace.db`
- Settings: `divine-server/data/settings.json`
- Logs: `divine-server/data/divine-server.log`
- Workspace: `divine-server/workspace/{documents,spreadsheets,notes,pdf,presentations,diagrams,html,svg}` (subdirectories are created on demand)

The packaged desktop build uses the system application data directory by default and never writes into the project directory. The database, settings and logs are controlled by `DIVINE_DATA_DIR`, and the workspace by `DIVINE_WORKSPACE_DIR`.

## Packaging

### Packaging the Sidecar

```bash
cd divine-server
source .venv/bin/activate
pip install -r requirements.txt pyinstaller
bash build-sidecar.sh                  # auto-detects the current platform
bash build-sidecar.sh darwin-arm64     # or name the target explicitly
bash build-sidecar.sh darwin-x64
bash build-sidecar.sh win32-x64
bash build-sidecar.sh linux-x64
```

Output goes to `divine-server/bin/<target>/` and is also copied as the Tauri externalBin into `divine-app/src-tauri/binaries/`.

> After changing Python sources you must rebuild the sidecar — the running process is the PyInstaller binary and does not hot-reload. The build compiles the current working tree, so uncommitted changes ship in the artifact.

### Packaging the Desktop App

```bash
cd divine-app
pnpm tauri:build:prod    # release build, no right-click debug menu
pnpm tauri:build:test    # test build, keeps right-click Reload / Inspect Element, unsigned and un-notarized
pnpm tauri:build:debug   # debug build with devtools enabled
```

Each configuration's `beforeBuildCommand` is `pnpm build` / `pnpm build:test`, which already includes `tsc -b` — so type errors abort packaging immediately.

### macOS Signing & Notarization

```bash
./scripts/release-macos.sh                  # Developer ID signing + notarization
./scripts/release-macos.sh --skip-notarize  # sign only, skip notarization
./scripts/release-macos.sh --keychain-profile <profile>  # use a saved notarytool profile
./scripts/release-macos.sh --adhoc          # local testing, ad-hoc signing
```

Full signing requires a Developer ID Application certificate installed; notarization requires `APPLE_ID`, `APPLE_PASSWORD` and `APPLE_TEAM_ID`, or an App Store Connect API key (`APPLE_API_ISSUER`, `APPLE_API_KEY`, `APPLE_API_KEY_PATH`).
You can also store credentials first with `xcrun notarytool store-credentials <profile> --apple-id ... --team-id ...` and then notarize with `--keychain-profile`.

Do not put the signing certificate in `tauri.conf.json`. Create a `.env` at the project root instead (see `.env.example`):

```bash
APPLE_SIGNING_IDENTITY="Developer ID Application: Your Name (TEAMID)"
```

`release-macos.sh` reads `.env` when packaging and overrides `signingIdentity` with a temporary config; `.env` is gitignored and never reaches the remote repository.

### Auto-Update & Release

First generate a dedicated signing key for the updater; the public key goes into `tauri.conf.json` and the private key must never be committed:

```bash
cd divine-app
pnpm tauri signer generate -w ~/.tauri/divine.key
```

If your shell has a leftover `TAURI_SIGNING_PRIVATE_KEY` from another project, unset it before releasing so the wrong key is not used:

```bash
unset TAURI_SIGNING_PRIVATE_KEY
export TAURI_SIGNING_PRIVATE_KEY_PATH="$HOME/.tauri/divine.key"
```

Build locally and upload a Release:

```bash
bash scripts/publish-macos.sh \
  --version 0.2.1 \
  --arch arm64 \
  --updater-key ~/.tauri/divine.key \
  --keychain-profile <profile> \
  --upload
```

The script builds the signed bundle, generates the `.app.tar.gz` and `release-assets/latest.json`, and uploads them to the Release. On launch the client checks that manifest automatically and, once a new version is found, offers a download and restart from the Settings page or the bottom-right prompt.

`--arch` selects the target architecture (`arm64` / `x86_64`, defaulting to the current machine), and `--keychain-profile` uses a saved notarytool credential. `--repo` is inferred from the git remote and `--notes` reads `release-notes.md` by default. Other common flags: `--bundles` (default `app,dmg`), `--skip-sidecar` (reuse an existing sidecar artifact) and `--adhoc`.

Release notes are read by default from the `## v<version>` block in the repository-root `release-notes.md` (for example `## v0.2.1`); override with `--notes` or `--notes-file`.

To overwrite an already-published version with the same number:

```bash
bash scripts/overwrite-release.sh 0.2.1
```

### CI

The repository ships two workflows, both triggerable by pushing a `v*` tag or manually:

- `.github/workflows/build.yml` (`Build Desktop Apps`): builds macOS ARM64 / macOS x64 / Windows x64 / Linux x64 and uploads the artifacts as Actions artifacts, also attaching them to the Release when a tag is pushed.
- `.gitea/workflows/release-macos-universal.yaml` (`macOS DMG Release`): builds, signs, notarizes and publishes both the arm64 and x64 DMGs on a macOS self-hosted runner.

## Screenshots

All captured from a real local run (dark theme by default; the Settings page is shown in light theme).

![Self-introduction](screenshots/0.png)

![Chat home](screenshots/1.png)

**Tool chain and artifact preview in a conversation** — Tools: `web_fetch`, `generate_chart`, `html_generate`

![Tool chain and artifact preview](screenshots/2.png)

**Skill hub** — Tools: `install_skill`, `preview_skill_repo`, `migrate_skill`

![Skill hub](screenshots/3.png)

**Scheduled tasks** — Tools: `schedule_task`

![Scheduled tasks](screenshots/4.png)

**Project architecture walkthrough and workspace browsing** — Tools: `directory_tree`, `read_file` (Mermaid rendered in prose)

![Project architecture walkthrough and workspace browsing](screenshots/5.PNG)

![Settings: intent recognition and local models](screenshots/6.png)

**Diagram generation** — Tools: `read_file`, `glob_files` (Mermaid rendered in prose)

![Diagram generation](screenshots/7.png)

**A2UI interactive panel** — Tool: `render_ui`

![A2UI interactive panel](screenshots/8.png)

**Document generation & workspace preview** — Tool: `presentation`

![Document generation & workspace preview](screenshots/9.png)

**Scheduled task + file preview split view** — Tools: `schedule_task`

![Scheduled task + file preview](screenshots/10.png)

**General web task engine in action** — Tool: `web_task`

![General web task engine](screenshots/11.jpg)

**Auto-shopping in action** — Tool: `web_task` (shopping policy pack)

![Auto-shopping](screenshots/12.png)
