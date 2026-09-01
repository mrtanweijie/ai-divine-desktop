export function storageGet<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw == null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export function storageSet(key: string, value: unknown): void {
  localStorage.setItem(key, JSON.stringify(value));
}

/** 无序列化版：读写裸字符串（theme/locale/effort/model 等纯字符串 key 专用，
 * 避免 JSON.parse 破坏存量裸字符串数据）。 */
export function storageGetRaw(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function storageSetRaw(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // localStorage 不可用时静默失败
  }
}

export function storageRemove(key: string): void {
  localStorage.removeItem(key);
}
