import { useEffect, useMemo, useRef, useState } from "react";
import type { Virtualizer } from "@tanstack/react-virtual";
import { AlertCircle, LoaderCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { MarkdownView } from "@/pages/chat/components/MarkdownView";
import type { ChatMessage } from "@/types";

// marker 固定间距：会话极长时轨道高度超出 rail 可视区，由轨道内滚动承接
const MINIMAP_GAP = 8;
// minimap 高度上限：内容超高时 rail 钳制在此高度内，超出部分在滚动层内滚动
const MINIMAP_MAX_HEIGHT = 400;

interface ConversationMinimapProps {
  virtualizer: Virtualizer<HTMLDivElement, Element>;
  messages: ChatMessage[];
  scrollTop: number;
  viewportHeight: number;
}

interface MinimapEntry {
  id: string;
  index: number;
  offset: number;
  prompt: string;
  content: string;
  createdAt: string;
  streaming: boolean;
  error?: string;
}

export function ConversationMinimap({
  virtualizer,
  messages,
  scrollTop,
  viewportHeight,
}: ConversationMinimapProps) {
  const { t } = useTranslation();
  const railRef = useRef<HTMLDivElement>(null);
  const suppressHoverUntil = useRef(0);
  // 指针在 rail 上（悬停看预览/手动滚轮浏览）时暂停 active 自动跟随，离开后恢复。
  // 注意：不要在 pointerdown 里置 true——点击跳转应交给自动跟随，否则会永久锁死跟随
  const userDrivingRail = useRef(false);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // 滚动边缘状态：决定上/下渐变蒙版是否显示（轨道超高可滚时，到达顶/底则隐藏对应端）
  const [railAtTop, setRailAtTop] = useState(true);
  const [railAtBottom, setRailAtBottom] = useState(true);

  const entries = useMemo(() => {
    const result: MinimapEntry[] = [];
    let lastUserPrompt = "";
    for (let index = 0; index < messages.length; index++) {
      const message = messages[index];
      if (message.role === "user") {
        if (message.content.trim()) {
          lastUserPrompt = message.content.trim();
        }
        continue;
      }
      const measurement = virtualizer.measurementsCache[index];
      const start = measurement?.start ?? index * 140;
      const size = measurement?.size ?? 140;
      result.push({
        id: message.id,
        index,
        offset: start + size / 2,
        prompt: lastUserPrompt,
        content: message.content,
        createdAt: message.created_at,
        streaming: Boolean(message.streaming),
        error: message.error,
      });
    }
    return result;
  }, [messages, virtualizer]);

  // 轨道内容自然高：marker 固定间距铺开（含上下各 8px 呼吸空间）
  const trackHeight = Math.max(18, Math.max(entries.length - 1, 0) * MINIMAP_GAP + 16);
  // rail 可视高：短会话按内容自然高自适应；超过 400px（或视口更矮时按视口）钳制，
  // 杜绝随消息数无限长高/溢出窗口，超高部分由滚动层承接
  const railHeight = useMemo(() => {
    const natural = Math.max(24, Math.max(entries.length - 1, 0) * 10 + 18);
    const cap = Math.min(MINIMAP_MAX_HEIGHT, viewportHeight || MINIMAP_MAX_HEIGHT);
    return Math.max(24, Math.min(natural, cap));
  }, [entries.length, viewportHeight]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 从派生条目回收已消失的选中 id（外部状态同步，函数式更新自带守卫）
    setSelectedId((current) =>
      current && entries.some((entry) => entry.id === current) ? current : null,
    );
  }, [entries]);

  const positionedEntries = useMemo(() => {
    // marker 固定间距铺开：内容不足时整组在 rail 可视区内垂直居中；
    // 超出（trackHeight > railHeight）时贴顶布局，超出部分由滚动层承接。
    const padTop = 8 + Math.max(0, (railHeight - trackHeight) / 2);
    return entries.map((entry, index) => ({
      ...entry,
      top: Math.round(padTop + index * MINIMAP_GAP),
    }));
  }, [entries, railHeight, trackHeight]);

  const activeEntry = useMemo(() => {
    if (positionedEntries.length === 0) return null;
    const targetOffset = scrollTop + (viewportHeight || 600) * 0.35;
    let active = positionedEntries[0];
    for (const entry of positionedEntries) {
      if (entry.offset <= targetOffset) {
        active = entry;
      } else {
        break;
      }
    }
    return active;
  }, [positionedEntries, scrollTop, viewportHeight]);

  const hoveredIndex = hoveredId
    ? positionedEntries.findIndex((entry) => entry.id === hoveredId)
    : -1;
  const hoveredEntry = positionedEntries.find((entry) => entry.id === hoveredId) ?? null;
  const previewTop = Math.max(8, Math.round((railHeight - 120) / 2));
  // 轨道是否超高可滚（与滚动层 scrollHeight>clientHeight 一致，纯派生避免首帧闪烁）
  const railScrollable = trackHeight > railHeight + 1;

  // 轨道滚动时同步蒙版显隐：顶部/底部还有内容可读则淡出提示，滚到尽头则隐藏
  const handleRailScroll = (rail: HTMLDivElement) => {
    setRailAtTop(rail.scrollTop <= 2);
    const maxScroll = rail.scrollHeight - rail.clientHeight;
    setRailAtBottom(maxScroll <= 0 || rail.scrollTop >= maxScroll - 2);
  };

  // 消息滚动时轨道持续自动跟随：把 active 指示 marker 带到 rail 可视中部。
  // 相比边缘触发式（出界才滚 8px），幅度明显且 marker 恒可见；
  // 指针在 rail 上（userDrivingRail）时暂停，离开后恢复。
  // activeEntry 随 scrollTop 高频重建，同 marker 期间的重复调用走 early-return，开销可忽略
  useEffect(() => {
    if (!activeEntry || userDrivingRail.current) return;
    const rail = railRef.current;
    if (!rail || rail.scrollHeight <= rail.clientHeight) return;
    handleRailScroll(rail); // scrollTop 程序赋值派发的 scroll 事件是异步的，先按当前值同步一次
    const target = activeEntry.top - (rail.clientHeight - MINIMAP_GAP) / 2;
    const next = Math.max(0, Math.min(rail.scrollHeight - rail.clientHeight, target));
    if (Math.abs(rail.scrollTop - next) > 0.5) {
      rail.scrollTop = next;
      handleRailScroll(rail); // 设置后本帧立即同步蒙版，不等异步事件
    }
  }, [activeEntry, railHeight]);

  if (entries.length === 0) return null;

  const hoverAt = (clientY: number): MinimapEntry | null => {
    const rail = railRef.current;
    if (!rail) return null;
    const rect = rail.getBoundingClientRect();
    // rail 自身可滚动：指针可视 Y 需加上 scrollTop 折算成轨道内容坐标
    const localY = clientY - rect.top + rail.scrollTop;
    let nearest = positionedEntries[0] ?? null;
    let bestDistance = Number.POSITIVE_INFINITY;
    for (const entry of positionedEntries) {
      const distance = Math.abs(entry.top - localY);
      if (distance < bestDistance) {
        bestDistance = distance;
        nearest = entry;
      }
    }
    return nearest;
  };

  const scrollToEntry = (entry: MinimapEntry) => {
    virtualizer.scrollToIndex(entry.index, {
      align: "center",
      behavior: "smooth",
    });
  };

  return (
    <div
      className="conversation-minimap"
      style={{ height: railHeight }}
      role="navigation"
      aria-label={t("chat.minimapLabel", "对话导航")}
      onPointerLeave={() => {
        suppressHoverUntil.current = 0;
        userDrivingRail.current = false;
        setHoveredId(null);
      }}
    >
      <div
        ref={railRef}
        className="conversation-minimap-scroll"
        onPointerEnter={() => {
          userDrivingRail.current = true;
        }}
        onScroll={(event) => {
          handleRailScroll(event.currentTarget);
        }}
        onPointerMove={(event) => {
          if (Date.now() < suppressHoverUntil.current) return;
          setHoveredId(hoverAt(event.clientY)?.id ?? null);
        }}
        onPointerDown={(event) => {
          if (event.button !== 0) return;
          suppressHoverUntil.current = Number.POSITIVE_INFINITY;
          setHoveredId(null);
          const entry = hoverAt(event.clientY);
          if (entry) {
            setSelectedId(entry.id);
            scrollToEntry(entry);
          }
        }}
      >
        <div className="conversation-minimap-track" style={{ height: trackHeight }}>
          {positionedEntries.map((entry, index) => {
            const hovered = entry.id === hoveredId;
            const selected = entry.id === selectedId;
            const active = !selectedId && activeEntry?.id === entry.id;
            const waveDistance = hoveredIndex >= 0 ? Math.abs(index - hoveredIndex) : -1;
            return (
              <span
                key={entry.id}
                className={`minimap-marker${active ? " active" : ""}${selected ? " selected" : ""}${
                  hovered ? " hovered" : ""
                }${waveDistance >= 1 && waveDistance <= 3 ? ` wave-${waveDistance}` : ""}${
                  entry.streaming ? " streaming" : ""
                }${entry.error ? " error" : ""}`}
                style={{ top: entry.top }}
              />
            );
          })}
        </div>
      </div>
      {/* 上下渐变蒙版：轨道超高可滚时，指示未滚尽的方向仍有内容；滚到尽头该端淡出 */}
      <div
        className={`conversation-minimap-fade top${railScrollable && !railAtTop ? " visible" : ""}`}
      />
      <div
        className={`conversation-minimap-fade bottom${
          railScrollable && !railAtBottom ? " visible" : ""
        }`}
      />
      {hoveredEntry && (
        <div className="minimap-preview" style={{ top: previewTop }}>
          {hoveredEntry.prompt && (
            <div className="minimap-preview-title">{hoveredEntry.prompt}</div>
          )}
          <div className="minimap-preview-answer">
            {hoveredEntry.streaming && (
              <span className="minimap-preview-streaming">
                <LoaderCircle size={12} className="spin" />
              </span>
            )}
            {hoveredEntry.error && (
              <span className="minimap-preview-error">
                <AlertCircle size={12} />
              </span>
            )}
            <div className="minimap-preview-markdown">
              <MarkdownView content={hoveredEntry.content} streaming={false} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
