// 提供商统一配置
// 所有提供商相关的配置都在这里维护，避免重复定义

export interface ProviderConfig {
  value: string;
  label: string;
  base_url: string;
  default_model: string;
  list: string[];      // 该提供商的可选模型列表
  prefix: string[];    // 用于根据模型名判断提供商
}

// 提供商列表（按顺序显示）
export const PROVIDER_LIST: ProviderConfig[] = [
  {
    value: "deepseek",
    label: "DeepSeek",
    base_url: "https://api.deepseek.com",
    default_model: "deepseek-v4-flash",
    list: [
      "deepseek-v4-flash",
      "deepseek-v4-flash-vision-exp",
      "deepseek-v4-pro",
    ],
    prefix: ["deepseek"],
  },
  {
    value: "xiaomi",
    label: "Xiaomi (MiMo)",
    base_url: "https://api.xiaomimimo.com/v1",
    default_model: "mimo-v2.5",
    list: ["mimo-v2.5", "mimo-v2.5-pro"],
    prefix: ["mimo"],
  },
  {
    value: "glm",
    label: "GLM (智谱)",
    base_url: "https://open.bigmodel.cn/api/paas/v4",
    default_model: "glm-5.3",
    list: [
      "glm-5.3",
      "glm-5.2",
      "glm-5",
      "glm-5v-turbo",
      "glm-4.7-flash",
      "glm-4.6v-flash",
    ],
    prefix: ["glm"],
  },
  {
    value: "openai",
    label: "OpenAI",
    base_url: "https://api.openai.com/v1",
    default_model: "gpt-5.5",
    list: [
      "gpt-5.6",
      "gpt-5.5",
      "gpt-5.4",
      "gpt-4.1",
      "gpt-4.1-mini",
      "gpt-4o",
    ],
    prefix: ["gpt"],
  },
  {
    value: "minimax",
    label: "MiniMax",
    base_url: "https://api.minimax.io/v1",
    default_model: "MiniMax-M3",
    list: ["MiniMax-M3", "MiniMax-M2.7", "MiniMax-M2.5", "MiniMax-M2.1"],
    prefix: ["minimax"],
  },
  {
    value: "qwen",
    label: "Qwen (通义千问)",
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    default_model: "qwen3.8-max",
    list: [
      "qwen3.8-max",
      "qwen3.7-max",
      "qwen3.7-plus",
      "qwen3.7-flash",
      "qwen3.6-plus",
      "qwen-vl-max",
    ],
    prefix: ["qwen"],
  },
  {
    value: "custom",
    label: "自定义",
    base_url: "",
    default_model: "",
    list: [],
    prefix: [],
  },
];

// 提供商 Map（方便查找）
export const PROVIDER_MAP = new Map<string, ProviderConfig>(
  PROVIDER_LIST.map(p => [p.value, p])
);

// 根据模型名获取提供商 key（仅作回退：当条目未显式保存 vendor 时使用）
export function getProviderFromModel(model: string): string {
  if (!model) return "";
  const modelLower = model.toLowerCase();
  
  for (const provider of PROVIDER_LIST) {
    if (provider.value === "custom") continue;  // 跳过自定义
    if (provider.prefix.some(p => modelLower.startsWith(p))) {
      return provider.value;
    }
  }
  
  // 如果模型名不匹配任何已知提供商，返回自定义
  return "custom";
}

/**
 * 获取条目实际的提供方 key。
 * 优先用用户显式保存的 vendor（避免 qwen2.5:14b 等本地模型被模型名前缀误判），
 * 兼容旧数据：没有 vendor 时回退到模型名反推。
 */
export function getEntryProvider<T extends { vendor?: string; model?: string; name?: string }>(
  entry: T
): string {
  const vendor = (entry.vendor || "").trim();
  if (vendor) return vendor;
  return getProviderFromModel(entry.model || entry.name || "");
}

// 获取提供商配置
export function getProviderConfig(provider: string): ProviderConfig | undefined {
  return PROVIDER_MAP.get(provider);
}

// 判断模型是否支持多模态（图片理解）
export function isMultimodalModel(modelName: string): boolean {
  if (!modelName) return false;
  const multimodalPrefixes = [
    "mimo-",
    "gpt-5",
    "gpt-4o",
    "gpt-4-vision",
    "claude-3",
    "gemini",
    "deepseek-v4-flash-vision",
    "glm-5v",
    "glm-4.6v",
    "glm-4v",
    "qwen-vl",
  ];
  const lower = modelName.toLowerCase();
  return multimodalPrefixes.some((prefix) => lower.startsWith(prefix));
}

