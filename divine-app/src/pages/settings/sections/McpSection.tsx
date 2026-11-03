import { useCallback, useEffect, useState } from "react";
import { Blocks, ChevronDown, Pencil, PlugZap, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { McpServerConfig, McpServerStatus } from "@/types";
import { getMcpServers, testMcpServer } from "@/services/api";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Switch } from "@/components/ui/Switch";
import { TextArea } from "@/components/ui/TextArea";
import "./McpSection.less";

/** Claude Desktop 的 {"mcpServers": {...}} 配置也支持整段粘贴导入 */
interface DraftServer {
  id: string;
  name: string;
  transport: "stdio" | "http";
  command: string;
  argsText: string; // 每行一个参数
  envText: string; // 每行 KEY=VALUE；空值提交后服务端保留已存密钥
  url: string;
  enabled: boolean;
  trusted: boolean;
}

function toDraft(server: McpServerConfig): DraftServer {
  return {
    id: server.id,
    name: server.name || server.id,
    transport: server.transport || "stdio",
    command: server.command || "",
    argsText: (server.args || []).join("\n"),
    envText: Object.entries(server.env || {})
      .map(([key, value]) => `${key}=${value}`)
      .join("\n"),
    url: server.url || "",
    enabled: server.enabled,
    trusted: server.trusted ?? false,
  };
}

function fromDraft(draft: DraftServer): McpServerConfig {
  const env: Record<string, string> = {};
  for (const line of draft.envText.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const eq = trimmed.indexOf("=");
    if (eq <= 0) continue;
    env[trimmed.slice(0, eq).trim()] = trimmed.slice(eq + 1);
  }
  return {
    id: draft.id,
    name: draft.name.trim() || draft.id,
    transport: draft.transport,
    command: draft.transport === "stdio" ? draft.command.trim() : "",
    args:
      draft.transport === "stdio"
        ? draft.argsText
            .split("\n")
            .map((line) => line.trim())
            .filter(Boolean)
        : [],
    env: draft.transport === "stdio" ? env : {},
    url: draft.transport === "http" ? draft.url.trim() : "",
    enabled: draft.enabled,
    trusted: draft.trusted,
  };
}

interface McpSectionProps {
  initialServers?: McpServerConfig[];
  onSave: (body: { mcp_servers: McpServerConfig[] }) => Promise<void> | void;
  onSilentSave?: (body: { mcp_servers: McpServerConfig[] }) => Promise<void> | void;
  onConfirm?: (title: string, description: string, action: () => void) => void;
}

