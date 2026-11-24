export type WindowKind = 'explorer' | 'editor' | 'terminal' | 'monitor' | 'admin' | 'settings' | 'ide' | 'containers' | 'ai';
export type WindowState = { id: string; kind: WindowKind; x: number; y: number; width: number; height: number; z: number; minimized: boolean; maximized: boolean };
export type DesktopState = { schemaVersion: 2; windows: WindowState[]; activeId: string | null; theme: 'dark' | 'light' };
export type Viewport = { width: number; height: number };

export const emptyDesktop: DesktopState = { schemaVersion: 2, windows: [], activeId: null, theme: 'dark' };
const kinds: WindowKind[] = ['explorer', 'editor', 'terminal', 'monitor', 'admin', 'settings', 'ide', 'containers', 'ai'];
const finite = (value: unknown, fallback: number) => typeof value === 'number' && Number.isFinite(value) ? value : fallback;
const between = (value: number, low: number, high: number) => Math.min(Math.max(value, low), high);

export function fitWindow(window: WindowState, viewport: Viewport): WindowState {
  const availableWidth = Math.max(1, viewport.width);
  const availableHeight = Math.max(1, viewport.height);
  const width = between(window.width, Math.min(200, availableWidth), availableWidth);
  const height = between(window.height, Math.min(160, availableHeight), availableHeight);
  return { ...window, width, height,
    x: between(window.x, 0, Math.max(0, viewport.width - width)),
    y: between(window.y, 0, Math.max(0, viewport.height - height)) };
}

export function normalizeDesktop(value: unknown, viewport: Viewport): DesktopState {
  if (!value || typeof value !== 'object') return emptyDesktop;
  const raw = value as Partial<DesktopState>;
  const ids = new Set<string>();
  const windows = (Array.isArray(raw.windows) ? raw.windows : []).slice(0, 40).flatMap((candidate, index) => {
    if (!candidate || !kinds.includes(candidate.kind)) return [];
    const id = typeof candidate.id === 'string' && candidate.id && !ids.has(candidate.id) ? candidate.id : crypto.randomUUID();
    ids.add(id);
    return [fitWindow({ id, kind: candidate.kind, x: finite(candidate.x, 0), y: finite(candidate.y, 0),
      width: finite(candidate.width, 720), height: finite(candidate.height, 470),
      z: between(finite(candidate.z, index + 1), 1, 10_000),
      minimized: candidate.minimized === true, maximized: candidate.maximized === true }, viewport)];
  });
  const ordered = [...windows].sort((a, b) => a.z - b.z);
  const compact = new Map(ordered.map((window, index) => [window.id, index + 1]));
  return { schemaVersion: 2, windows: windows.map(window => ({ ...window, z: compact.get(window.id)! })),
    activeId: typeof raw.activeId === 'string' && ids.has(raw.activeId) ? raw.activeId : null,
    theme: raw.theme === 'light' ? 'light' : 'dark' };
}

export function recoverDesktopDraft(raw: string | null, server: DesktopState, revision: number,
                                    viewport: Viewport): { state: DesktopState; conflict: boolean; recovered: boolean } {
  if (!raw) return { state: server, conflict: false, recovered: false };
  try {
    const draft = JSON.parse(raw) as { revision?: unknown; state?: Partial<DesktopState> };
    if (!Number.isSafeInteger(draft.revision) || (draft.revision as number) < 0 ||
        draft.state?.schemaVersion !== 2 || !Array.isArray(draft.state.windows)) {
      return { state: server, conflict: false, recovered: false };
    }
    return { state: normalizeDesktop(draft.state, viewport),
      conflict: draft.revision !== revision, recovered: true };
  } catch { return { state: server, conflict: false, recovered: false }; }
}

export function focusWindow(state: DesktopState, id: string): DesktopState {
  const target = state.windows.find(window => window.id === id);
  if (!target) return state;
  if (state.activeId === id && target.z === Math.max(...state.windows.map(window => window.z))) return state;
  const windows = state.windows.map(window => window.id === id ? { ...window, z: state.windows.length + 1 } : window);
  const ordered = [...windows].sort((a, b) => a.z - b.z);
  const compact = new Map(ordered.map((window, index) => [window.id, index + 1]));
  return { ...state, activeId: id, windows: windows.map(window => ({ ...window, z: compact.get(window.id)! })) };
}

export function patchWindow(state: DesktopState, id: string, patch: Partial<WindowState>, viewport: Viewport): DesktopState {
  if (!state.windows.some(window => window.id === id)) return state;
  return { ...state, windows: state.windows.map(window => window.id === id ? fitWindow({ ...window, ...patch, id, kind: window.kind, z: window.z }, viewport) : window) };
}
