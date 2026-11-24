import type { WindowKind } from '../window-state';
import { appRegistry } from './app-registry';

export type Background = 'default' | 'solid' | 'gradient' | 'gallery' | 'upload';
export type ShellPreferences = { pinned: WindowKind[]; background: Background; recent: WindowKind[] };
const allKinds = appRegistry.map(app => app.kind);
export const defaultPreferences = (): ShellPreferences => ({ pinned: [...allKinds], background: 'default', recent: [] });
const storageKey = (accountId: string) => `aetherdesk-shell:${accountId}`;

export function normalizePreferences(value: unknown): ShellPreferences {
  if (!value || typeof value !== 'object') return defaultPreferences();
  const raw = value as Partial<ShellPreferences>;
  const unique = (items: unknown) => Array.isArray(items)
    ? [...new Set(items.filter((item): item is WindowKind => allKinds.includes(item as WindowKind)))].slice(0, allKinds.length)
    : [];
  const background = raw.background === 'solid' || raw.background === 'gradient' || raw.background === 'gallery' || raw.background === 'upload'
    ? raw.background : 'default';
  return { pinned: Array.isArray(raw.pinned) ? unique(raw.pinned) : [...allKinds],
    background, recent: unique(raw.recent).slice(0, 4) };
}

export function readPreferences(accountId: string): ShellPreferences {
  try { return normalizePreferences(JSON.parse(localStorage.getItem(storageKey(accountId)) || 'null')); }
  catch { return defaultPreferences(); }
}

export function writePreferences(accountId: string, preferences: ShellPreferences): void {
  try { localStorage.setItem(storageKey(accountId), JSON.stringify(normalizePreferences(preferences))); }
  catch { /* armazenamento bloqueado: a sessão atual continua funcional */ }
}

export function rememberApp(preferences: ShellPreferences, kind: WindowKind): ShellPreferences {
  return { ...preferences, recent: [kind, ...preferences.recent.filter(item => item !== kind)].slice(0, 4) };
}

export function movePinned(preferences: ShellPreferences, kind: WindowKind, direction: -1 | 1): ShellPreferences {
  const from = preferences.pinned.indexOf(kind);
  const to = from + direction;
  if (from < 0 || to < 0 || to >= preferences.pinned.length) return preferences;
  const pinned = [...preferences.pinned];
  [pinned[from], pinned[to]] = [pinned[to], pinned[from]];
  return { ...preferences, pinned };
}

export function placePinned(preferences: ShellPreferences, source: WindowKind, before: WindowKind): ShellPreferences {
  if (source === before || !preferences.pinned.includes(source) || !preferences.pinned.includes(before)) return preferences;
  const pinned = preferences.pinned.filter(kind => kind !== source);
  pinned.splice(pinned.indexOf(before), 0, source);
  return { ...preferences, pinned };
}

export function arrangePinned(preferences: ShellPreferences): ShellPreferences {
  return { ...preferences, pinned: allKinds.filter(kind => preferences.pinned.includes(kind)) };
}