export function McpSection({ initialServers, onSave, onSilentSave, onConfirm }: McpSectionProps) {
  const { t } = useTranslation();
  const [servers, setServers] = useState<McpServerConfig[]>(initialServers ?? []);
  const [statuses, setStatuses] = useState<Record<string, McpServerStatus | undefined>>({});
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<DraftServer | null>(null);
  const [expandedTools, setExpandedTools] = useState<Record<string, boolean>>({});
  const [jsonMode, setJsonMode] = useState(false);
  const [jsonText, setJsonText] = useState("");
  const [jsonError, setJsonError] = useState("");

  const persist = useCallback(
    (next: McpServerConfig[]) => {
      setServers(next);
      void (onSilentSave ?? onSave)({ mcp_servers: next });
    },
    [onSave, onSilentSave],
  );

  const refreshStatuses = useCallback(() => {
    void getMcpServers()
      .then((result) => {
        const next: Record<string, McpServerStatus | undefined> = {};
        for (const item of result.servers || []) next[item.id] = item;
        setStatuses(next);
      })
      .catch(() => {
        // 状态接口失败不打断配置编辑
      });
  }, []);

  useEffect(() => {
    refreshStatuses();
  }, [refreshStatuses]);

  // 刷新：退出 JSON 面板/表单回到列表视图，并重新拉取服务器状态
  const handleRefresh = () => {
    setJsonMode(false);
    setEditingId(null);
    setDraft(null);
    refreshStatuses();
  };

  const startCreate = () => {
    setJsonMode(false);
    const id = `mcp-${Date.now().toString(36)}`;
    setEditingId(id);
    setDraft({
      id,
      name: "",
      transport: "stdio",
      command: "",
      argsText: "",
      envText: "",
      url: "",
      enabled: true,
      trusted: false,
    });
  };

  const startEdit = (server: McpServerConfig) => {
    // 与 JSON 面板互斥
    setJsonMode(false);
    setEditingId(server.id);
    setDraft(toDraft(server));
  };

  const submitDraft = () => {
    if (!draft) return;
    const config = fromDraft(draft);
    if (!config.name) return;
    const exists = servers.some((item) => item.id === config.id);
    const next = exists
      ? servers.map((item) => (item.id === config.id ? config : item))
      : [...servers, config];
    persist(next);
    setEditingId(null);
    setDraft(null);
    // 新增/修改后刷新一次状态
    setTimeout(refreshStatuses, 300);
  };

  const removeServer = (server: McpServerConfig) => {
    const run = () => {
      persist(servers.filter((item) => item.id !== server.id));
    };
    if (onConfirm) {
      onConfirm(
        t("settings.mcp.deleteTitle", "删除 MCP 服务器"),
        t("settings.mcp.deleteConfirm", "确定删除 {{name}} 吗？", {
          name: server.name,
        }),
        run,
      );
    } else {
      run();
    }
  };

  const toggleEnabled = (server: McpServerConfig) => {
    persist(
      servers.map((item) => (item.id === server.id ? { ...item, enabled: !item.enabled } : item)),
    );
    setTimeout(refreshStatuses, 300);
  };

  const runTest = async (serverId: string) => {
    setStatuses((prev) => ({ ...prev, [serverId]: undefined }));
    try {
      const status = await testMcpServer(serverId);
      setStatuses((prev) => ({ ...prev, [serverId]: status }));
    } catch {
      setStatuses((prev) => ({
        ...prev,
        [serverId]: { id: serverId, status: "error", error: "network error" },
      }));
    }
  };

  const importJson = () => {
    try {
      const parsed = JSON.parse(jsonText);
      const raw = parsed.mcpServers ?? parsed;
      const imported: McpServerConfig[] = [];
      for (const [key, value] of Object.entries(raw as Record<string, Record<string, unknown>>)) {
        const entry = value || {};
        const url = typeof entry.url === "string" ? entry.url : "";
        imported.push({
          id: `mcp-${key.toLowerCase().replace(/[^a-z0-9_-]+/g, "-")}-${Math.random()
            .toString(36)
            .slice(2, 6)}`,
          name: key,
          transport: url ? "http" : "stdio",
          command: typeof entry.command === "string" ? entry.command : "",
          args: Array.isArray(entry.args) ? (entry.args as unknown[]).map(String) : [],
          env:
            entry.env && typeof entry.env === "object" ? (entry.env as Record<string, string>) : {},
          url,
          enabled: true,
        });
      }
      if (imported.length === 0) {
        setJsonError(t("settings.mcp.importEmpty", "没有解析到服务器配置"));
        return;
      }
      persist([...servers, ...imported]);
      setJsonMode(false);
      setJsonText("");
      setJsonError("");
      setTimeout(refreshStatuses, 300);
    } catch (exc) {
      setJsonError(
        t("settings.mcp.importInvalid", "JSON 解析失败：{{msg}}", {
          msg: String(exc).slice(0, 200),
        }),
      );
    }
  };

  const statusOf = (server: McpServerConfig): McpServerStatus | undefined => statuses[server.id];

  return (
    <div className="settings-form">
      <div className="settings-mcp-head">
        <p className="settings-field-hint-inline settings-models-hint settings-mcp-hint">
          {t(
            "settings.mcp.hint",
            "接入 MCP 外部工具服务器（本地进程 / HTTP）。配置保存后新对话生效；未标记信任的服务器执行前需要确认。",
          )}
        </p>
        <div className="settings-mcp-toolbar">
          <Button variant="secondary" onClick={handleRefresh}>
            <RefreshCw size={14} />
            {t("settings.mcp.refresh", "刷新状态")}
          </Button>
          <Button
            variant="secondary"
            onClick={() => {
              // 与新建/编辑表单互斥：打开 JSON 面板时收起表单
              setEditingId(null);
              setDraft(null);
              setJsonMode((v) => !v);
            }}
          >
            <Blocks size={14} />
            {t("settings.mcp.jsonImport", "JSON 导入")}
          </Button>
          <Button variant="secondary" onClick={startCreate}>
            <Plus size={14} />
            {t("settings.mcp.add", "添加服务器")}
          </Button>
        </div>
      </div>

      <div className="settings-mcp-list">
        {jsonMode ? (
          <div className="settings-mcp-json">
            <TextArea
              rows={8}
              placeholder={`{\n  "mcpServers": {\n    "github": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-github"]\n    }\n  }\n}`}
              value={jsonText}
              onChange={(event) => {
                setJsonText(event.target.value);
                setJsonError("");
              }}
            />
            {jsonError && <p className="settings-mcp-error">{jsonError}</p>}
            <div className="settings-mcp-toolbar">
              <Button variant="secondary" onClick={() => setJsonMode(false)}>
                {t("common.cancel", "取消")}
              </Button>
              <Button variant="primary" onClick={importJson}>
                {t("settings.mcp.import", "导入")}
              </Button>
            </div>
          </div>
        ) : editingId !== null && draft ? (
          // 新建/编辑表单独占列表区域：点击「添加服务器」时隐藏服务器列表
          <div className="settings-model-card settings-model-card--expanded">
            <McpDraftForm
              draft={draft}
              onDraftChange={setDraft}
              onSubmit={submitDraft}
              onCancel={() => {
                setEditingId(null);
                setDraft(null);
              }}
            />
          </div>
        ) : (
          <>
            {servers.length === 0 ? (
              <EmptyState
                icon={<Blocks size={26} />}
                title={t("settings.mcp.emptyTitle", "还没有接入 MCP 服务器")}
                description={t(
                  "settings.mcp.emptyHint",
                  "点击右上角「添加服务器」或「JSON 导入」接入外部工具，接入后 agent 可直接调用",
                )}
              />
            ) : null}
            {servers.map((server) => {
              const status = statusOf(server);
              const dotClass =
                status === undefined
                  ? "settings-mcp-dot--pending"
                  : status.status === "connected"
                    ? "settings-mcp-dot--ok"
                    : status.status === "disabled"
                      ? "settings-mcp-dot--off"
                      : "settings-mcp-dot--error";
              return (
                <div key={server.id} className="settings-model-card">
                  <div className="settings-model-card-header">
                    <span className={`settings-mcp-dot ${dotClass}`} />
                    <span className="settings-model-name">{server.name}</span>
                    <span className="settings-mcp-badge">
                      {server.transport === "http"
                        ? t("settings.mcp.http", "HTTP")
                        : t("settings.mcp.stdio", "本地进程")}
                    </span>
                    {server.trusted ? (
                      <span className="settings-mcp-badge">
                        {t("settings.mcp.trusted", "已信任")}
                      </span>
                    ) : null}
                    <span className="settings-mcp-summary">
                      {server.transport === "http"
                        ? server.url
                        : [server.command, ...(server.args || [])].join(" ")}
                    </span>
                  </div>
                  {status?.status === "error" && status.error ? (
                    <p className="settings-mcp-error">{status.error}</p>
                  ) : null}
                  {status?.tools && status.tools.length > 0 ? (
                    <div>
                      <div
                        className={`settings-custom-toggle${
                          expandedTools[server.id] ? " open" : ""
                        }`}
                      >
                        <div
                          className="settings-custom-toggle-header"
                          role="button"
                          tabIndex={0}
                          onClick={() =>
                            setExpandedTools((prev) => ({
                              ...prev,
                              [server.id]: !prev[server.id],
                            }))
                          }
                        >
                          {t("settings.mcp.toolsCount", "{{count}} 个工具", {
                            count: status.tools.length,
                          })}
                          <ChevronDown size={13} className="settings-custom-toggle-chevron" />
                        </div>
                        {expandedTools[server.id] ? (
                          <ul className="settings-mcp-tools">
                            {status.tools.map((tool) => (
                              <li key={tool.name}>
                                <code>{tool.name}</code>
                                {tool.description ? ` — ${tool.description}` : ""}
                              </li>
                            ))}
                          </ul>
                        ) : null}
                      </div>
                    </div>
                  ) : null}
                  <div className="settings-mcp-actions">
                    <Button variant="secondary" onClick={() => void runTest(server.id)}>
                      <PlugZap size={13} />
                      {t("settings.mcp.test", "测试连接")}
                    </Button>
                    <Switch
                      checked={server.enabled}
                      onChange={() => toggleEnabled(server)}
                      label={
                        server.enabled
                          ? t("settings.mcp.enabled", "已启用")
                          : t("settings.mcp.disabled", "已停用")
                      }
                    />
                    <Button variant="icon" onClick={() => startEdit(server)}>
                      <Pencil size={13} />
                    </Button>
                    <Button variant="icon" onClick={() => removeServer(server)}>
                      <Trash2 size={13} />
                    </Button>
                  </div>
                </div>
              );
            })}
          </>
        )}
      </div>
    </div>
  );
}

