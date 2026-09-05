import { useEffect, useMemo, useRef, useState } from "react";
import type { Virtualizer } from "@tanstack/react-virtual";
import { AlertCircle, LoaderCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { MarkdownView } from "@/pages/chat/components/MarkdownView";
import type { ChatMessage } from "@/types";

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
  const [railHeight, setRailHeight] = useState(0);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    const rail = railRef.current;
    if (!rail) return;
    const updateHeight = () => setRailHeight(rail.clientHeight);
    updateHeight();
    const observer = new ResizeObserver(updateHeight);
    observer.observe(rail);
    return () => observer.disconnect();
  }, []);

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

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 从派生条目回收已消失的选中 id（外部状态同步，函数式更新自带守卫）
    setSelectedId((current) =>
      current && entries.some((entry) => entry.id === current) ? current : null,
    );
  }, [entries]);

  const positionedEntries = useMemo(() => {
    const usableHeight = Math.max(railHeight - 16, 0);
    const gap = Math.min(8, usableHeight / Math.max(entries.length - 1, 1));
    const totalSpan = Math.max(entries.length - 1, 0) * gap;
    const start = 8 + Math.max(0, (usableHeight - totalSpan) / 2);
    return entries.map((entry, index) => ({
      ...entry,
      top: usableHeight > 0 ? start + index * gap : 0,
    }));
  }, [entries, railHeight]);

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
  const previewTop = Math.max(8, Math.round((railHeight - 150) / 2));

  if (entries.length === 0) return null;
  const contentHeight =
    entries.length > 0
      ? Math.max(
          24,
          Math.min(
            (entries.length - 1) * 10 + 18,
            viewportHeight || (entries.length - 1) * 10 + 18,
          ),
        )
      : undefined;

  const hoverAt = (clientY: number): MinimapEntry | null => {
    const rail = railRef.current;
    if (!rail) return null;
    const rect = rail.getBoundingClientRect();
    const localY = clientY - rect.top;
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
      ref={railRef}
      className="conversation-minimap"
      style={{ height: contentHeight }}
      role="navigation"
      aria-label={t("chat.minimapLabel", "对话导航")}
      onPointerMove={(event) => {
        if (Date.now() < suppressHoverUntil.current) return;
        setHoveredId(hoverAt(event.clientY)?.id ?? null);
      }}
      onPointerLeave={() => {
        suppressHoverUntil.current = 0;
        setHoveredId(null);
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
