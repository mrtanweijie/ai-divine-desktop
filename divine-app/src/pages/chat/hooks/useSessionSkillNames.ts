// 会话可见技能名集合的 React 绑定：数据与缓存见 services/skillNames.ts。
import { useEffect, useState } from "react";
import { getSessionSkillNames, peekSessionSkillNames } from "@/services/skillNames";

/**
 * 返回当前会话可用技能名集合（已按 `normalizeSkillName` 归一）。
 *
 * `undefined` = 集合尚未就绪或取不到 → 调用方退回纯词法判断：宁可多标一个胶囊，
 * 也不要把真技能降级成普通文本。
 */
export function useSessionSkillNames(sessionId?: string | null): ReadonlySet<string> | undefined {
  const key = sessionId || "__default__";
  const [state, setState] = useState<{ key: string; names?: ReadonlySet<string> }>(() => ({
    key,
    names: peekSessionSkillNames(sessionId),
  }));

  useEffect(() => {
    const cached = peekSessionSkillNames(sessionId);
    if (cached) {
      setState({ key, names: cached });
      return;
    }
    let alive = true;
    void getSessionSkillNames(sessionId).then((names) => {
      if (alive && names) setState({ key, names });
    });
    return () => {
      alive = false;
    };
  }, [key, sessionId]);

  // 会话切换的同一帧内 state 仍是旧会话的集合 → 视为未就绪，不拿它做判定
  return state.key === key ? state.names : undefined;
}
