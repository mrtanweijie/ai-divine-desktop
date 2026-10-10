/**
 * A2UI 面板样式样张（**临时验证基座**，不入产品代码）。
 *
 * 用途：改 `UISurface.less` 后，不走「让模型吐 IR」那条链路也能看到真实效果。
 * 走的是**真解析 + 真组件**（`parseUISurfaceIR` → `UISurfaceBlock`），
 * 所以样式、token、深浅色都是产品路径上的同一套。
 *
 * 用法：`pnpm dev` 后打开
 *   http://localhost:8010/ui-harness.html            （浅色）
 *   http://localhost:8010/ui-harness.html?theme=dark （深色）
 *   ...&narrow=1                                      （360px 窄窗）
 *   ...&only=table,stats                              （只渲染指定块，便于放大看细节）
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@/i18n";
import { parseUISurfaceIR } from "@/pages/chat/components/UISurface/parseUISurface";
import { UISurfaceBlock } from "@/pages/chat/components/UISurface/UISurfaceBlock";

const params = new URLSearchParams(location.search);
document.documentElement.dataset.theme = params.get("theme") === "dark" ? "dark" : "light";
if (params.get("narrow") === "1") document.body.classList.add("is-narrow");

/** 复刻「本月成本看板」：覆盖 Card（有/无 tone）、Table、输入行、按钮行。 */
const IR = {
  surfaceId: "harness-cost",
  title: "本月成本看板",
  data: { laborRatio: 58, headcount: 120, growth: 8 },
  actions: ["recalc", "reset"],
  components: [
    { id: "root", component: "Column", gap: "md", children: ["concl", "stats", "inputs", "table"] },

    { id: "concl", component: "Card", title: "本月成本结论", child: "concl-col" },
    { id: "concl-col", component: "Column", gap: "sm", children: ["concl-text", "concl-badges"] },
    {
      id: "concl-text",
      component: "Text",
      variant: "body",
      text: "本月总成本 ¥486.0 万，环比上升 6.8%，人力是最大成本项。",
    },
    {
      id: "concl-badges",
      component: "Row",
      gap: "sm",
      align: "center",
      wrap: true,
      children: ["b1", "b2", "b3"],
    },
    { id: "b1", component: "Badge", text: "总成本环比 +6.8%", tone: "danger" },
    { id: "b2", component: "Badge", text: "人力占比 58.0%" },
    { id: "b3", component: "Badge", text: "人均成本 2.35 万元" },

    // 四个统计块：Card 带 title（竖条）+ 两句文本组成的内容
    {
      id: "stats",
      component: "Row",
      gap: "md",
      align: "stretch",
      children: ["s1", "s2", "s3", "s4"],
    },
    { id: "s1", component: "Card", title: "本月总成本", child: "s1c" },
    { id: "s1c", component: "Column", gap: "none", children: ["s1v", "s1n"] },
    { id: "s1v", component: "Text", variant: "h3", text: "486.0 万元" },
    { id: "s1n", component: "Text", variant: "caption", text: "环比 +6.8%" },

    { id: "s2", component: "Card", title: "人力成本", child: "s2c" },
    { id: "s2c", component: "Column", gap: "none", children: ["s2v", "s2n"] },
    { id: "s2v", component: "Text", variant: "h3", text: "282.0 万元" },
    { id: "s2n", component: "Text", variant: "caption", text: "占比 58.0%" },

    { id: "s3", component: "Card", title: "非人力成本", child: "s3c" },
    { id: "s3c", component: "Column", gap: "none", children: ["s3v", "s3n"] },
    { id: "s3v", component: "Text", variant: "h3", text: "204.0 万元" },
    { id: "s3n", component: "Text", variant: "caption", text: "占比 42.0%" },

    { id: "s4", component: "Card", title: "人均成本", tone: "success", child: "s4c" },
    { id: "s4c", component: "Column", gap: "none", children: ["s4v", "s4n"] },
    { id: "s4v", component: "Text", variant: "h3", text: "2.35 万元/人" },
    { id: "s4n", component: "Text", variant: "caption", text: "团队 120 人" },

    { id: "inputs", component: "Card", title: "人力占比测算", child: "inputs-col" },
    { id: "inputs-col", component: "Column", gap: "md", children: ["inputs-row", "actions-row"] },
    {
      id: "inputs-row",
      component: "Row",
      gap: "md",
      align: "end",
      wrap: true,
      children: ["f1", "f2", "f3"],
    },
    {
      id: "f1",
      component: "NumberField",
      label: "人力成本占比（%）",
      value: { path: "/laborRatio" },
      min: 0,
      max: 100,
      step: 1,
      unit: "%",
    },
    {
      id: "f2",
      component: "NumberField",
      label: "团队人数（人）",
      value: { path: "/headcount" },
      min: 1,
      unit: "人",
    },
    {
      id: "f3",
      component: "NumberField",
      label: "业务量环比增长（%）",
      value: { path: "/growth" },
      step: 0.1,
      unit: "%",
    },
    { id: "actions-row", component: "Row", gap: "sm", align: "center", children: ["btn1", "btn2"] },
    {
      id: "btn1",
      component: "Button",
      text: "重新测算",
      variant: "primary",
      action: { name: "recalc" },
    },
    {
      id: "btn2",
      component: "Button",
      text: "恢复默认",
      variant: "ghost",
      action: { name: "reset" },
    },

    { id: "table", component: "Card", title: "成本项明细", child: "tbl" },
    {
      id: "tbl",
      component: "Table",
      columns: [
        { key: "item", title: "成本项" },
        { key: "money", title: "金额（万元）" },
        { key: "ratio", title: "占比" },
        { key: "mom", title: "环比" },
      ],
      rows: [
        { item: "人力成本", money: "282.0", ratio: "58.0%", mom: "+6.8%" },
        { item: "服务器与带宽", money: "100.0", ratio: "20.6%", mom: "+4.2%" },
        { item: "营销投放", money: "54.0", ratio: "11.1%", mom: "+12.5%" },
        { item: "办公与差旅", money: "30.0", ratio: "6.2%", mom: "-1.8%" },
        { item: "第三方服务", money: "20.0", ratio: "4.1%", mom: "+2.1%" },
        { item: "合计", money: "486.0", ratio: "100.0%", mom: "+6.8%" },
      ],
    },
  ],
};

// ?only=table,stats —— 只保留指定块（放大看某个块的细节用）。
const only = params.get("only");
if (only) {
  (IR.components[0] as { children: string[] }).children = only.split(",");
}

const parsed = parseUISurfaceIR(IR, { seq: 1, status: "live" });
const stage = document.getElementById("stage");

if (!parsed.ok) {
  const error = document.createElement("pre");
  error.style.cssText = "color:var(--color-danger);font-size:12px;white-space:pre-wrap";
  error.textContent = `样张 IR 没通过解析：${parsed.reason}`;
  stage?.appendChild(error);
} else {
  const host = document.createElement("div");
  stage?.appendChild(host);
  createRoot(host).render(
    <StrictMode>
      <UISurfaceBlock surface={parsed.surface} sessionId={null} workspacePath={null} />
    </StrictMode>,
  );
}
