import { lazy, Suspense, useCallback, useEffect, useRef, useState, type ComponentType } from 'react';
import type { DeployTarget, FileNode, FileSnapshot, GitSnapshot, IdeClient, IdeJob } from './contracts';
import './ide.css';

const MonacoPane = lazy(() => import('../monaco-pane').then(mod => ({ default: mod.MonacoPane })));
const TerminalApp = lazy(() => import('../terminal').then(mod => ({ default: mod.TerminalApp })));
type EditorProps = { path: string; language: string; content: string; theme: 'dark' | 'light';
  onEditor: () => void; onSave: () => void; onChange: (value: string) => void };
type TerminalProps = { client: IdeClient['terminal']; theme: 'dark' | 'light' };
type Tab = FileSnapshot & { saved: string; dirty: boolean; conflict?: string };
type Activity = 'files' | 'search' | 'git';
type Dock = 'bottom' | 'right';
const layoutPrefix = 'aetherdesk.ide.layout.v1:';
const recoveryPrefix = 'aetherdesk.ide.recovery.v1:';
const MAX_TABS = 12;
const MAX_FILE = 2 * 1024 * 1024;

function readLayout(layoutKey: string): { dock: Dock; splits: number; autosave: boolean } {
  try {
    const raw = JSON.parse(localStorage.getItem(layoutKey) || '{}');
    return { dock: raw.dock === 'right' ? 'right' : 'bottom', splits: raw.splits === 2 ? 2 : 1,
      autosave: raw.autosave === true };
  } catch { return { dock: 'bottom', splits: 1, autosave: false }; }
}

function Tree({ nodes, onOpen }: { nodes: FileNode[]; onOpen: (path: string) => void }) {
  return <ul className="ide-tree">{nodes.map(node => <li key={node.path}>{node.kind === 'directory' ?
    <details open><summary>{node.name}</summary><Tree nodes={node.children || []} onOpen={onOpen} /></details> :
    <button onClick={() => onOpen(node.path)} title={node.path}>{node.name}</button>}</li>)}</ul>;
}

