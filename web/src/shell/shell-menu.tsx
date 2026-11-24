import { useEffect, useRef, useState } from 'react';
import type { WindowKind } from '../window-state';
import type { AppDescriptor } from './app-registry';
import type { ShellPreferences } from './personalization';

type Props = {
  mode: 'start' | 'palette';
  apps: readonly AppDescriptor[];
  preferences: ShellPreferences;
  onOpen: (kind: WindowKind) => void;
  onPin: (kind: WindowKind) => void;
  onBackground: (background: Exclude<ShellPreferences['background'], 'upload'>) => void;
  onUpload: (file: File) => void;
  uploadError: string;
  uploading: boolean;
  onArrange: () => void;
  onReset: () => void;
  onClose: () => void;
};

export function ShellMenu({ mode, apps, preferences, onOpen, onPin, onBackground, onUpload,
  uploadError, uploading, onArrange, onReset, onClose }: Props) {
  const panel = useRef<HTMLDivElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState('');
  const [confirmReset, setConfirmReset] = useState(false);
  const cancelReset = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const prior = document.activeElement as HTMLElement | null;
    search.current?.focus();
    return () => prior?.focus();
  }, []);
  useEffect(() => { if (confirmReset) cancelReset.current?.focus(); }, [confirmReset]);
  const filtered = apps.filter(app => `${app.title} ${app.description}`.toLocaleLowerCase('pt-BR')
    .includes(query.trim().toLocaleLowerCase('pt-BR')));
  function keyDown(event: React.KeyboardEvent) {
    if (confirmReset) return;
    if (event.key === 'Escape') { event.preventDefault(); onClose(); return; }
    if (event.key !== 'Tab') return;
    const focusable = [...(panel.current?.querySelectorAll<HTMLElement>('button:not([disabled]),input') || [])];
    if (!focusable.length) return;
    const first = focusable[0], last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }
  return <div className="shell-overlay" onPointerDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div ref={panel} className={`shell-menu ${mode}`} role="dialog" aria-modal="true"
      aria-label={mode === 'start' ? 'Menu Início' : 'Paleta de comandos'} onKeyDown={keyDown}>
      <div className="shell-menu-heading"><strong>{mode === 'start' ? 'Início' : 'Comandos'}</strong>
        <button type="button" aria-label="Fechar menu" onClick={onClose}>×</button></div>
      <input ref={search} aria-label="Buscar aplicativos" placeholder="Buscar aplicativos…" value={query}
        onChange={event => setQuery(event.target.value)}
        onKeyDown={event => { if (event.key === 'Enter' && filtered[0]) { onOpen(filtered[0].kind); onClose(); } }} />
      {mode === 'start' && !query && preferences.recent.some(kind => apps.some(app => app.kind === kind)) &&
        <div className="shell-menu-section"><small>Recentes</small><div className="shell-recent">
          {preferences.recent.filter(kind => apps.some(app => app.kind === kind)).map(kind => {
            const app = apps.find(item => item.kind === kind)!;
            return <button key={kind} onClick={() => { onOpen(kind); onClose(); }}>{app.icon}<span>{app.title}</span></button>;
          })}</div></div>}
      <div className="shell-menu-section"><small>Aplicativos</small><div className="shell-app-list">
        {filtered.map(app => <div className="shell-app-row" key={app.kind}>
          <button className="shell-app-open" onClick={() => { onOpen(app.kind); onClose(); }}
            title={app.description}>{app.icon}<span><strong>{app.title}</strong><small>{app.description}</small></span></button>
          <button className="shell-pin" aria-label={`${preferences.pinned.includes(app.kind) ? 'Remover' : 'Fixar'} ${app.title} na área de trabalho`}
            title={preferences.pinned.includes(app.kind) ? 'Remover atalho' : 'Fixar atalho'}
            onClick={() => onPin(app.kind)}>{preferences.pinned.includes(app.kind) ? '●' : '○'}</button>
        </div>)}
        {!filtered.length && <p>Nenhum aplicativo encontrado.</p>}
      </div></div>
      {mode === 'start' && <div className="shell-menu-section"><small>Plano de fundo</small>
        <div className="shell-background-options">{(['default', 'solid', 'gradient', 'gallery'] as const).map(background =>
          <button key={background} aria-pressed={preferences.background === background}
            disabled={uploading} onClick={() => onBackground(background)}>{({ default: 'Padrão', solid: 'Sólido', gradient: 'Gradiente', gallery: 'Galeria' })[background]}</button>)}</div>
        <label className="shell-upload">Enviar imagem PNG, JPEG ou WebP (até 8 MiB)
          <input type="file" accept="image/png,image/jpeg,image/webp" disabled={uploading}
            onChange={event => { const file = event.currentTarget.files?.[0]; if (file) onUpload(file); event.currentTarget.value = ''; }} />
        </label>
        {uploading && <p role="status">Processando imagem…</p>}
        {uploadError && <p className="shell-upload-error" role="alert">{uploadError}</p>}
      </div>}
      {mode === 'start' && <button className="shell-reset" disabled={uploading} onClick={onArrange}>Ordenar atalhos</button>}
      {mode === 'start' && <button className="shell-reset" disabled={uploading} onClick={() => setConfirmReset(true)}>Restaurar atalhos e aparência</button>}
    </div>
    {confirmReset && <div className="shell-confirm" role="alertdialog" aria-modal="true" aria-label="Restaurar personalização"
      onKeyDown={event => { if (event.key === 'Escape') { event.preventDefault(); setConfirmReset(false); }
        if (event.key === 'Tab') { event.preventDefault(); const buttons = event.currentTarget.querySelectorAll<HTMLButtonElement>('button');
          (document.activeElement === buttons[0] && !event.shiftKey ? buttons[1] : buttons[0]).focus(); } }}>
      <strong>Restaurar personalização?</strong><p>Os atalhos, a ordem, os recentes e o plano de fundo voltarão ao padrão desta conta. Suas janelas e arquivos permanecem.</p>
      <div><button ref={cancelReset} onClick={() => setConfirmReset(false)}>Cancelar</button>
        <button onClick={() => { onReset(); setConfirmReset(false); }}>Restaurar</button></div>
    </div>}
  </div>;
}