// 为 Select 组件生成提供商选项格式
export const PROVIDER_OPTIONS = PROVIDER_LIST.map(p => ({
  value: p.value,
  label: p.label,
}));

// 获取提供商的模型选项列表（带多模态标记）
export function getModelOptionsForProvider(provider: string): { value: string; label: string }[] {
  const config = PROVIDER_MAP.get(provider);
  if (!config) return [];
  
  return config.list.map(model => ({
    value: model,
    label: isMultimodalModel(model) ? `${model} (多模态)` : model,
  }));
}

// 将模型列表按提供商分组（用于对话框模型切换）
export function groupModelsByProvider<
  T extends { vendor?: string; model?: string; name?: string }
>(
  models: T[]
): Map<string, T[]> {
  const groups = new Map<string, T[]>();
  
  // 按提供商顺序初始化
  for (const provider of PROVIDER_LIST) {
    groups.set(provider.value, []);
  }
  
  for (const model of models) {
    const providerKey = getEntryProvider(model);
    const group = groups.get(providerKey) || [];
    group.push(model);
    groups.set(providerKey, group);
  }
  
  // 移除空分组
  for (const [key, value] of groups.entries()) {
    if (value.length === 0) groups.delete(key);
  }
  
  return groups;
}

/**
 * 把配置的模型条目按提供商 list 展开为可切换的完整模型列表（用于对话框切换）。
 * 展开结果为：提供商预置 list + 用户自定义模型（custom_models，逗号分隔），去重。
 * 每项共享原条目的 base_url / api_key / tool_mode。
 * 展开项的 id 格式：`{原id}::{模型名}`。
 */
export function expandModelsForSwitcher<
  T extends {
    id: string;
    vendor?: string;
    model?: string;
    name?: string;
    custom_models?: string;
  }
>(
  models: T[]
): T[] {
  const expanded: T[] = [];
  for (const entry of models) {
    // 优先用用户显式保存的 vendor，避免本地模型名（如 qwen2.5:14b）被误判
    const providerKey = getEntryProvider(entry);
    const config = PROVIDER_MAP.get(providerKey);
    const base = config?.list?.length ? [...config.list] : [];
    // 自定义模型：支持中英文逗号分隔，拆分后追加到 list 之后并去重
    const custom = (entry.custom_models || "")
      .split(/[,，]/)
      .map((s) => s.trim())
      .filter(Boolean);
    const names = [...new Set([...base, ...custom])];
    if (names.length === 0) {
      const only = [entry.model || entry.name || ""].filter(Boolean);
      if (only.length === 0) {
        // 模型名为空：保留原条目，不做展开
        expanded.push(entry);
        continue;
      }
      for (const modelName of only) {
        expanded.push({
          ...entry,
          id: `${entry.id}::${modelName}`,
          name: modelName,
          model: modelName,
        });
      }
      continue;
    }
    for (const modelName of names) {
      expanded.push({
        ...entry,
        id: `${entry.id}::${modelName}`,
        name: modelName,
        model: modelName,
      });
    }
  }
  return expanded;
}

/** 把展开的模型 id（`原id::模型名`）解析为 { baseId, modelName }。 */
export function resolveModelId(
  modelId: string
): { baseId: string; modelName: string | null } {
  if (modelId.includes("::")) {
    const [baseId, ...rest] = modelId.split("::");
    return { baseId, modelName: rest.join("::") || null };
  }
  return { baseId: modelId, modelName: null };
}

/** 把原模型条目 id 映射为展开后的 id（默认选该条目当前配置的模型）。 */
export function expandModelId(
  modelId: string | null,
  models: Array<{ id: string; model?: string; name?: string }>
): string | null {
  if (!modelId) return null;
  if (modelId.includes("::")) return modelId; // 已是展开 id
  const entry = models.find((m) => m.id === modelId);
  if (!entry) return modelId;
  const providerKey = getProviderFromModel(entry.model || entry.name || "");
  const config = PROVIDER_MAP.get(providerKey);
  const targetModel = entry.model || config?.default_model || "";
  return targetModel ? `${entry.id}::${targetModel}` : entry.id;
}
