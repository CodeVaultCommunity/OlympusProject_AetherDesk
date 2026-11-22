import { useEffect, useRef, useState } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import './terminal.css';

export interface TerminalClient {
  list(): Promise<{ id: string; state: string }[]>;
  create(columns: number, rows: number): Promise<string>;
  close(id: string): Promise<void>;
  connect(id: string): WebSocket;
}

export function TerminalApp({ client }: { client: TerminalClient }) {
  const [sessions, setSessions] = useState<{ id: string; state: string }[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [status, setStatus] = useState('Carregando terminais…');
  const mount = useRef<HTMLDivElement>(null);
  const xterm = useRef<Terminal | null>(null);
  const socket = useRef<WebSocket | null>(null);
  const fit = useRef<FitAddon | null>(null);

  async function refresh() {
    try {
      const entries = (await client.list()).filter(entry => entry.state === 'open');
      setSessions(entries);
      setSelected(old => old && entries.some(entry => entry.id === old) ? old : entries[0]?.id || null);
      setStatus('Terminais atualizados');
    } catch { setStatus('Falha ao listar terminais'); }
  }
  useEffect(() => { void refresh(); }, [client]);

  async function create() {
    try {
      const id = await client.create(fit.current?.proposeDimensions()?.cols || 80,
        fit.current?.proposeDimensions()?.rows || 24);
      await refresh(); setSelected(id);
    } catch { setStatus('Falha ao criar terminal'); }
  }
  async function close() {
    if (!selected || !window.confirm('Encerrar este terminal e seus processos?')) return;
    try { await client.close(selected); await refresh(); }
    catch { setStatus('Falha ao encerrar terminal'); }
  }

  useEffect(() => {
    if (!selected || !mount.current) return;
    const term = new Terminal({ cursorBlink: true, convertEol: true, fontFamily: 'Cascadia Code, Consolas, monospace', fontSize: 13 });
    const addon = new FitAddon(); term.loadAddon(addon); term.open(mount.current); addon.fit(); term.focus();
    xterm.current = term; fit.current = addon;
    const ws = client.connect(selected); socket.current = ws;
    const input = term.onData(data => { if (ws.readyState === WebSocket.OPEN) ws.send(new TextEncoder().encode(data)); });
    ws.binaryType = 'arraybuffer';
    ws.onopen = () => { setStatus('Conectado'); ws.send(JSON.stringify({ type: 'resize', columns: term.cols, rows: term.rows })); };
    ws.onmessage = event => {
      if (event.data instanceof ArrayBuffer) term.write(new Uint8Array(event.data));
      else term.write(event.data);
    };
    ws.onclose = () => setStatus('Desconectado. Se o processo continuou, selecione o terminal para reconectar.');
    const observer = new ResizeObserver(() => {
      addon.fit();
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'resize', columns: term.cols, rows: term.rows }));
    });
    observer.observe(mount.current);
    return () => { observer.disconnect(); input.dispose(); ws.close(); term.dispose(); xterm.current = null; socket.current = null; fit.current = null; };
  }, [client, selected]);

  return <div className="terminal-app">
    <div className="terminal-toolbar"><button onClick={() => void create()}>Novo Bash</button><button onClick={() => void refresh()}>Atualizar</button><button onClick={() => void close()} disabled={!selected}>Encerrar</button><span>{status}</span></div>
    <div className="terminal-tabs">{sessions.map(entry => <button key={entry.id} className={selected === entry.id ? 'selected' : ''} onClick={() => setSelected(entry.id)}>Bash {entry.id.slice(0, 8)}</button>)}</div>
    {selected ? <div className="terminal-mount" ref={mount} /> : <div className="terminal-empty">Crie um terminal para iniciar o Bash.</div>}
  </div>;
}
