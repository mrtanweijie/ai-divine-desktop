from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# DeepSeek thinking-mode effort vocabulary (see
# https://api-docs.deepseek.com/zh-cn/guides/thinking_mode).
ReasoningEffort = Literal["low", "medium", "high", "xhigh", "max"]


class Attachment(BaseModel):
    name: str
    content: str = ""
    file_path: str | None = None
    size: int | None = None


class MentionRef(BaseModel):
    """消息里的 `@文件` / `/技能` 引用（结构化）。

    后端只信这个数组，不从消息正文反向抽取；旧客户端可能直接传路径
    字符串列表，由 before 校验器归一为 `type="file"`。
    """

    type: Literal["file", "skill"] = "file"
    path: str | None = None
    name: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_string(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"type": "file", "path": value}
        return value


class StreamChatRequest(BaseModel):
    question: str = Field(default="")
    session_id: str | None = None
    project_id: str | None = None
    approval_mode: str | None = None
    think: bool = False
    reasoning_effort: ReasoningEffort | None = None
    locale: str | None = None
    # 桌面端当前 UI 主题（"dark" / "light"），由前端解析 system 后传 resolved 值。
    # 用于让 SVG/图表等定色产物匹配当前外观；缺省或非法值服务端回落 "dark"。
    ui_theme: str | None = None
    attachments: list[Attachment] = []
    # 输入框里 `@文件` / `/技能` 的显式引用（结构化传参，非正文解析）
    mentions: list[MentionRef] = []
    model_id: str | None = None
    # Per-request tool-calling override ("native" / "react"); only for
    # debugging/A-B comparison. Absent means the model entry decides.
    tool_mode: str | None = None


class RetryCloudRequest(BaseModel):
    """本地模型回答不满意 → 用户点【重答】：对同一问题直接用云端重答。

    message_id 指向那条本地回答；服务端回溯到它前面的用户问题，
    以历史截断到该问题为止重新跑云端 agent，追加一条新回答。
    """
    session_id: str
    message_id: str
    approval_mode: str | None = None
    think: bool = False
    reasoning_effort: ReasoningEffort | None = None
    locale: str | None = None
    ui_theme: str | None = None
    model_id: str | None = None
    tool_mode: str | None = None


class InjectRequest(BaseModel):
    """用户插话（steering）：agent 执行中用户主动补充的信息。

    落库为带 [用户补充] 前缀的 user 消息并入队，由当前 agent run
    的 UserInjectionMiddleware 在下一次模型调用前注入 state。
    """

    content: str = Field(min_length=1)


class ChatAnswer(BaseModel):
    """ask_user 的用户回答：session_id + call_id 配对，answer 为文本。"""

    session_id: str
    call_id: str
    answer: str = Field(min_length=1, max_length=2000)


class SessionCreate(BaseModel):
    title: str | None = None
    project_id: str | None = None
    approval_mode: str | None = None
    locale: str | None = None


class SessionUpdate(BaseModel):
    title: str | None = None
    approval_mode: str | None = None


class ChoiceStateUpdate(BaseModel):
    state: dict[str, Any] | None = None


class UiSurfaceStateUpdate(BaseModel):
    """面板编辑态（用户改了但没提交的值），抗刷新（design 028 §5.5 ②）。

    与 `choice_state` 分开存：那是"选项卡片的已选态"，这是"A2UI 面板的
    输入控件当前值"，语义与体量都不同（后者可能很大）。
    """

    surface_id: str = Field(min_length=1, max_length=120)
    #: 面板所属 assistant 消息（可空）。**仅作回放定位的元信息**：
    #: 流式期间这个 id 还是前端乐观 id，所以它不参与任何校验。
    message_id: str = ""
    data: dict[str, Any] = {}


class SurfaceActionRequest(BaseModel):
    """A2UI 面板动作 → 新回合（design 028 §8.1）。

    动作**不是**特权通道：服务端把它写成一条**可见的 user 消息**再跑常规回合
    （不做隐藏注入 —— 隐藏注入会绕过 steering / plan / 工具预算这些既有中间件）。
    因此这一步在 agent 内核上是零侵入的。
    """

    session_id: str
    #: 面板所属的 assistant 消息（定位与回显用；可为空）
    message_id: str = ""
    surface_id: str = ""
    #: 幂等键，60s 内重复只跑一轮
    action_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=64)
    #: 按钮文案（可见 user 消息正文的主体）
    label: str = ""
    #: action.context 的求值结果（会写进正文，见 §8.2 的 ⚠️）
    context: dict[str, Any] = {}
    #: 提交瞬间的面板状态（只入 part 供回放/分析，不进模型上下文）
    data_model: dict[str, Any] = {}
    approval_mode: str | None = None
    think: bool = False
    reasoning_effort: ReasoningEffort | None = None
    locale: str | None = None
    ui_theme: str | None = None
    model_id: str | None = None


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    path: str | None = None
    icon: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    path: str | None = None
    icon: str | None = None


