import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { MonitorApp } from './apps/monitor';
import { AdministrationApp, SettingsApp } from './apps/administration';
import { ApiError, request, desktopClient, filesClient, terminalClient, monitorClient, administrationClient } from './clients';
import { emptyDesktop, fitWindow, focusWindow, normalizeDesktop, patchWindow, recoverDesktopDraft, type DesktopState, type WindowKind, type WindowState } from './window-state';
import { AppBoundary } from './app-boundary';
import { appByKind, visibleApps } from './shell/app-registry';
import { ShellMenu } from './shell/shell-menu';
import { arrangePinned, defaultPreferences, movePinned, placePinned, readPreferences, rememberApp, writePreferences } from './shell/personalization';
import { loadWallpaper, removeWallpaper, saveWallpaper } from './shell/wallpaper-store';
import { ideClient } from './apps/ide/client';
import { containersClient } from './apps/containers/client';
import { aiClient } from './apps/ai/client';

const FilesApp = lazy(() => import('./apps/files').then(module => ({ default: module.FilesApp })));
const TerminalApp = lazy(() => import('./apps/terminal').then(module => ({ default: module.TerminalApp })));
const IdeApp = lazy(() => import('./apps/ide/IdeApp').then(module => ({ default: module.IdeApp })));
const ContainersApp = lazy(() => import('./apps/containers/ContainersApp').then(module => ({ default: module.ContainersApp })));
const AiApp = lazy(() => import('./apps/ai/AiApp').then(module => ({ default: module.AiApp })));

type Session = { username: string; role: 'admin' | 'member'; account_id: string; permissions: string[]; permissions_version: number };
const fixture = import.meta.env.DEV && new URLSearchParams(location.search).get('fixture') === '1';
const viewport = () => ({ width: window.innerWidth, height: Math.max(1, window.innerHeight - 116) });
const tabIdKey = 'aetherdesk-desktop-tab-id';
const fallbackTabId = crypto.randomUUID();
let resolvedTabId: string | null = null;
let navigationChecked = false;
function tabId() {
  try {
    let id = sessionStorage.getItem(tabIdKey);
    if (!navigationChecked) {
      navigationChecked = true;
      const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined;
      // Uma aba duplicada pode herdar sessionStorage. Só o reload mantém a identidade da aba.
      if (navigation && navigation.type !== 'reload') id = null;
    }
    if (!id) {
      id = crypto.randomUUID();
      sessionStorage.setItem(tabIdKey, id);
    }
    resolvedTabId = id;
    return resolvedTabId;
  } catch { return fallbackTabId; }
}
const draftKey = (accountId: string) => `aetherdesk-desktop-draft:${accountId}:${tabId()}`;
type OtherDraft = { key: string; raw: string; updatedAt: number };
function otherDraft(accountId: string): OtherDraft | null {
  try {
    const prefix = `aetherdesk-desktop-draft:${accountId}:`;
    const own = draftKey(accountId);
    const ignored = sessionStorage.getItem(`aetherdesk-desktop-ignored:${accountId}`);
    let latest: OtherDraft | null = null;
    const legacyKey = `aetherdesk-desktop-draft:${accountId}`;
    const legacyRaw = localStorage.getItem(legacyKey);
    if (legacyRaw && ignored !== legacyKey &&
        localStorage.getItem(`${legacyKey}:consumed`) !== '0') {
      latest = { key: legacyKey, raw: legacyRaw, updatedAt: 0 };
    }
    for (let index = 0; index < localStorage.length; index++) {
      const key = localStorage.key(index);
      if (!key || !key.startsWith(prefix) || key === own || key === ignored ||
          !/^[0-9a-f-]{36}$/.test(key.slice(prefix.length))) continue;
      const raw = localStorage.getItem(key);
      if (!raw) continue;
      let draft: { updatedAt?: unknown; revision?: unknown; state?: { schemaVersion?: unknown } };
      try { draft = JSON.parse(raw); } catch { continue; }
      if (!draft || !Number.isSafeInteger(draft.revision) || draft.state?.schemaVersion !== 2) continue;
      const updatedAt = typeof draft.updatedAt === 'number' ? draft.updatedAt : 0;
      const consumed = Number(localStorage.getItem(`${key}:consumed`) || 0);
      if (updatedAt <= consumed) continue;
      if (!latest || updatedAt > latest.updatedAt) latest = { key, raw, updatedAt };
    }
    return latest;
  } catch { return null; }
}
function ignoreOtherDraft(accountId: string, key: string) {
  try { sessionStorage.setItem(`aetherdesk-desktop-ignored:${accountId}`, key); }
  catch { /* armazenamento indisponível */ }
}

