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

export function storageRemove(key: string): void {
  localStorage.removeItem(key);
}
