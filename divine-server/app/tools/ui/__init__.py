"""A2UI 接入的协议层。

设计文档：``docs/design/028-a2ui-integration-20261009.md``（编号 044）。

三个子模块，职责互不重叠：

- :mod:`~app.tools.ui.catalog` —— **唯一真源**：组件枚举 / 属性表 / 限额 /
  tone 集合 / action 规则。``divine_catalog.json`` 由它生成，前端
  ``UISurface/types.ts`` 手工镜像（与 GraphIR 同范式）。
- :mod:`~app.tools.ui.validator` —— 中立 IR 的校验：未知组件/属性、引用缺失、
  成环、超限一律**硬报错**，报错文本携带合法枚举，让模型自纠后重试。
- :mod:`~app.tools.ui.versions` —— **协议版本边界**。业务侧只产出中立 IR；
  升级到 A2UI v1.0 时只改这里的一个模块。
"""

from __future__ import annotations

from .catalog import A2UI_VERSION, CATALOG_ID

__all__ = ["A2UI_VERSION", "CATALOG_ID"]
