import { useEffect, useRef, useState } from 'react';
import Editor, { type OnMount } from '@monaco-editor/react';
import { monaco } from './monaco';
import './files.css';

export type FileEntry = { name: string; kind: 'file' | 'directory' | 'link'; size: number; mtime_ns: number };
export type FileRead = { content: string; revision: string };
export interface FileClient {
  list(path: string): Promise<FileEntry[]>;
  read(path: string): Promise<FileRead>;
  write(path: string, content: string, revision?: string): Promise<string>;
  mkdir(path: string): Promise<void>;
  move(source: string, destination: string): Promise<void>;
  copy(source: string, destination: string): Promise<void>;
  delete(path: string): Promise<void>;
  download(path: string): Promise<Blob>;
  upload(path: string, file: File, replace?: boolean): Promise<void>;
}
type Tab = { path: string; content: string; revision: string; dirty: boolean; conflict: boolean };
const join = (dir: string, name: string) => dir === '/' ? `/${name}` : `${dir}/${name}`;
const language = (path: string) => ({ ts: 'typescript', tsx: 'typescript', js: 'javascript', jsx: 'javascript', json: 'json', css: 'css', html: 'html', py: 'python', md: 'markdown', sh: 'shell' }[path.split('.').pop() || ''] || 'plaintext');