class ProjectOrderUpdate(BaseModel):
    sort_order: int = Field(ge=0)


class ProjectPinUpdate(BaseModel):
    pinned: bool


class ProjectReorderItem(BaseModel):
    id: str
    sort_order: int = Field(ge=0)


class ProjectReorderRequest(BaseModel):
    orders: list[ProjectReorderItem]


class ModelConfigUpdate(BaseModel):
    """One editable model entry as submitted by the settings UI.

    ``api_key`` is only meaningful when the user typed a new value; an empty
    or missing key means "keep the previously saved key".
    """

    id: str | None = None
    name: str = ""
    provider: str = "langchain"
    model: str = ""
    base_url: str | None = None
    api_key: str | None = None
    active: bool = False
    tool_mode: str | None = None
    custom_models: str | None = None
    vendor: str | None = None


class SettingsUpdate(BaseModel):
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    glm_api_key: str | None = None
    workspace_dir: str | None = None
    username: str | None = None
    think_default: bool | None = None
    reasoning_effort: ReasoningEffort | None = None
    context_limit: int | None = Field(default=None, ge=1, le=200)
    models: list[ModelConfigUpdate] | None = None
    # MCP 外部服务器（stdio/http）；env 值回传空字符串时保留已存密钥
    mcp_servers: list[dict[str, Any]] | None = None
    # 本地模型配置
    local_llm_enabled: bool | None = None
    local_llm_mode: Literal["keyword", "local", "hybrid"] | None = None
    local_llm_port: int | None = Field(default=None, ge=1, le=65535)
    local_llm_model: str | None = None
    local_llm_ctx_size: int | None = Field(default=None, ge=256, le=131072)
    local_llm_threshold: float | None = Field(default=None, ge=0, le=1)
    # 桌面全局快捷键（唤起/隐藏主窗口）开关
    global_shortcut_enabled: bool | None = None


class ScheduledTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = ""
    session_id: str | None = None
    # 027 设计：加 3 类新任务（webhook / interactive / digest），
    # reminder / agent / monitor 保留原语义。
    task_type: Literal[
        "reminder", "agent", "monitor", "webhook", "interactive", "digest"
    ] = "reminder"
    frequency: Literal["once", "interval", "daily", "weekly", "monthly"] = (
        "interval"
    )
    interval_minutes: int | None = Field(default=None, ge=1)
    run_at: str | None = None
    run_hour: int | None = Field(default=None, ge=0, le=23)
    run_minute: int | None = Field(default=None, ge=0, le=59)
    days_of_week: list[int] = []
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    status: Literal["active", "paused", "done"] = "active"
    # 027 设计：把任务源 / 投递 / 交互元数据下沉到任务本身。
    # 仅 webhook / interactive / digest 使用；其他类型留空也合法。
    prompt: str = ""
    model_id: str | None = None
    allow_full_access: bool = False
    delivery: dict[str, Any] | None = None
    interactive: dict[str, Any] | None = None
    digest: dict[str, Any] | None = None


class ScheduledTaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    session_id: str | None = None
    task_type: Literal[
        "reminder", "agent", "monitor", "webhook", "interactive", "digest"
    ] | None = None
    frequency: Literal["once", "interval", "daily", "weekly", "monthly"] | None = None
    interval_minutes: int | None = Field(default=None, ge=1)
    run_at: str | None = None
    run_hour: int | None = Field(default=None, ge=0, le=23)
    run_minute: int | None = Field(default=None, ge=0, le=59)
    days_of_week: list[int] | None = None
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    next_run_at: str | None = None
    last_run_at: str | None = None
    status: Literal["active", "paused", "done"] | None = None
    calendar_synced: int | None = None
    # 027 设计：stage 2+ 才会从前端传入；stage 1 仅开放字段，API 透传。
    prompt: str | None = None
    model_id: str | None = None
    allow_full_access: bool | None = None
    delivery: dict[str, Any] | None = None
    interactive: dict[str, Any] | None = None
    digest: dict[str, Any] | None = None


class ScheduledTaskDecide(BaseModel):
    """定时任务交互决策（design 027 §3.4）。"""

    ticket: str = Field(min_length=1)
    decision: Literal["approve", "reject"]


class CalendarEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    start_at: str
    end_at: str | None = None
    notes: str = ""
    location: str = ""
    task_id: str | None = None


class CalendarEventUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    start_at: str | None = None
    end_at: str | None = None
    notes: str | None = None
    location: str | None = None
    task_id: str | None = None
    system_event_id: str | None = None
    synced: int | None = None
