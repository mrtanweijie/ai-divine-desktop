import {
  createContext,
  useContext,
  useEffect,
  useId,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react";

/**
 * 预览头部动作插槽：叶子视图（如 DocumentPreview）把自己的动作按钮注册进来，
 * 由外层 diff-view-head 里的 <PreviewHeaderSlot /> 统一渲染，
 * 避免「外层文件名头部 + 内层预览头部」两行堆叠占空间。
 *
 * 实现说明：Provider 持有一个极小的外部 store（Map + 版本号），
 * Slot 用 useSyncExternalStore 订阅——注册方变化只触发 Slot 局部重渲染，
 * 不会连带重渲染整个预览子树。
 */
function createSlotStore() {
  const listeners = new Set<() => void>();
  const nodes = new Map<string, ReactNode>();
  let version = 0;
  const emit = () => {
    version += 1;
    listeners.forEach((listener) => listener());
  };
  return {
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    getSnapshot: () => version,
    getNodes: () => Array.from(nodes.values()),
    set(id: string, node: ReactNode) {
      nodes.set(id, node);
      emit();
    },
    remove(id: string) {
      if (nodes.delete(id)) emit();
    },
  };
}

type SlotStore = ReturnType<typeof createSlotStore>;

const SlotContext = createContext<SlotStore | null>(null);
// 是否处于面板头部宿主内：聊天消息侧复用同一预览组件时没有 Provider，需保留自带头部
const HostContext = createContext(false);

const noopSubscribe = () => () => undefined;

export function PreviewHeaderSlotProvider({ children }: { children: ReactNode }) {
  const store = useMemo(() => createSlotStore(), []);
  return (
    <SlotContext.Provider value={store}>
      <HostContext.Provider value={true}>{children}</HostContext.Provider>
    </SlotContext.Provider>
  );
}

/** 当前是否在文件面板头部宿主内（决定预览组件用插槽还是自带头部） */
export function usePreviewHeaderHosted() {
  return useContext(HostContext);
}

/** 渲染所有已注册动作的容器，放在 diff-view-head 内、接受/扩缩按钮之前 */
export function PreviewHeaderSlot() {
  const store = useContext(SlotContext);
  useSyncExternalStore(store?.subscribe ?? noopSubscribe, store?.getSnapshot ?? (() => 0));
  if (!store) return null;
  const nodes = store.getNodes();
  if (nodes.length === 0) return null;
  return <>{nodes}</>;
}

/** 注册方：children 会渲染到外层头部；deps 变化时重新注册（保持最新状态） */
export function PreviewHeaderActions({ children }: { children: ReactNode }) {
  const store = useContext(SlotContext);
  const id = useId();
  useEffect(() => {
    store?.set(id, children);
    return () => store?.remove(id);
  }, [store, id, children]);
  return null;
}
