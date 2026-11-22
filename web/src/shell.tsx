import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { MonitorApp } from './apps/monitor';
import { AdministrationApp, SettingsApp } from './apps/administration';
import { filesClient, terminalClient, monitorClient, administrationClient } from './clients';

const FilesApp = lazy(() => import('./apps/files').then(module => ({ default: module.FilesApp })));
const TerminalApp = lazy(() => import('./apps/terminal').then(module => ({ default: module.TerminalApp })));

type WindowKind = 'explorer' | 'editor' | 'terminal' | 'monitor' | 'admin' | 'settings';
type WindowState = { id: string; kind: WindowKind; x: number; y: number; width: number; height: number; z: number; minimized: boolean; maximized: boolean };
type DesktopState = { windows: WindowState[]; activeId: string | null; theme: 'dark' | 'light' };
type Session = { username: string; role: 'admin' | 'member' };
const apps: { kind: WindowKind; title: string; icon: string; description: string }[] = [
  { kind: 'explorer', title: 'Explorador', icon: '▦', description: 'Arquivos e pastas' },
  { kind: 'editor', title: 'Editor', icon: '⌘', description: 'Código e texto' },
  { kind: 'terminal', title: 'Terminal', icon: '⌁', description: 'Bash interativo' },
  { kind: 'monitor', title: 'Monitor', icon: '◫', description: 'Recursos do sistema' },
  { kind: 'admin', title: 'Administração', icon: '⚙', description: 'Contas e ambientes' },
  { kind: 'settings', title: 'Configurações', icon: '◈', description: 'Preferências pessoais' },
];
const empty: DesktopState = { windows: [], activeId: null, theme: 'dark' };
const fixture = import.meta.env.DEV && new URLSearchParams(location.search).get('fixture') === '1';

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const csrf = document.cookie.split('; ').find(part => part.startsWith('aether_csrf='))?.split('=')[1];
  const response = await fetch(`/api/v1${path}`, { credentials: 'include', ...init,
    headers: { 'Content-Type': 'application/json', ...(csrf ? { 'X-CSRF-Token': csrf } : {}), ...init?.headers } });
  if (!response.ok) throw new Error(response.status === 401 ? 'Sessão expirada' : `Falha ${response.status}`);
  return (await response.json()).data as T;
}

function useDesktop(session: Session | null) {
  const [state, setState] = useState<DesktopState>(empty);
  const [sync, setSync] = useState<'loading' | 'saved' | 'saving' | 'offline' | 'error'>('loading');
  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    const load = fixture ? Promise.resolve(JSON.parse(localStorage.getItem('aetherdesk-fixture') || 'null') as DesktopState | null)
      : api<DesktopState>('/desktop/state');
    load.then(value => { if (!cancelled) { setState(value || empty); setSync('saved'); } })
      .catch(() => { if (!cancelled) setSync(navigator.onLine ? 'error' : 'offline'); });
    return () => { cancelled = true; };
  }, [session]);
  useEffect(() => {
    if (!session || sync === 'loading') return;
    if (fixture) {
      localStorage.setItem('aetherdesk-fixture', JSON.stringify(state));
      setSync('saved');
      return;
    }
    setSync('saving');
    const timer = setTimeout(() => {
      const save = api('/desktop/state', { method: 'PUT', body: JSON.stringify(state) });
      save.then(() => setSync('saved')).catch(() => setSync(navigator.onLine ? 'error' : 'offline'));
    }, 350);
    return () => clearTimeout(timer);
  }, [state, session]);
  return { state, setState, sync };
}

