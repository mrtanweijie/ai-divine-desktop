# 工具插件机制

从 v0.2.1 起，工具注册中心支持**运行时插件**：把 Python 文件放进
`data/plugins/` 目录，sidecar 启动时会自动加载并注册其中用
`@register_tool` 装饰器声明的工具。

## 快速开始

创建 `data/plugins/my_tool.py`：

```python
from __future__ import annotations

from typing import Any

from app.tools.base import ToolAdapter, ToolResult
from app.tools.registry import register_tool


@register_tool(
    "my_tool",
    "我的自定义工具：做某件事",
    {
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "输入参数"},
        },
        "required": ["input"],
    },
)
class MyToolAdapter(ToolAdapter):
    category = "custom"
    timeout = 30

    async def run(self, workspace, arguments, locale=None, progress_callback=None):
        # 在这里实现工具逻辑
        return ToolResult(success=True, message="完成", content="结果内容")
```

重启 sidecar（或调用插件重载接口）后，`my_tool` 就出现在工具列表里，
Agent 可以直接调用它——审批、终端策略、超时、工具运行记录等执行管线
与内置工具完全一致。

## 机制说明

- **加载时机**：sidecar 启动时（`app/main.py` lifespan）扫描
  `data/plugins/` 下所有 `*.py` 文件，逐个导入并注册。
- **命名空间**：每个插件以 `divine_plugin_<文件名>` 的独立顶层模块名导入，
  无需包结构；文件名以下划线开头（如 `_disabled.py`）会被跳过。
- **幂等**：同一插件文件不会重复加载（按模块名去重）。
- **容错**：单个插件导入失败只记日志、跳过该插件，不影响服务启动。
- **卸载**：`ToolRegistry.unregister(name)` 可按名移除（API 层预留，
  下个会话生效，因 LLM schema 已在当前会话注入）。
- **打包**：插件是运行时用户文件，不随 PyInstaller 打包；内置 60 个工具
  的 hiddenimports 保持不变。

## 参考

- 示例插件：`data/plugins/example_hello.py`
- 注册中心实现：`app/tools/registry.py`
- 内置工具注册：`app/tools/adapters/__init__.py`
