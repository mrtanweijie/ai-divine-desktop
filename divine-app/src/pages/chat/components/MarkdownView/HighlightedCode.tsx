import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { CodeToTokenTransformStream, type RecallToken } from "@shikijs/stream";
import type { ThemedToken } from "shiki";
import { useTheme } from "@/services/theme";
import { normalizeLanguage } from "./language";

interface HighlightedCodeProps {
  code: string;
  language?: string;
  streaming: boolean;
}

interface StreamHandle {
  enqueue: (chunk: string) => void;
  cancel: () => void;
  prevCode: string;
}

function tokenStyle(token: ThemedToken): CSSProperties {
  if (token.htmlStyle) {
    return { ...token.htmlStyle } as CSSProperties;
  }
  const style: CSSProperties = {};
  if (token.color) style.color = token.color;
  if (token.bgColor) style.backgroundColor = token.bgColor;
  const font = token.fontStyle;
  if (font) {
    if (font & 1) style.fontStyle = "italic";
    if (font & 2) style.fontWeight = "bold";
    if (font & 4) style.textDecoration = "underline";
  }
  return style;
}

function flattenLines(lines: ThemedToken[][]): ThemedToken[] {
  const flat: ThemedToken[] = [];
  for (let index = 0; index < lines.length; index += 1) {
    if (index > 0) flat.push({ content: "\n", offset: 0 });
    flat.push(...lines[index]);
  }
  return flat;
}

function createStreamHandle(
  language: string,
  sink: (token: ThemedToken | RecallToken) => void,
  theme: "dark" | "light",
): StreamHandle {
  let source: ReadableStreamDefaultController<string> | null = null;
  let cancelled = false;
  const readable = new ReadableStream<string>({
    start(controller) {
      source = controller;
    },
  });

  void import("./shiki")
    .then(async ({ getHighlighter, highlightTheme }) => {
      const highlighter = await getHighlighter();
      if (cancelled) return;
      const tokenStream = readable.pipeThrough(
        new CodeToTokenTransformStream({
          highlighter,
          lang: language,
          theme: highlightTheme(theme),
          allowRecalls: true,
        }),
      );
      await tokenStream
        .pipeTo(
          new WritableStream<ThemedToken | RecallToken>({
            write(token) {
              if (!cancelled) sink(token);
            },
          }),
        )
        .catch(() => undefined);
    })
    .catch(() => undefined);

  return {
    enqueue(chunk) {
      if (!chunk || cancelled) return;
      try {
        source?.enqueue(chunk);
      } catch {
        // stream may already be closed after a recall flush
      }
    },
    cancel() {
      cancelled = true;
      try {
        source?.close();
      } catch {
        // stream may already be closed
      }
    },
    prevCode: "",
  };
}

export function HighlightedCode({ code, language, streaming }: HighlightedCodeProps) {
  const lang = normalizeLanguage(language);
  const theme = useTheme();
  const [tokens, setTokens] = useState<ThemedToken[]>([]);
  const streamRef = useRef<StreamHandle | null>(null);
  const pendingCodeRef = useRef(code);
  // 流式高亮的 sink 是每个语法 token 回调一次（200 行代码块 2000+ 次），
  // 且回调来自异步微任务、React 不会自动合并 → 逐 token setState 是
  // O(n²) 渲染放大的最大来源。这里只进缓冲区，rAF 按帧合并成一次
  // setState（B1），批量内保持 recall/push 的相对顺序。
  const pendingTokensRef = useRef<Array<ThemedToken | RecallToken>>([]);
  const rafRef = useRef<number | null>(null);

  const discardPendingTokens = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    pendingTokensRef.current = [];
  }, []);

  const applyToken = useCallback((token: ThemedToken | RecallToken) => {
    pendingTokensRef.current.push(token);
    if (rafRef.current !== null) return;
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      const batch = pendingTokensRef.current;
      if (!batch.length) return;
      pendingTokensRef.current = [];
      setTokens((prev) => {
        const next = prev.slice();
        for (const item of batch) {
          if ("recall" in item) {
            if (item.recall > 0) next.splice(-item.recall, item.recall);
          } else {
            next.push(item);
          }
        }
        return next;
      });
    });
  }, []);

  useEffect(() => {
    pendingCodeRef.current = code;
  }, [code]);

  useEffect(() => {
    if (!streaming) return;
    const handle = createStreamHandle(lang, applyToken, theme);
    streamRef.current = handle;
    const initial = pendingCodeRef.current;
    if (initial) {
      handle.enqueue(initial);
      handle.prevCode = initial;
    }
    return () => {
      handle.cancel();
      streamRef.current = null;
      discardPendingTokens();

      setTokens([]);
    };
  }, [lang, streaming, theme, applyToken, discardPendingTokens]);

  useEffect(() => {
    if (!streaming) return;
    const handle = streamRef.current;
    if (!handle) return;
    if (code.startsWith(handle.prevCode)) {
      const delta = code.slice(handle.prevCode.length);
      if (delta) {
        handle.enqueue(delta);
        handle.prevCode = code;
      }
      return;
    }
    handle.cancel();
    discardPendingTokens();
    setTokens([]);
    const next = createStreamHandle(lang, applyToken, theme);
    streamRef.current = next;
    next.enqueue(code);
    next.prevCode = code;
  }, [code, lang, streaming, theme, applyToken, discardPendingTokens]);

  useEffect(() => {
    if (streaming) return;
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 取消护栏：整段重高亮前清空旧 token
    setTokens([]);
    void import("./shiki")
      .then(({ getHighlighter, highlightTheme }) => {
        return getHighlighter().then((highlighter) => ({
          highlighter,
          highlightTheme,
        }));
      })
      .then((highlighter) => {
        if (cancelled) return;
        try {
          const result = highlighter.highlighter.codeToTokens(code, {
            lang,
            theme: highlighter.highlightTheme(theme),
          });
          if (!cancelled) setTokens(flattenLines(result.tokens));
        } catch {
          // unknown or truncated language falls back to plain text
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [code, lang, streaming, theme]);

  return (
    <code className="shiki-code">
      {tokens.length > 0
        ? tokens.map((token, index) => (
            <span key={index} style={tokenStyle(token)}>
              {token.content}
            </span>
          ))
        : code}
    </code>
  );
}