export function App() {
  const [session, setSession] = useState<Session | null>(fixture ? { username: 'Douglas', role: 'admin' } : null);
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>(fixture ? 'ready' : 'loading');
  const [loginError, setLoginError] = useState('');
  const { state, setState, sync } = useDesktop(session);
  useEffect(() => {
    if (fixture) return;
    api<Session>('/me').then(value => { setSession(value); setPhase('ready'); })
      .catch(() => setPhase('ready'));
  }, []);
  async function login(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setLoginError('');
    const form = new FormData(event.currentTarget);
    try {
      const value = await api<Session>('/login', { method: 'POST', body: JSON.stringify({ username: form.get('username'), password: form.get('password') }) });
      setSession(value);
    } catch { setLoginError('Não foi possível entrar. Verifique suas credenciais.'); }
  }
  async function logout() {
    if (!fixture) {
      await api('/desktop/state', { method: 'PUT', body: JSON.stringify(state) }).catch(() => undefined);
      await api('/logout', { method: 'POST' }).catch(() => undefined);
    }
    setSession(null);
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

  const highest = Math.max(1, ...state.windows.map(window => window.z));
  function open(kind: WindowKind) {
    const existing = state.windows.find(window => window.kind === kind && !window.minimized);
    if (existing) { setState(current => ({ ...current, activeId: existing.id, windows: current.windows.map(window => window.id === existing.id ? { ...window, z: highest + 1 } : window) })); return; }
    const id = crypto.randomUUID(); const n = state.windows.length;
    setState(current => ({ ...current, activeId: id, windows: [...current.windows, { id, kind, x: 90 + n * 28, y: 80 + n * 24, width: 720, height: 470, z: highest + 1, minimized: false, maximized: false }] }));
  }
  function update(id: string, patch: Partial<WindowState>) {
    setState(current => ({ ...current, activeId: id, windows: current.windows.map(window => window.id === id ? { ...window, ...patch, z: highest + 1 } : window) }));
  }
  function close(id: string) { setState(current => ({ ...current, activeId: null, windows: current.windows.filter(window => window.id !== id) })); }
  return <div className={`desktop ${state.theme}`}>
    <header className="topbar"><div className="topbrand"><span className="spark">✦</span> AetherDesk <span className="topbar-divider" /> <span className="workspace-label">Meu espaço</span></div>
      <div className="top-actions"><span className={`sync ${sync}`}>● {sync === 'saved' ? 'Salvo' : sync === 'saving' ? 'Salvando' : sync === 'offline' ? 'Desconectado' : sync === 'loading' ? 'Carregando' : 'Falha ao salvar'}</span><span className="avatar">{session.username.slice(0, 1).toUpperCase()}</span><button className="text-button" onClick={logout}>Sair</button></div></header>
    <div className="desktop-background"><div className="hero"><div className="hero-emblem">✦</div><div className="hero-word">AetherDesk</div><p>Seu ambiente está pronto para você.</p></div>
      <div className="launchers">{apps.filter(app => app.kind !== 'admin' || session.role === 'admin').map(app => <button className="launcher" key={app.kind} onDoubleClick={() => open(app.kind)} onClick={() => open(app.kind)}><span className="launcher-icon">{app.icon}</span><span>{app.title}</span></button>)}</div>
      {state.windows.filter(window => !window.minimized).map(window => <DeskWindow key={window.id} value={window} active={state.activeId === window.id} admin={session.role === 'admin'} theme={state.theme} onTheme={theme => setState(current => ({ ...current, theme }))} onFocus={() => update(window.id, {})} onChange={patch => update(window.id, patch)} onClose={() => close(window.id)} />)}
    </div>
    <footer className="taskbar"><button className="task-home" aria-label="Início" onClick={() => open('explorer')}>✦</button><div className="task-separator" />{state.windows.map(window => { const app = apps.find(item => item.kind === window.kind)!; return <button key={window.id} className={`task-app ${state.activeId === window.id && !window.minimized ? 'active' : ''}`} onClick={() => update(window.id, { minimized: !window.minimized })}><span>{app.icon}</span>{app.title}</button>; })}<div className="task-spacer" /><span className="task-clock">{new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}</span></footer>
  </div>;
}

function DeskWindow({ value, active, admin, theme, onTheme, onFocus, onChange, onClose }: { value: WindowState; active: boolean; admin: boolean; theme: 'dark' | 'light'; onTheme: (theme: 'dark' | 'light') => void; onFocus: () => void; onChange: (patch: Partial<WindowState>) => void; onClose: () => void }) {
  const app = apps.find(item => item.kind === value.kind)!;
  const drag = useRef<{ x: number; y: number; left: number; top: number } | null>(null);
  function onPointerMove(event: React.PointerEvent) {
    if (!drag.current) return;
    onChange({ x: Math.max(0, drag.current.left + event.clientX - drag.current.x), y: Math.max(0, drag.current.top + event.clientY - drag.current.y) });
  }
  const style = value.maximized ? { left: 0, top: 0, width: '100%', height: '100%', zIndex: value.z } : { left: value.x, top: value.y, width: value.width, height: value.height, zIndex: value.z };
  return <section className={`desk-window ${active ? 'window-active' : ''}`} style={style} onPointerDown={onFocus}>
    <div className="window-titlebar" onPointerDown={event => { if (value.maximized) return; drag.current = { x: event.clientX, y: event.clientY, left: value.x, top: value.y }; event.currentTarget.setPointerCapture(event.pointerId); }} onPointerMove={onPointerMove} onPointerUp={() => { drag.current = null; }}>
      <span className="window-app-icon">{app.icon}</span><strong>{app.title}</strong><div className="window-controls"><button aria-label="Minimizar" onPointerDown={event => event.stopPropagation()} onClick={() => onChange({ minimized: true })}>—</button><button aria-label={value.maximized ? 'Restaurar' : 'Maximizar'} onPointerDown={event => event.stopPropagation()} onClick={() => onChange({ maximized: !value.maximized })}>□</button><button aria-label="Fechar" onPointerDown={event => event.stopPropagation()} onClick={onClose}>×</button></div>
    </div><div className="window-body">
      {(value.kind === 'explorer' || value.kind === 'editor') && <Suspense fallback={<div className="center-state">Abrindo arquivos…</div>}><FilesApp mode={value.kind} client={filesClient} /></Suspense>}
      {value.kind === 'terminal' && <Suspense fallback={<div className="center-state">Abrindo terminal…</div>}><TerminalApp client={terminalClient} /></Suspense>}
      {value.kind === 'monitor' && <MonitorApp client={monitorClient} admin={admin} />}
      {value.kind === 'admin' && admin && <AdministrationApp client={administrationClient} />}
      {value.kind === 'settings' && <SettingsApp theme={theme} onTheme={onTheme} />}
    </div>
    {!value.maximized && <div className="resize-corner" onPointerDown={event => { event.preventDefault(); event.stopPropagation(); const start = { x: event.clientX, y: event.clientY, width: value.width, height: value.height }; const move = (e: PointerEvent) => onChange({ width: Math.max(400, start.width + e.clientX - start.x), height: Math.max(260, start.height + e.clientY - start.y) }); const end = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', end); }; window.addEventListener('pointermove', move); window.addEventListener('pointerup', end); }} />}
  </section>;
}
