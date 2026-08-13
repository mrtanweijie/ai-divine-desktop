import { readFileSync, writeFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { Converter } from "opencc-js";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const zhCNPath = resolve(root, "src/i18n/locales/zh-CN/translation.json");
const zhTWPath = resolve(root, "src/i18n/locales/zh-TW/translation.json");

const toTraditional = Converter({ from: "cn", to: "tw" });

// Ordered replacements so specific phrases win over generic terms.
const TERMS = [
  ["批量", "批次"],
  ["剪贴板", "剪貼簿"],
  ["交互", "互動"],
  ["磁盤", "磁碟"],
  ["調用", "呼叫"],
  ["用戶級", "使用者層級"],
  ["用戶名", "使用者名稱"],
  ["文件樹", "檔案樹"],
  ["文件夾", "資料夾"],
  ["系統日曆", "系統行事曆"],
  ["桌面端", "桌面版"],
  ["本地演示", "本機示範"],
  ["發送", "傳送"],
  ["打開", "開啟"],
  ["設置", "設定"],
  ["保存", "儲存"],
  ["搜索", "搜尋"],
  ["刷新", "重新整理"],
  ["用戶", "使用者"],
  ["項目", "專案"],
  ["會話", "對話"],
  ["卸載", "卸載"],
  ["文件", "檔案"],
  ["加載", "載入"],
  ["查看", "檢視"],
  ["創建", "建立"],
  ["新建", "新增"],
  ["日曆", "行事曆"],
  ["日程", "行程"],
  ["生成", "產生"],
  ["列表", "清單"],
  ["抓取", "擷取"],
  ["腳本", "指令碼"],
  ["源碼", "原始碼"],
  ["消息", "訊息"],
  ["默認", "預設"],
  ["計劃", "計畫"],
  ["支持", "支援"],
  ["訪問", "存取"],
  ["互聯網", "網際網路"],
  ["演示", "示範"],
  ["內置", "內建"],
  ["文本", "文字"],
  ["依賴", "相依性"],
  ["正文", "內文"],
  ["重新命名", "重新命名"],
  ["複製", "複製"],
  ["代碼", "程式碼"],
  ["數據", "資料"],
  ["審核", "審核"],
  ["信息", "資訊"],
  ["二進制", "二進位"],
  ["圖標", "圖示"],
  ["導出", "匯出"],
  ["匹配", "符合"],
  ["字符", "字元"],
  ["添加", "新增"],
  ["改動", "變更"],
  ["拖拽", "拖曳"],
];

function convertValue(value) {
  let result = toTraditional(value);
  for (const [from, to] of TERMS) {
    result = result.split(from).join(to);
  }
  return result;
}

function fillFromZhCN(zhCNSection, targetSection) {
  const output = {};
  const zhCNKeys = Object.keys(zhCNSection ?? {});
  const targetKeys = Object.keys(targetSection ?? {});
  for (const key of new Set([...zhCNKeys, ...targetKeys])) {
    const existing = targetSection?.[key];
    if (existing && typeof existing === "object") {
      output[key] = fillFromZhCN(zhCNSection?.[key], existing);
    } else if (existing !== undefined) {
      output[key] = existing;
    } else {
      const baseKey = key.replace(/_(one|other|few|many|zero|two)$/, "");
      const source = zhCNSection?.[baseKey] ?? zhCNSection?.[key] ?? "";
      output[key] = convertValue(source);
    }
  }
  return output;
}

const zhCN = JSON.parse(readFileSync(zhCNPath, "utf8"));
const zhTWCurrent = JSON.parse(readFileSync(zhTWPath, "utf8"));
const zhTW = fillFromZhCN(zhCN, zhTWCurrent);
writeFileSync(zhTWPath, `${JSON.stringify(zhTW, null, 2)}\n`);
console.log("zh-TW updated");