function useDesktop(accountId: string) {
  const [state, setState] = useState<DesktopState>(emptyDesktop);
  const [sync, setSync] = useState<'loading' | 'saved' | 'saving' | 'offline' | 'error' | 'conflict'>('loading');
  const [retry, setRetry] = useState(0);
  const [saveRetry, setSaveRetry] = useState(0);
  const [interacting, setInteracting] = useState(false);
  const [pendingDraft, setPendingDraft] = useState<OtherDraft | null>(null);
  const revision = useRef(0);
  const lastSaved = useRef('');
  const latest = useRef(state);
  const queue = useRef<Promise<void>>(Promise.resolve());
  const blocked = useRef(false);
  const recoveredSource = useRef<OtherDraft | null>(null);
  useEffect(() => { latest.current = state; }, [state]);
  useEffect(() => {
    let cancelled = false;
    const load = fixture ? Promise.resolve({ data: JSON.parse(localStorage.getItem('aetherdesk-fixture') || 'null') as DesktopState | null, revision: 0 })
      : desktopClient.load();
    load.then(value => { if (!cancelled) {
      revision.current = value.revision || 0;
      const normalized = normalizeDesktop(value.data, viewport());
      lastSaved.current = value.data?.schemaVersion === 2 ? JSON.stringify(normalized) : '';
      let rawDraft: string | null = null;
      if (!fixture) { try { rawDraft = localStorage.getItem(draftKey(accountId)); } catch { /* armazenamento indisponível */ } }
      setPendingDraft(!fixture && !rawDraft ? otherDraft(accountId) : null);
      const recovered = recoverDesktopDraft(rawDraft, normalized, revision.current, viewport());
      blocked.current = recovered.conflict;
      setState(recovered.state); setSync(recovered.conflict ? 'conflict' : 'saved');
    } }).catch(() => { if (!cancelled) { blocked.current = true; setSync(navigator.onLine ? 'error' : 'offline'); } });
    return () => { cancelled = true; };
  }, [accountId, retry]);
  const loading = sync === 'loading';
  useEffect(() => {
    if (loading || blocked.current || JSON.stringify(state) === lastSaved.current) return;
    if (fixture) {
      localStorage.setItem('aetherdesk-fixture', JSON.stringify(state));
      lastSaved.current = JSON.stringify(state);
      return;
    }
    try { localStorage.setItem(draftKey(accountId), JSON.stringify({ revision: revision.current, state, updatedAt: Date.now() })); }
    catch { /* o desktop continua funcional sem recuperação local */ }
    if (interacting) return;
    const timer = setTimeout(() => {
      const snapshot = state;
      queue.current = queue.current.then(async () => {
        if (blocked.current || snapshot !== latest.current || JSON.stringify(snapshot) === lastSaved.current) return;
        setSync('saving');
        try {
          const result = await desktopClient.save(snapshot, revision.current);
          revision.current = result.revision ?? revision.current + 1;
          lastSaved.current = JSON.stringify(snapshot);
          if (snapshot === latest.current) {
            try { localStorage.removeItem(draftKey(accountId)); } catch { /* armazenamento indisponível */ }
            if (recoveredSource.current) {
              try { localStorage.setItem(`${recoveredSource.current.key}:consumed`,
                String(recoveredSource.current.updatedAt)); } catch { /* armazenamento indisponível */ }
              recoveredSource.current = null;
            }
            setSync('saved');
          } else {
            try { localStorage.setItem(draftKey(accountId), JSON.stringify({ revision: revision.current, state: latest.current, updatedAt: Date.now() })); }
            catch { /* armazenamento indisponível */ }
          }
        } catch (error) {
          if (error instanceof ApiError && error.status === 412) { blocked.current = true; setSync('conflict'); }
          else setSync(navigator.onLine ? 'error' : 'offline');
        }
      });
    }, 350);
    return () => clearTimeout(timer);
  }, [state, accountId, loading, saveRetry, interacting]);
  useEffect(() => {
    const online = () => setSaveRetry(value => value + 1);
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (sync !== 'loading' && (sync !== 'saved' || JSON.stringify(state) !== lastSaved.current)) {
        event.preventDefault(); event.returnValue = '';
      }
    };
    window.addEventListener('online', online);
    window.addEventListener('beforeunload', beforeUnload);
    return () => { window.removeEventListener('online', online); window.removeEventListener('beforeunload', beforeUnload); };
  }, [sync, state]);
  useEffect(() => {
    const reflow = () => setState(current => {
      const next = normalizeDesktop(current, viewport());
      return JSON.stringify(next) === JSON.stringify(current) ? current : next;
    });
    window.addEventListener('resize', reflow);
    return () => window.removeEventListener('resize', reflow);
  }, []);
  return { state, setState, setInteracting, sync, pendingDraft,
    recoverOther: () => {
      if (!pendingDraft) return;
      ignoreOtherDraft(accountId, pendingDraft.key);
      const recovered = recoverDesktopDraft(pendingDraft.raw, state, revision.current, viewport());
      try { localStorage.setItem(draftKey(accountId), pendingDraft.raw); } catch { /* armazenamento indisponível */ }
      recoveredSource.current = pendingDraft;
      blocked.current = recovered.conflict;
      setPendingDraft(null);
      setState(recovered.state);
      setSync(recovered.conflict ? 'conflict' : 'saved');
      setSaveRetry(value => value + 1);
    },
    ignoreOther: () => {
      if (pendingDraft) ignoreOtherDraft(accountId, pendingDraft.key);
      setPendingDraft(null);
    },
    hasPending: () => JSON.stringify(latest.current) !== lastSaved.current,
    reload: () => { recoveredSource.current = null; setSync('loading'); setRetry(value => value + 1); },
    retrySave: () => {
      if (blocked.current) { setSync('loading'); setRetry(value => value + 1); }
      else setSaveRetry(value => value + 1);
    } };
}