export function IdeApp({ client, workspace, project, accountScope, permissions, theme = 'dark',
  EditorComponent = MonacoPane as ComponentType<EditorProps>,
  TerminalComponent = TerminalApp as ComponentType<TerminalProps>,
}: { client: IdeClient; workspace: string; project: string; accountScope: string;
  permissions: readonly string[]; theme?: 'dark' | 'light';
  EditorComponent?: ComponentType<EditorProps>; TerminalComponent?: ComponentType<TerminalProps> }) {
  const layoutKey = layoutPrefix + accountScope;
  const recoveryKey = (path: string) => recoveryPrefix + accountScope + ':' + workspace + ':' + path;
  const [layout, setLayout] = useState(() => readLayout(layoutKey));
  const [activity, setActivity] = useState<Activity>('files');
  const [tree, setTree] = useState<FileNode[]>([]);
  const [tabs, setTabs] = useState<Tab[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [git, setGit] = useState<GitSnapshot | null>(null);
  const [search, setSearch] = useState('');
  const [results, setResults] = useState<{ path: string; line: number; snippet: string }[]>([]);
  const [replace, setReplace] = useState('');
  const [commitMessage, setCommitMessage] = useState('');
  const [diff, setDiff] = useState<{ path: string; text: string } | null>(null);
  const [job, setJob] = useState<IdeJob | null>(null);
  const [deployTargets, setDeployTargets] = useState<DeployTarget[]>([]);
  const [deployKey, setDeployKey] = useState('');
  const [status, setStatus] = useState('Carregando workspace…');
  const [offline, setOffline] = useState(false);
  const [palette, setPalette] = useState(false);
  const [confirm, setConfirm] = useState<'deploy' | 'push' | 'close' | null>(null);
  const [closing, setClosing] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [diagnostics, setDiagnostics] = useState('LSP desabilitado pela política do workspace');
  const confirmRef = useRef<HTMLDivElement>(null);
  const current = tabs.find(tab => tab.path === active);
  const dirtyCount = tabs.filter(tab => tab.dirty).length;
  const canGitRead = permissions.includes('git.read');
  const canGitWrite = permissions.includes('git.write');
  const canGitRemote = permissions.includes('git.remote');
  const canDeploy = permissions.includes('workloads.deploy');
  const deployTarget = deployTargets.find(target => `${target.workloadId}:${target.template}` === deployKey);

  const refresh = useCallback(async () => {
    try {
      const nodes = await client.tree();
      setTree(nodes); setOffline(false); setStatus('Workspace atualizado');
      if (canDeploy) {
        try {
          const targets = await client.deployTargets();
          setDeployTargets(targets);
          setDeployKey(old => targets.some(target => `${target.workloadId}:${target.template}` === old)
            ? old : targets[0] ? `${targets[0].workloadId}:${targets[0].template}` : '');
        } catch { setDeployTargets([]); setStatus('Deploy indisponível; consulte Containers.'); }
      }
      if (canGitRead) {
        try { setGit(await client.gitStatus()); }
        catch { setGit(null); setStatus('Arquivos prontos; Git indisponível neste workspace.'); }
      }
    } catch { setOffline(true); setStatus('Offline. Reabra a conexão e atualize o workspace.'); }
  }, [client, canGitRead, canDeploy]);
  useEffect(() => { const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer); }, [refresh]);
  useEffect(() => { localStorage.setItem(layoutKey, JSON.stringify(layout)); }, [layout, layoutKey]);
  useEffect(() => {
    const before = (event: BeforeUnloadEvent) => { if (dirtyCount) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', before);
    return () => window.removeEventListener('beforeunload', before);
  }, [dirtyCount]);
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'p') {
        event.preventDefault(); setPalette(value => !value);
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
        event.preventDefault(); void save();
      }
      if (event.key === 'Escape') { setPalette(false); setConfirm(null); setDiff(null); }
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  });
  useEffect(() => {
    if (!confirm) return;
    const before = document.activeElement as HTMLElement | null;
    const dialog = confirmRef.current;
    dialog?.querySelector('button')?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key !== 'Tab' || !dialog) return;
      const controls = [...dialog.querySelectorAll('button')];
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', key);
    return () => { document.removeEventListener('keydown', key); before?.focus(); };
  }, [confirm]);
  useEffect(() => {
    if (!job || job.status !== 'pending') return;
    let active = true;
    const timer = window.setInterval(() => void client.job(job.id).then(next => {
      if (active) setJob(next);
    }).catch(() => { if (active) setStatus('Job indisponível. Consulte novamente.'); }), 1000);
    return () => { active = false; window.clearInterval(timer); };
  }, [client, job]);
  useEffect(() => {
    if (!layout.autosave || !current?.dirty || current.conflict || offline || busy) return;
    const timer = window.setTimeout(() => void save(), 1200);
    return () => window.clearTimeout(timer);
  });

  async function open(path: string) {
    if (tabs.some(tab => tab.path === path)) { setActive(path); return; }
    if (tabs.length >= MAX_TABS) { setStatus('Limite de 12 arquivos abertos. Feche uma aba.'); return; }
    try {
      const file = await client.read(path);
      if (file.content.length > MAX_FILE || file.readonly) {
        setStatus('Arquivo grande, binário ou codificação não suportada: somente leitura segura.');
        if (file.content.length > MAX_FILE) return;
      }
      const recovery = localStorage.getItem(recoveryKey(path));
      const tab: Tab = { ...file, saved: file.content, content: recovery || file.content,
        dirty: !!recovery && recovery !== file.content };
      setTabs(old => [...old, tab]); setActive(path);
      if (recovery) setStatus('Rascunho local recuperado após recarregar. Revise antes de salvar.');
    } catch { setStatus('Falha ao abrir arquivo. Verifique permissão e conexão.'); }
  }
  function change(value: string) {
    if (!current || current.readonly) return;
    setTabs(old => old.map(tab => tab.path === active ? { ...tab, content: value,
      dirty: value !== tab.saved } : tab));
    const key = recoveryKey(current.path);
    if (value === current.saved) localStorage.removeItem(key); else localStorage.setItem(key, value);
  }
  async function save() {
    if (!current || !current.dirty || current.readonly || busy || offline) return;
    setBusy(true);
    try {
      const next = await client.save(current.path, current.content, current.revision);
      setTabs(old => old.map(tab => tab.path === current.path ? { ...next, saved: next.content,
        dirty: false } : tab));
      localStorage.removeItem(recoveryKey(current.path));
      setStatus('Arquivo salvo: ' + current.path);
      void refresh();
    } catch (error) {
      if (error instanceof Error && /conflict|revision|conflito/i.test(error.message)) {
        setTabs(old => old.map(tab => tab.path === current.path ? { ...tab, conflict: error.message } : tab));
        setStatus('Conflito de revisão. Compare o arquivo antes de substituir.');
      } else setStatus('Falha ao salvar. O rascunho local foi mantido.');
    } finally { setBusy(false); }
  }
  function close(path: string) {
    const tab = tabs.find(entry => entry.path === path);
    if (tab?.dirty) { setClosing(path); setConfirm('close'); return; }
    setTabs(old => old.filter(entry => entry.path !== path));
    if (active === path) setActive(tabs.find(entry => entry.path !== path)?.path || null);
  }
  function discardClose() {
    if (!closing) return;
    localStorage.removeItem(recoveryKey(closing));
    setTabs(old => old.filter(entry => entry.path !== closing));
    if (active === closing) setActive(tabs.find(entry => entry.path !== closing)?.path || null);
    setClosing(null); setConfirm(null);
  }
  async function runJob(start: (key: string) => Promise<IdeJob>) {
    setBusy(true);
    try { setJob(await start(crypto.randomUUID())); setStatus('Job solicitado.'); }
    catch { setStatus('Pedido incerto. Consulte o estado antes de repetir a operação.'); }
    finally { setBusy(false); }
  }
  async function doSearch() {
    if (!search.trim()) return;
    try { setResults((await client.search(search.trim())).slice(0, 200)); setStatus('Busca concluída'); }
    catch { setStatus('Busca indisponível ou cancelada.'); }
  }
  async function openDiff(path: string) {
    try { setDiff({ path, text: await client.gitDiff(path) }); }
    catch { setStatus('Diff indisponível.'); }
  }
  async function compareServer() {
    if (!current) return;
    try {
      const remote = await client.read(current.path);
      setDiff({ path: current.path, text: `VERSÃO NO SERVIDOR\n${remote.content}\n\nRASCUNHO LOCAL\n${current.content}` });
    } catch { setStatus('Versão do servidor indisponível. Rascunho local preservado.'); }
  }
  async function commit() {
    if (!commitMessage.trim() || dirtyCount) { setStatus('Salve arquivos alterados e informe a mensagem.'); return; }
    await runJob(key => client.gitCommit(commitMessage.trim(), key));
    void refresh();
  }
  const canOperate = !offline && !busy;
  return <section className={`ide-app ide-${layout.dock}`} aria-label="IDE">
    <header className="ide-header"><strong>IDE · {workspace}</strong><span>{project}</span>
      <button onClick={() => setPalette(true)} title="Ctrl+P">Comandos</button>
      <button onClick={() => void refresh()}>Atualizar</button></header>
    <div className="ide-workspace"><nav className="ide-activity" aria-label="Atividades">
      {(['files', 'search', ...(canGitRead ? ['git'] : [])] as Activity[]).map(item => <button key={item}
        aria-current={activity === item ? 'page' : undefined} onClick={() => setActivity(item)}>
        {item === 'files' ? 'Arquivos' : item === 'search' ? 'Busca' : 'Git'}</button>)}
      <button onClick={() => setLayout(old => ({ ...old, dock: old.dock === 'bottom' ? 'right' : 'bottom' }))}>
        Terminal {layout.dock === 'bottom' ? 'à direita' : 'embaixo'}</button></nav>
      <aside className="ide-sidebar" aria-label="Painel lateral">
        {activity === 'files' && <><h3>Explorer</h3><Tree nodes={tree} onOpen={path => void open(path)} /></>}
        {activity === 'search' && <><h3>Busca</h3><label>Buscar <input value={search}
          onChange={event => setSearch(event.target.value)} /></label><button onClick={() => void doSearch()}>Buscar</button>
          <label>Substituir na aba <input value={replace} onChange={event => setReplace(event.target.value)} /></label>
          <button disabled={!current || !!current.readonly || !search || !replace}
            onClick={() => { if (current) change(current.content.replaceAll(search, replace)); }}>Substituir na aba</button>
          <ul>{results.map((result, index) => <li key={result.path + index}><button onClick={() => void open(result.path)}>
            {result.path}:{result.line} · {result.snippet}</button></li>)}</ul></>}
        {activity === 'git' && <><h3>Controle de código</h3><p>{git?.branch || 'Sem branch'} · ↑{git?.ahead || 0} ↓{git?.behind || 0}</p>
          <ul>{git?.entries.map(entry => <li key={entry.path}><button onClick={() => void openDiff(entry.path)}>
            {entry.status} · {entry.path}</button>{canGitWrite && <button disabled={!canOperate} onClick={() => void client.gitStage([entry.path])
              .then(refresh).catch(() => setStatus('Falha ao preparar arquivo.'))}>Preparar</button>}</li>)}</ul>
          <label>Mensagem <input value={commitMessage} onChange={event => setCommitMessage(event.target.value)} /></label>
          {canGitWrite && <button disabled={!canOperate || dirtyCount > 0} onClick={() => void commit()}>Commit</button>}
          {canGitRemote && <button disabled={!canOperate || dirtyCount > 0} onClick={() => setConfirm('push')}>Publicar Git</button>}</>}
      </aside>
      <div className="ide-center"><div className="ide-tabs" aria-label="Arquivos abertos">
        {tabs.map(tab => <div key={tab.path}><button aria-current={active === tab.path ? 'page' : undefined}
          onClick={() => setActive(tab.path)}>{tab.path.split('/').at(-1)}{tab.dirty ? ' •' : ''}</button>
          <button aria-label={`Fechar ${tab.path}`} onClick={() => close(tab.path)}>×</button></div>)}</div>
        <div className="ide-editor"><p className="ide-breadcrumb">{active || 'Abra um arquivo pela árvore'}</p>
          {current && <><div className="ide-editor-tools"><button disabled={!current.dirty || !canOperate}
            onClick={() => void save()}>Salvar</button><label><input type="checkbox" checked={layout.autosave}
              onChange={event => setLayout(old => ({ ...old, autosave: event.target.checked }))} />Autosave</label></div>
            {current.conflict && <p role="alert">Conflito: {current.conflict}. O rascunho local foi preservado.
              <button onClick={() => void compareServer()}>Comparar com servidor</button></p>}
            <Suspense fallback={<p>Carregando editor…</p>}><EditorComponent path={current.path}
              language={current.language} content={current.content} theme={theme} onEditor={() => {}}
              onSave={() => void save()} onChange={change} /></Suspense></>}
          {!current && <p>Escolha um arquivo sem digitar caminho absoluto.</p>}</div>
      </div>
      <section className="ide-dock" aria-label="Terminal"><header><strong>Terminal</strong>
        <button onClick={() => setLayout(old => ({ ...old, splits: old.splits === 1 ? 2 : 1 }))}>
          {layout.splits === 1 ? 'Dividir terminal' : 'Unir terminal'}</button></header>
        <div className="ide-terminal-splits">{Array.from({ length: layout.splits }, (_, index) =>
          <Suspense key={index} fallback={<p>Carregando terminal…</p>}><TerminalComponent client={client.terminal}
            theme={theme} /></Suspense>)}</div></section></div>
    <footer className="ide-status" role="status"><span>{offline ? 'Offline' : 'Conectado'}</span>
      <span>{dirtyCount} arquivo(s) não salvo(s)</span><span>{diagnostics}</span>
      <button onClick={() => setDiagnostics('LSP/formatter indisponível nesta configuração')}>Diagnósticos</button>
      {canDeploy && <label>Destino <select value={deployKey} onChange={event => setDeployKey(event.target.value)}>
        {deployTargets.length === 0 && <option value="">Crie uma aplicação em Containers</option>}
        {deployTargets.map(target => <option key={`${target.workloadId}:${target.template}`}
          value={`${target.workloadId}:${target.template}`}>{target.project} / {target.name} · {target.template}</option>)}
      </select></label>}
      {canDeploy && <button disabled={!canOperate || dirtyCount > 0 || !deployTarget}
        onClick={() => setConfirm('deploy')}>Deploy</button>}
      <span>{status}</span>{job && <span>Job: {job.status} {job.message || ''}</span>}
      {job?.status === 'pending' && <button onClick={() => void client.cancelJob(job.id).then(setJob)
        .catch(() => setStatus('Cancelamento incerto. Consulte o job.'))}>Cancelar job</button>}</footer>
    {diff && <div className="ide-overlay"><div role="dialog" aria-modal="true" aria-label={`Diff ${diff.path}`}>
      <button onClick={() => setDiff(null)}>Fechar diff</button><h3>{diff.path}</h3><pre>{diff.text}</pre></div></div>}
    {palette && <div className="ide-overlay"><div role="dialog" aria-modal="true" aria-label="Paleta de comandos">
      <button onClick={() => setPalette(false)}>Fechar</button><h3>Comandos</h3>
      <button onClick={() => { setActivity('files'); setPalette(false); }}>Explorar arquivos</button>
      <button onClick={() => { setActivity('search'); setPalette(false); }}>Buscar no workspace</button>
      <button onClick={() => { setActivity('git'); setPalette(false); }}>Controle de código</button>
      <button onClick={() => { void save(); setPalette(false); }}>Salvar arquivo</button></div></div>}
    {confirm && <div className="ide-overlay"><div className="ide-confirm" ref={confirmRef} role="alertdialog"
      aria-modal="true" aria-labelledby="ide-confirm-title" aria-describedby="ide-confirm-detail">
      <h3 id="ide-confirm-title">{confirm === 'deploy' ? `Publicar ${deployTarget?.name || project}` : confirm === 'push' ? `Enviar branch ${git?.branch || ''}` : `Fechar ${closing}`}</h3>
      <p id="ide-confirm-detail">{confirm === 'deploy' ? 'O deploy reinicia o workload e acompanha saúde e rollback.' :
        confirm === 'push' ? 'Os commits locais serão enviados ao remoto configurado.' :
          'Alterações não salvas serão descartadas. O rascunho recuperável será removido.'}</p>
      <button onClick={() => setConfirm(null)}>Cancelar</button><button onClick={() => {
        const action = confirm; setConfirm(null);
        if (action === 'close') discardClose();
        else if (action === 'deploy' && deployTarget) void runJob(key => client.deploy(deployTarget, key));
        else void runJob(key => client.gitPush(key));
      }}>Confirmar</button></div></div>}
  </section>;
}
