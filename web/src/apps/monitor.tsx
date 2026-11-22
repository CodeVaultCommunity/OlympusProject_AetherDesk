import { useEffect, useState } from 'react';
import './monitor.css';

type Sample = { category: string; reference: string; sampled_at: string; status: string; values: Record<string, number | string | null> };
export interface MonitorClient {
  self(): Promise<{ current: Sample; recent: Sample[] }>;
  server(): Promise<{ server: Sample; shared: Sample }>;
  accounts(): Promise<{ account_id: string; username: string; sample: Sample }[]>;
}
const bytes = (value: number | string | null | undefined) => typeof value === 'number' ? `${(value / 1024 / 1024).toFixed(1)} MiB` : 'Indisponível';
const percent = (value: number | string | null | undefined) => typeof value === 'number' ? `${value.toFixed(1)}%` : 'Indisponível';
function Card({ title, sample }: { title: string; sample: Sample }) {
  const v = sample.values;
  return <section className="metric-card"><h3>{title}</h3><span className="metric-state">{sample.status === 'available' ? 'Disponível' : sample.status === 'partial' ? 'Parcial' : 'Indisponível'}</span>
    <dl><dt>CPU</dt><dd>{percent(v.cpu_percent)}</dd><dt>Memória</dt><dd>{bytes(v.memory_bytes)} / {bytes(v.memory_limit_bytes)}</dd><dt>Disco</dt><dd>{bytes(v.storage_bytes)} / {bytes(v.storage_limit_bytes)}</dd><dt>Leitura</dt><dd>{bytes(v.read_bytes)}</dd><dt>Escrita</dt><dd>{bytes(v.write_bytes)}</dd><dt>Rede recebida</dt><dd>{bytes(v.network_rx_bytes)}</dd><dt>Rede enviada</dt><dd>{bytes(v.network_tx_bytes)}</dd></dl>
    <small>Referência: {sample.reference} · {new Date(sample.sampled_at).toLocaleString('pt-BR')}</small></section>;
}
export function MonitorApp({ client, admin }: { client: MonitorClient; admin: boolean }) {
  const [view, setView] = useState<'self' | 'server' | 'accounts'>('self');
  const [mine, setMine] = useState<{ current: Sample; recent: Sample[] } | null>(null);
  const [host, setHost] = useState<{ server: Sample; shared: Sample } | null>(null);
  const [accounts, setAccounts] = useState<{ account_id: string; username: string; sample: Sample }[]>([]);
  const [status, setStatus] = useState('Carregando…');
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        if (view === 'self') { const data = await client.self(); if (active) setMine(data); }
        if (view === 'server') { const data = await client.server(); if (active) setHost(data); }
        if (view === 'accounts') { const data = await client.accounts(); if (active) setAccounts(data); }
        if (active) setStatus('Atualizado');
      } catch { if (active) setStatus('Métricas indisponíveis ou acesso negado'); }
    }
    void load(); const timer = setInterval(() => void load(), 5000);
    return () => { active = false; clearInterval(timer); };
  }, [client, view]);
  return <div className="monitor-app"><nav><button className={view === 'self' ? 'active' : ''} onClick={() => setView('self')}>Meu ambiente</button>{admin && <><button className={view === 'server' ? 'active' : ''} onClick={() => setView('server')}>Servidor</button><button className={view === 'accounts' ? 'active' : ''} onClick={() => setView('accounts')}>Usuários</button></>}<span>{status}</span></nav>
    <div className="metric-grid">{view === 'self' && mine && <><Card title="Meu ambiente" sample={mine.current} /><section className="metric-card"><h3>CPU recente</h3><div className="metric-bars">{mine.recent.map((entry, index) => <div key={index} style={{ height: `${Math.max(2, Number(entry.values.cpu_percent) || 0)}%` }} title={`${entry.values.cpu_percent ?? 'Indisponível'}%`} />)}</div></section></>}
      {view === 'server' && host && <><Card title="Servidor" sample={host.server} /><Card title="Serviços compartilhados" sample={host.shared} /></>}
      {view === 'accounts' && accounts.map(account => <Card key={account.account_id} title={account.username} sample={account.sample} />)}</div>
  </div>;
}