export function App() {
  const [session, setSession] = useState<Session | null>(fixture ? { username: 'Douglas', role: 'admin', account_id: 'fixture', permissions: ['files.read', 'files.write', 'terminal.open', 'terminal.control', 'metrics.self', 'metrics.server', 'preferences.read', 'preferences.write', 'accounts.view'], permissions_version: 1 } : null);
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>(fixture ? 'ready' : 'loading');
  const [loginError, setLoginError] = useState('');
  const accountId = session?.account_id;
  useEffect(() => {
    if (fixture) return;
    request<Session>('/me').then(value => { setSession(value); setPhase('ready'); })
      .catch(() => setPhase('ready'));
  }, []);
  useEffect(() => {
    if (fixture || !accountId) return;
    const refresh = () => {
      if (document.visibilityState !== 'visible') return;
      void request<Session>('/me').then(value => setSession(current => current && current.account_id === value.account_id && current.permissions_version === value.permissions_version ? current : value))
        .catch(error => { if (error instanceof ApiError && error.status === 401) setSession(null); });
    };
    const timer = window.setInterval(refresh, 5_000);
    document.addEventListener('visibilitychange', refresh);
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', refresh); };
  }, [accountId]);
  async function login(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setLoginError('');
    const form = new FormData(event.currentTarget);
    try {
      await request<Session>('/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: form.get('username'), password: form.get('password') }) });
      setSession(await request<Session>('/me'));
    } catch { setLoginError('Não foi possível entrar. Verifique suas credenciais.'); }
  }
  if (phase === 'loading') return <div className="center-state">Preparando seu espaço…</div>;
  if (phase === 'error') return <div className="center-state">Não foi possível conectar ao AetherDesk.</div>;
  if (!session) return <main className="login-page"><form className="login-card" onSubmit={login}>
    <div className="brand-mark">✦</div><div className="eyebrow">SEU ESPAÇO, SUA RAIZ</div><h1>Bem-vindo ao AetherDesk.</h1>
    <p>Entre para continuar de onde você parou.</p><label>Usuário<input name="username" autoComplete="username" required /></label>
    <label>Senha<input name="password" type="password" autoComplete="current-password" required /></label>
    {loginError && <div role="alert" className="error-note">{loginError}</div>}
    <button className="primary" type="submit">Entrar <span>→</span></button>
  </form></main>;

  return <DesktopWorkspace key={session.account_id} session={session} onLogout={() => setSession(null)} />;
}

function DesktopWorkspace({ session, onLogout }: { session: Session; onLogout: () => void }) {
  const [now, setNow] = useState(() => new Date());
  const available = visibleApps(session.permissions);
  const [preferences, setPreferences] = useState(() => readPreferences(session.account_id));
  const [overlay, setOverlay] = useState<'start' | 'palette' | null>(null);
  const [contextMenu, setContextMenu] = useState<{ kind: WindowKind; x: number; y: number } | null>(null);
  const [wallpaperUrl, setWallpaperUrl] = useState<string | null>(null);
  const [wallpaperError, setWallpaperError] = useState('');
  const [wallpaperBusy, setWallpaperBusy] = useState(false);
  const wallpaperUrlRef = useRef<string | null>(null);
  const contextRef = useRef<HTMLDivElement>(null);
  const longPress = useRef<number | null>(null);
  const pinnedApps = preferences.pinned.flatMap(kind => available.filter(app => app.kind === kind));
  const { state, setState, setInteracting, sync, pendingDraft, recoverOther, ignoreOther,
    hasPending, reload, retrySave } = useDesktop(session.account_id);
  useEffect(() => { const timer = window.setInterval(() => setNow(new Date()), 15_000); return () => window.clearInterval(timer); }, []);
  useEffect(() => { writePreferences(session.account_id, preferences); }, [session.account_id, preferences]);
  useEffect(() => {
    let cancelled = false;
    void loadWallpaper(session.account_id).then(record => {
      if (cancelled || !record) return;
      const url = URL.createObjectURL(record.image);
      if (wallpaperUrlRef.current) URL.revokeObjectURL(wallpaperUrlRef.current);
      wallpaperUrlRef.current = url;
      setWallpaperUrl(url);
    }).catch(() => undefined);
    return () => { cancelled = true; if (wallpaperUrlRef.current) URL.revokeObjectURL(wallpaperUrlRef.current); wallpaperUrlRef.current = null; };
  }, [session.account_id]);
  useEffect(() => {
    const keyboard = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault(); setContextMenu(null); setOverlay('palette');
      } else if (event.key === 'Escape') setContextMenu(null);
    };
    window.addEventListener('keydown', keyboard);
    return () => window.removeEventListener('keydown', keyboard);
  }, []);
  useEffect(() => () => { if (longPress.current !== null) window.clearTimeout(longPress.current); }, []);
  useEffect(() => {
    if (!contextMenu) return;
    const prior = document.activeElement as HTMLElement | null;
    contextRef.current?.querySelector('button')?.focus();
    const outside = (event: PointerEvent) => { if (!contextRef.current?.contains(event.target as Node)) setContextMenu(null); };
    window.addEventListener('pointerdown', outside);
    return () => { window.removeEventListener('pointerdown', outside); prior?.focus(); };
  }, [contextMenu]);

  async function logout() {
    if (!fixture) {
      if ((sync !== 'saved' || hasPending()) && !window.confirm('Há alterações do desktop não salvas. Sair mesmo assim?')) return;
      try { localStorage.removeItem(draftKey(session.account_id)); } catch { /* armazenamento indisponível */ }
      await request('/logout', { method: 'POST' }).catch(() => undefined);
    }
    onLogout();
  }

  function open(kind: WindowKind) {
    if (!available.some(app => app.kind === kind)) return;
    setPreferences(current => rememberApp(current, kind));
    setState(current => {
      const existing = current.windows.find(window => window.kind === kind);
      if (existing) return focusWindow(patchWindow(current, existing.id, { minimized: false }, viewport()), existing.id);
      const id = crypto.randomUUID(); const n = current.windows.length;
      const window = fitWindow({ id, kind, x: 90 + n * 28, y: 80 + n * 24,
        width: 720, height: 470, z: n + 1, minimized: false, maximized: false }, viewport());
      return focusWindow({ ...current, windows: [...current.windows, window] }, id);
    });
  }
  function update(id: string, patch: Partial<WindowState>) {
    setState(current => {
      const next = patchWindow(current, id, patch, viewport());
      return patch.minimized ? { ...next, activeId: null } : next;
    });
  }
  function close(id: string) { setState(current => ({ ...current, activeId: null, windows: current.windows.filter(window => window.id !== id) })); }
  function togglePin(kind: WindowKind) {
    setPreferences(current => ({ ...current, pinned: current.pinned.includes(kind)
      ? current.pinned.filter(item => item !== kind) : [...current.pinned, kind] }));
  }
  async function uploadWallpaper(file: File) {
    setWallpaperBusy(true); setWallpaperError('');
    try {
      const record = await saveWallpaper(session.account_id, file);
      const url = URL.createObjectURL(record.image);
      if (wallpaperUrlRef.current) URL.revokeObjectURL(wallpaperUrlRef.current);
      wallpaperUrlRef.current = url; setWallpaperUrl(url);
      setPreferences(current => ({ ...current, background: 'upload' }));
    } catch (error) {
      const code = error instanceof Error ? error.message : '';
      setWallpaperError(code === 'WALLPAPER_TOO_LARGE' ? 'Imagem excede o limite de 8 MiB de origem ou 2 MiB após processamento.'
        : code === 'WALLPAPER_INVALID_DIMENSIONS' ? 'Imagem excede 4096 px por lado ou 16 milhões de pixels.'
          : code.startsWith('WALLPAPER_STORAGE_UNAVAILABLE') ? 'Armazenamento local indisponível para esta imagem.'
          : 'Use uma imagem PNG, JPEG ou WebP válida.');
    } finally { setWallpaperBusy(false); }
  }
  async function changeBackground(background: 'default' | 'solid' | 'gradient' | 'gallery') {
    setWallpaperBusy(true); setWallpaperError('');
    try {
      if (preferences.background === 'upload' || wallpaperUrlRef.current) await removeWallpaper(session.account_id);
      if (wallpaperUrlRef.current) URL.revokeObjectURL(wallpaperUrlRef.current);
      wallpaperUrlRef.current = null; setWallpaperUrl(null);
      setPreferences(current => ({ ...current, background }));
    } catch { setWallpaperError('Não foi possível remover a imagem armazenada. Tente novamente.'); }
    finally { setWallpaperBusy(false); }
  }
  async function resetPersonalization() {
    setWallpaperBusy(true); setWallpaperError('');
    try {
      if (preferences.background === 'upload' || wallpaperUrlRef.current) await removeWallpaper(session.account_id);
      if (wallpaperUrlRef.current) URL.revokeObjectURL(wallpaperUrlRef.current);
      wallpaperUrlRef.current = null; setWallpaperUrl(null);
      setPreferences(defaultPreferences());
    } catch { setWallpaperError('Não foi possível remover a imagem armazenada. Tente novamente.'); }
    finally { setWallpaperBusy(false); }
  }
  return <div className={`desktop ${state.theme} background-${preferences.background}`}>
    <header className="topbar"><div className="topbrand"><span className="spark">✦</span> AetherDesk <span className="topbar-divider" /> <span className="workspace-label">Meu espaço</span></div>
      <div className="top-actions"><span className={`sync ${sync}`} role="status">● {sync === 'saved' ? 'Salvo' : sync === 'saving' ? 'Salvando' : sync === 'offline' ? 'Desconectado' : sync === 'loading' ? 'Carregando' : sync === 'conflict' ? 'Conflito entre abas' : 'Falha ao salvar'}</span>{pendingDraft && <><button className="text-button" onClick={recoverOther}>Recuperar rascunho</button><button className="text-button" onClick={ignoreOther}>Ignorar rascunho</button></>}{sync === 'conflict' && <button className="text-button" onClick={() => { if (window.confirm('Descartar alterações locais e carregar o estado mais recente?')) { try { localStorage.removeItem(draftKey(session.account_id)); } catch { /* armazenamento indisponível */ } reload(); } }}>Recarregar estado</button>}{(sync === 'error' || sync === 'offline') && <button className="text-button" onClick={retrySave}>Tentar salvar</button>}<span className="avatar">{session.username.slice(0, 1).toUpperCase()}</span><button className="text-button" onClick={logout}>Sair</button></div></header>
    <div className="desktop-background" style={preferences.background === 'upload' && wallpaperUrl ? { backgroundImage: `url("${wallpaperUrl}")` } : undefined}><div className="hero"><div className="hero-emblem">✦</div><div className="hero-word">AetherDesk</div><p>Seu ambiente está pronto para você.</p></div>
      <div className="launchers">{pinnedApps.map(app => <button className="launcher" key={app.kind} draggable onClick={() => open(app.kind)}
        title={app.description} onContextMenu={event => { event.preventDefault(); setContextMenu({ kind: app.kind, x: event.clientX, y: event.clientY }); }}
        onDragStart={event => event.dataTransfer.setData('text/x-aetherdesk-app', app.kind)}
        onDragOver={event => { if (event.dataTransfer.types.includes('text/x-aetherdesk-app')) event.preventDefault(); }}
        onDrop={event => { event.preventDefault(); const source = event.dataTransfer.getData('text/x-aetherdesk-app') as WindowKind;
          setPreferences(current => placePinned(current, source, app.kind)); }}
        onKeyDown={event => { if (event.key === 'F10' && event.shiftKey) { event.preventDefault(); const rect = event.currentTarget.getBoundingClientRect(); setContextMenu({ kind: app.kind, x: rect.left, y: rect.bottom }); } }}
        onPointerDown={event => { if (event.pointerType === 'touch') { const rect = event.currentTarget.getBoundingClientRect(); longPress.current = window.setTimeout(() => setContextMenu({ kind: app.kind, x: rect.left, y: rect.bottom }), 550); } }}
        onPointerUp={() => { if (longPress.current !== null) window.clearTimeout(longPress.current); }}
        onPointerCancel={() => { if (longPress.current !== null) window.clearTimeout(longPress.current); }}>
        <span className="launcher-icon">{app.icon}</span><span>{app.title}</span></button>)}</div>
      {state.windows.filter(window => !window.minimized && available.some(app => app.kind === window.kind)).map(window => <DeskWindow key={window.id} value={window} active={state.activeId === window.id} session={session} canAdmin={session.permissions.includes('accounts.view')} canServerMetrics={session.permissions.includes('metrics.server')} theme={state.theme} onTheme={theme => setState(current => ({ ...current, theme }))} onFocus={() => setState(current => focusWindow(current, window.id))} onChange={patch => update(window.id, patch)} onInteractionChange={setInteracting} onClose={() => close(window.id)} />)}
    </div>
    {contextMenu && <div ref={contextRef} className="launcher-context" role="menu" style={{ left: Math.max(0, Math.min(contextMenu.x, innerWidth - 170)), top: Math.max(0, Math.min(contextMenu.y, innerHeight - 155)) }}
      onKeyDown={event => { if (event.key === 'Escape') { setContextMenu(null); event.preventDefault(); }
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); const buttons = [...event.currentTarget.querySelectorAll('button')];
          const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
          buttons[(index + (event.key === 'ArrowDown' ? 1 : buttons.length - 1)) % buttons.length].focus(); } }}>
      <button role="menuitem" onClick={() => { open(contextMenu.kind); setContextMenu(null); }}>Abrir {appByKind(contextMenu.kind).title}</button>
      <button role="menuitem" onClick={() => { togglePin(contextMenu.kind); setContextMenu(null); }}>Remover atalho</button>
      <button role="menuitem" onClick={() => { setPreferences(current => movePinned(current, contextMenu.kind, -1)); setContextMenu(null); }}>Mover antes</button>
      <button role="menuitem" onClick={() => { setPreferences(current => movePinned(current, contextMenu.kind, 1)); setContextMenu(null); }}>Mover depois</button>
    </div>}
    {overlay && <ShellMenu mode={overlay} apps={available} preferences={preferences} onOpen={open} onPin={togglePin}
      onBackground={background => { void changeBackground(background); }} onUpload={uploadWallpaper}
      uploadError={wallpaperError} uploading={wallpaperBusy}
      onArrange={() => setPreferences(current => arrangePinned(current))}
      onReset={() => { void resetPersonalization(); }}
      onClose={() => setOverlay(null)} />}
    <footer className="taskbar"><button className="task-home" aria-label="Início" aria-expanded={overlay === 'start'} onClick={() => { setContextMenu(null); setOverlay(current => current === 'start' ? null : 'start'); }}>✦</button><div className="task-separator" />{state.windows.filter(window => available.some(app => app.kind === window.kind)).map(window => { const app = appByKind(window.kind); return <button key={window.id} className={`task-app ${state.activeId === window.id && !window.minimized ? 'active' : ''}`} onClick={() => setState(current => { const target = current.windows.find(item => item.id === window.id); return target?.minimized ? focusWindow(patchWindow(current, window.id, { minimized: false }, viewport()), window.id) : { ...patchWindow(current, window.id, { minimized: true }, viewport()), activeId: null }; })}><span>{app.icon}</span>{app.title}</button>; })}<div className="task-spacer" /><span className="task-clock">{now.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}</span></footer>
  </div>;
}