function McpDraftForm({
  draft,
  onDraftChange,
  onSubmit,
  onCancel,
}: {
  draft: DraftServer;
  onDraftChange: (draft: DraftServer) => void;
  onSubmit: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const patch = (part: Partial<DraftServer>) => onDraftChange({ ...draft, ...part });

  return (
    <div className="settings-mcp-form">
      <div className="settings-mcp-row">
        <Input
          label={t("settings.mcp.name", "名称")}
          value={draft.name}
          onChange={(event) => patch({ name: event.target.value })}
          placeholder="github"
        />
        <div className="settings-mcp-transport">
          <Select
            label={t("settings.mcp.transport", "类型")}
            value={draft.transport}
            onChange={(value) => patch({ transport: value as "stdio" | "http" })}
            options={[
              { value: "stdio", label: t("settings.mcp.stdio", "本地进程") },
              { value: "http", label: t("settings.mcp.http", "HTTP") },
            ]}
          />
        </div>
      </div>
      {draft.transport === "stdio" ? (
        <>
          <Input
            label={t("settings.mcp.command", "启动命令")}
            value={draft.command}
            onChange={(event) => patch({ command: event.target.value })}
            placeholder="npx"
          />
          <TextArea
            label={t("settings.mcp.args", "参数（每行一个）")}
            rows={2}
            value={draft.argsText}
            onChange={(event) => patch({ argsText: event.target.value })}
            placeholder={"-y\n@modelcontextprotocol/server-github"}
          />
          <TextArea
            label={t("settings.mcp.env", "环境变量（每行 KEY=VALUE，留空保留已存值）")}
            rows={2}
            value={draft.envText}
            onChange={(event) => patch({ envText: event.target.value })}
            placeholder={"GITHUB_TOKEN=••••••"}
          />
        </>
      ) : (
        <Input
          label={t("settings.mcp.url", "服务器地址")}
          value={draft.url}
          onChange={(event) => patch({ url: event.target.value })}
          placeholder="https://example.com/mcp"
        />
      )}
      <Switch
        checked={draft.trusted}
        onChange={(checked) => patch({ trusted: checked })}
        label={t("settings.mcp.trustHint", "信任该服务器（跳过执行前确认）")}
      />
      <div className="settings-mcp-toolbar">
        <Button variant="secondary" onClick={onCancel}>
          {t("common.cancel", "取消")}
        </Button>
        <Button variant="primary" onClick={onSubmit}>
          {t("common.save", "保存")}
        </Button>
      </div>
    </div>
  );
}