export function FilesApp({ mode, client }: { mode: 'explorer' | 'editor'; client: FileClient }) {
  const [directory, setDirectory] = useState('/');
  const [entries, setEntries] = useState<FileEntry[]>([]);
  const [tabs, setTabs] = useState<Tab[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [status, setStatus] = useState('Carregando arquivos…');
  const [openingPath, setOpeningPath] = useState('');
  const fileInput = useRef<HTMLInputElement>(null);
  const editorRef = useRef<Parameters<OnMount>[0] | null>(null);
  const saveRef = useRef<() => void>(() => {});
  const current = tabs.find(tab => tab.path === active);

  async function refresh() {
    try { setEntries(await client.list(directory)); setStatus('Atualizado agora'); }
    catch { setStatus('Não foi possível atualizar os arquivos'); }
  }
  useEffect(() => { void refresh(); const timer = setInterval(() => { void refresh(); }, 2500); return () => clearInterval(timer); }, [directory, client]);

  async function openFile(path: string) {
    if (tabs.some(tab => tab.path === path)) { setActive(path); return; }
    setStatus('Abrindo arquivo…');
    try {
      const file = await client.read(path);
      setTabs(old => [...old, { path, content: file.content, revision: file.revision, dirty: false, conflict: false }]);
      setActive(path); setStatus('Arquivo aberto');
    } catch { setStatus('Não foi possível abrir o arquivo'); }
  }
  async function save() {
    if (!current || !current.dirty) return;
    setStatus('Salvando…');
    try {
      const revision = await client.write(current.path, current.content, current.revision);
      setTabs(old => old.map(tab => tab.path === current.path ? { ...tab, revision, dirty: false, conflict: false } : tab));
      setStatus('Salvo'); void refresh();
    } catch (error) {
      const conflict = String(error).includes('STALE_REVISION');
      setTabs(old => old.map(tab => tab.path === current.path ? { ...tab, conflict } : tab));
      setStatus(conflict ? 'Conflito: o arquivo mudou fora do editor' : 'Falha ao salvar; resultado desconhecido');
    }
  }
  saveRef.current = () => { void save(); };
  function closeTab(path: string) {
    const tab = tabs.find(item => item.path === path);
    if (tab?.dirty && !window.confirm('Descartar alterações não salvas?')) return;
    setTabs(old => old.filter(item => item.path !== path));
    if (active === path) setActive(tabs.find(item => item.path !== path)?.path || null);
  }
  const onMount: OnMount = (editor) => {
    editorRef.current = editor;
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => saveRef.current());
  };
  async function operation(kind: 'mkdir' | 'new' | 'move' | 'copy' | 'delete', entry?: FileEntry) {
    try {
      if (kind === 'mkdir') {
        const name = window.prompt('Nome da nova pasta'); if (!name) return;
        await client.mkdir(join(directory, name));
      } else if (kind === 'new') {
        const name = window.prompt('Nome do novo arquivo'); if (!name) return;
        await client.write(join(directory, name), '');
      } else if (entry) {
        const source = join(directory, entry.name);
        if (kind === 'delete') { if (!window.confirm(`Excluir ${entry.name} permanentemente?`)) return; await client.delete(source); }
        else { const target = window.prompt('Novo caminho absoluto', source); if (!target || target === source) return; await client[kind](source, target); }
      }
      setStatus('Operação concluída'); void refresh();
    } catch { setStatus('Operação falhou; verifique conflito ou permissão'); }
  }
  async function download(entry: FileEntry) {
    try { const blob = await client.download(join(directory, entry.name)); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = entry.name; link.click(); URL.revokeObjectURL(url); }
    catch { setStatus('Falha no download'); }
  }
  return <div className="files-app">
    <div className="files-toolbar"><span className="path-label">{directory}</span><button onClick={() => setDirectory(directory === '/' ? '/' : directory.slice(0, directory.lastIndexOf('/')) || '/')}>↑</button><button onClick={() => void refresh()}>Atualizar</button><button onClick={() => void operation('mkdir')}>Nova pasta</button><button onClick={() => void operation('new')}>Novo arquivo</button><button onClick={() => fileInput.current?.click()}>Enviar</button><input ref={fileInput} type="file" hidden onChange={async event => { const file = event.target.files?.[0]; if (file) { const path = join(directory, file.name); try { await client.upload(path, file); void refresh(); } catch (error) { if (String(error).includes('CONFLICT') && window.confirm(`${file.name} já existe. Substituir explicitamente?`)) { await client.upload(path, file, true).then(refresh).catch(() => setStatus('Falha no envio')); } else setStatus('Falha no envio'); } event.target.value = ''; } }} /></div>
    <div className="files-content">
      {mode === 'explorer' && <aside className="files-list">{entries.map(entry => <div className="file-row" key={entry.name}><button className="file-name" onClick={() => entry.kind === 'directory' ? setDirectory(join(directory, entry.name)) : void openFile(join(directory, entry.name))}><span>{entry.kind === 'directory' ? '▦' : entry.kind === 'link' ? '↗' : '▤'}</span>{entry.name}</button><span className="file-size">{entry.kind === 'file' ? `${entry.size} B` : ''}</span><div className="file-actions"><button title="Mover ou renomear" onClick={() => void operation('move', entry)}>↗</button><button title="Copiar" onClick={() => void operation('copy', entry)}>⧉</button>{entry.kind === 'file' && <button title="Baixar" onClick={() => void download(entry)}>↓</button>}<button title="Excluir" onClick={() => void operation('delete', entry)}>×</button></div></div>)}</aside>}
      <div className="editor-area">{mode === 'editor' && <div className="open-path"><input value={openingPath} onChange={event => setOpeningPath(event.target.value)} placeholder="/persist/arquivo.py" onKeyDown={event => { if (event.key === 'Enter') void openFile(openingPath); }} /><button onClick={() => void openFile(openingPath)}>Abrir</button></div>}
        <div className="editor-tabs">{tabs.map(tab => <button className={tab.path === active ? 'selected' : ''} key={tab.path} onClick={() => setActive(tab.path)}>{tab.path.split('/').pop()}{tab.dirty ? ' •' : ''}<span onClick={event => { event.stopPropagation(); closeTab(tab.path); }}>×</span></button>)}</div>
        {current ? <><div className="editor-actions"><span>{current.path}</span><button onClick={() => editorRef.current?.getAction('actions.find')?.run()}>Buscar</button><button onClick={() => editorRef.current?.getAction('editor.action.startFindReplaceAction')?.run()}>Substituir</button><button onClick={() => void save()} disabled={!current.dirty}>Salvar · Ctrl+S</button></div>{current.conflict && <div className="file-conflict" role="alert">O arquivo mudou fora do editor. Copie suas alterações e reabra antes de salvar.</div>}<div className="monaco-host"><Editor path={current.path} language={language(current.path)} value={current.content} theme="vs-dark" onMount={onMount} onChange={value => setTabs(old => old.map(tab => tab.path === current.path ? { ...tab, content: value || '', dirty: true } : tab))} options={{ minimap: { enabled: false }, automaticLayout: true, fontSize: 13 }} /></div></> : <div className="editor-empty">Selecione um arquivo para editar.</div>}
      </div>
    </div><div className="files-status" role="status">{status}</div>
  </div>;
}