function DeskWindow({ value, active, session, canAdmin, canServerMetrics, theme, onTheme, onFocus, onChange, onInteractionChange, onClose }: { value: WindowState; active: boolean; session: Session; canAdmin: boolean; canServerMetrics: boolean; theme: 'dark' | 'light'; onTheme: (theme: 'dark' | 'light') => void; onFocus: () => void; onChange: (patch: Partial<WindowState>) => void; onInteractionChange: (active: boolean) => void; onClose: () => void }) {
  const app = appByKind(value.kind);
  const drag = useRef<{ x: number; y: number; left: number; top: number } | null>(null);
  const frame = useRef<number | null>(null);
  const pending = useRef<Partial<WindowState> | null>(null);
  const resizeCleanup = useRef<(() => void) | null>(null);
  useEffect(() => () => {
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    resizeCleanup.current?.();
  }, []);
  function schedule(patch: Partial<WindowState>) {
    pending.current = patch;
    if (frame.current !== null) return;
    frame.current = requestAnimationFrame(() => {
      frame.current = null;
      if (pending.current) onChange(pending.current);
      pending.current = null;
    });
  }
  function flush() {
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    frame.current = null;
    if (pending.current) onChange(pending.current);
    pending.current = null;
  }
  function onPointerMove(event: React.PointerEvent) {
    if (!drag.current) return;
    schedule({ x: Math.max(0, drag.current.left + event.clientX - drag.current.x), y: Math.max(0, drag.current.top + event.clientY - drag.current.y) });
  }
  const style = value.maximized ? { left: 0, top: 0, width: '100%', height: '100%', zIndex: value.z } : { left: value.x, top: value.y, width: value.width, height: value.height, zIndex: value.z };
  return <section className={`desk-window ${active ? 'window-active' : ''}`} style={style} onPointerDown={onFocus}>
    <div className="window-titlebar" onPointerDown={event => { if (value.maximized) return; onInteractionChange(true); drag.current = { x: event.clientX, y: event.clientY, left: value.x, top: value.y }; event.currentTarget.setPointerCapture(event.pointerId); }} onPointerMove={onPointerMove} onPointerUp={() => { if (drag.current) { flush(); drag.current = null; onInteractionChange(false); } }} onPointerCancel={() => { if (drag.current) { flush(); drag.current = null; onInteractionChange(false); } }}>
      <span className="window-app-icon">{app.icon}</span><strong>{app.title}</strong><div className="window-controls"><button aria-label="Minimizar" onPointerDown={event => event.stopPropagation()} onClick={() => onChange({ minimized: true })}>—</button><button aria-label={value.maximized ? 'Restaurar' : 'Maximizar'} onPointerDown={event => event.stopPropagation()} onClick={() => onChange({ maximized: !value.maximized })}>□</button><button aria-label="Fechar" onPointerDown={event => event.stopPropagation()} onClick={onClose}>×</button></div>
    </div><div className="window-body"><AppBoundary appName={app.title}>
      {(value.kind === 'explorer' || value.kind === 'editor') && <Suspense fallback={<div className="center-state">Abrindo arquivos…</div>}><FilesApp mode={value.kind} client={filesClient} theme={theme} /></Suspense>}
      {value.kind === 'terminal' && <Suspense fallback={<div className="center-state">Abrindo terminal…</div>}><TerminalApp client={terminalClient} theme={theme} /></Suspense>}
      {value.kind === 'monitor' && <MonitorApp client={monitorClient} admin={canServerMetrics} />}
      {value.kind === 'admin' && canAdmin && <AdministrationApp client={administrationClient} />}
      {value.kind === 'settings' && <SettingsApp theme={theme} onTheme={onTheme} />}
      {value.kind === 'ide' && <Suspense fallback={<div className="center-state">Abrindo IDE…</div>}><IdeApp client={ideClient} workspace="Meu workspace" project="default" accountScope={session.account_id} permissions={session.permissions} theme={theme} /></Suspense>}
      {value.kind === 'containers' && <Suspense fallback={<div className="center-state">Abrindo Containers…</div>}><ContainersApp client={containersClient} permissions={session.permissions} /></Suspense>}
      {value.kind === 'ai' && <Suspense fallback={<div className="center-state">Abrindo IA…</div>}><AiApp client={aiClient} permissions={session.permissions} /></Suspense>}
    </AppBoundary></div>
    {!value.maximized && <div className="resize-corner" onPointerDown={event => { event.preventDefault(); event.stopPropagation(); onFocus(); onInteractionChange(true); const start = { x: event.clientX, y: event.clientY, width: value.width, height: value.height }; const move = (e: PointerEvent) => schedule({ width: Math.max(200, start.width + e.clientX - start.x), height: Math.max(160, start.height + e.clientY - start.y) }); const end = () => { flush(); window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', end); window.removeEventListener('pointercancel', end); resizeCleanup.current = null; onInteractionChange(false); }; resizeCleanup.current = end; window.addEventListener('pointermove', move); window.addEventListener('pointerup', end); window.addEventListener('pointercancel', end); }} />}
  </section>;
}
