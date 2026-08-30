import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { searchSessions, type SearchResult } from "@/services/api";
import type { Session } from "@/types";
import "./SessionSearchModal.less";

interface SessionSearchModalProps {
  open: boolean;
  sessions: Session[];
  selectedId: string | null;
  projectId?: string | null;
  onClose: () => void;
  onSelect: (id: string) => void;
}

function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + "…";
}

export function SessionSearchModal({
  open,
  sessions,
  selectedId,
  projectId,
  onClose,
  onSelect,
}: SessionSearchModalProps) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(null);
  const abortRef = useRef<AbortController | null>(null);

  const doSearch = useCallback(
    async (q: string) => {
      const text = q.trim();
      if (!text) {
        setResults([]);
        return;
      }
      // 取消上一次请求
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const data = await searchSessions(text, projectId ?? undefined);
        if (!controller.signal.aborted) {
          setResults(data.sessions);
        }
      } catch {
        // 忽略取消的请求
      }
    },
    [projectId]
  );

  useEffect(() => {
    if (!open) {
      setQuery("");
      setResults([]);
      return;
    }
  }, [open]);

  const handleChange = useCallback(
    (value: string) => {
      setQuery(value);
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => doSearch(value), 300);
    },
    [doSearch]
  );

  const isSearching = query.trim().length > 0;
  const displayList = isSearching ? results : sessions;

  return (
    <Modal
      open={open}
      title={t("common.searchSessions", "搜索会话")}
      onClose={onClose}
      width={560}
    >
      <Input
        autoFocus
        value={query}
        onChange={(event) => handleChange(event.target.value)}
        placeholder={t("session.searchPlaceholder", "搜索标题或内容，支持拼音…")}
        aria-label={t("common.searchSessions", "搜索会话")}
      />
      <div className="session-search-results">
        {!isSearching && displayList.length === 0 && (
          <EmptyState title={t("session.noMatches", "没有匹配的会话")} />
        )}
        {isSearching && displayList.length === 0 && (
          <EmptyState title={t("session.noMatches", "没有匹配的会话")} />
        )}
        {displayList.map((session) => {
          const s = session as SearchResult;
          const subtitle = isSearching
            ? s.snippet
            : s.last_message
              ? truncate(s.last_message, 60)
              : undefined;
          return (
            <div
              key={s.id}
              role="button"
              tabIndex={0}
              className={`session-search-result${
                s.id === selectedId ? " active" : ""
              }`}
              onClick={() => {
                onSelect(s.id);
                onClose();
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(s.id);
                  onClose();
                }
              }}
            >
              <div className="session-search-result-content">
                <span className="session-search-title">{s.title}</span>
                {subtitle && (
                  <span
                    className="session-search-subtitle"
                    dangerouslySetInnerHTML={
                      isSearching ? { __html: subtitle } : undefined
                    }
                  >
                    {!isSearching ? subtitle : undefined}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </Modal>
  );
}
