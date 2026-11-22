import { useEffect, useState } from 'react';
import './administration.css';

export type Account = { id: string; username: string; role: string; state: string; revision: number; environment_id: string };
export type BackupPolicy = { enabled: boolean; frequency_hours: number; destination: string; retention_mode: 'replace' | 'days'; retention_days: number | null };
export interface AdministrationClient {
  accounts(): Promise<Account[]>;
  create(username: string, password: string, role: string): Promise<void>;
  update(account: Account, change: Record<string, unknown>): Promise<void>;
  permissions(id: string): Promise<string[]>;
  setPermission(id: string, capability: string, allowed: boolean): Promise<void>;
  sessions(id: string): Promise<{ id: string; created_at: string; revoked_at: string | null }[]>;
  revoke(sessionId: string): Promise<void>;
  stop(accountId: string): Promise<void>;
  environment(id: string): Promise<{ state: string }>;
  retry(id: string): Promise<void>;
  audit(): Promise<{ id: string; actor_id: string; operation: string; target_id: string; at: string }[]>;
  backup(): Promise<BackupPolicy>;
  configureBackup(policy: BackupPolicy): Promise<void>;
}

const availableCapabilities = ['files.read', 'files.write', 'terminal.open', 'terminal.control', 'metrics.self', 'metrics.server', 'metrics.accounts', 'accounts.view', 'accounts.manage', 'permissions.view', 'permissions.manage', 'audit.view', 'backup.view', 'backup.manage', 'backup.restore', 'environment.manage', 'sessions.revoke', 'sessions.stop'];
export function AdministrationApp({ client }: { client: AdministrationClient }) {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selected, setSelected] = useState<Account | null>(null);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [sessions, setSessions] = useState<{ id: string; created_at: string; revoked_at: string | null }[]>([]);
  const [environment, setEnvironment] = useState('…');
  const [backup, setBackup] = useState<BackupPolicy | null>(null);
  const [audit, setAudit] = useState<{ id: string; actor_id: string; operation: string; target_id: string; at: string }[]>([]);
  const [status, setStatus] = useState('Carregando…');
  async function refresh() {
    try { setAccounts(await client.accounts()); setBackup(await client.backup()); setAudit(await client.audit()); setStatus('Atualizado'); }
    catch { setStatus('Falha ao carregar administração'); }
  }
  useEffect(() => { void refresh(); }, [client]);
  useEffect(() => { if (!selected) return; let active = true; Promise.all([client.permissions(selected.id), client.sessions(selected.id), client.environment(selected.id)]).then(([p, s, e]) => { if (active) { setPermissions(p); setSessions(s); setEnvironment(e.state); } }).catch(() => setStatus('Falha ao carregar conta')); return () => { active = false; }; }, [selected, client]);
  async function create() {
    const username = window.prompt('Nome do usuário'); if (!username) return;
    const password = window.prompt('Senha inicial (mínimo 12 caracteres)'); if (!password) return;
    const role = window.confirm('Conceder papel de administrador?') ? 'admin' : 'member';
    try { await client.create(username, password, role); await refresh(); }
    catch { setStatus('Falha ao criar conta'); }
  }
  async function change(change: Record<string, unknown>, consequence: string) {
    if (!selected || !window.confirm(`${selected.username}: ${consequence}. Confirmar?`)) return;
    try { await client.update(selected, change); setSelected(null); await refresh(); }
    catch { setStatus('Falha na alteração da conta'); }
  }
  async function permission(capability: string, allowed: boolean) {
    if (!selected) return;
    try { await client.setPermission(selected.id, capability, allowed); setPermissions(await client.permissions(selected.id)); }
    catch { setStatus('Falha ao alterar permissão'); }
  }
  return <div className="admin-app"><header><h2>Administração</h2><span>{status}</span><button onClick={() => void refresh()}>Atualizar</button></header>
    <div className="admin-layout"><aside><button onClick={() => void create()}>+ Criar usuário</button>{accounts.map(account => <button key={account.id} className={selected?.id === account.id ? 'selected' : ''} onClick={() => setSelected(account)}>{account.username}<small>{account.role} · {account.state}</small></button>)}</aside>
      <main>{selected ? <><h3>{selected.username}</h3><p>ID: {selected.id}</p><p>Ambiente: {environment} <button onClick={() => void client.retry(selected.id).then(() => setEnvironment('running')).catch(() => setStatus('Falha ao retentar ambiente'))}>Retentar</button></p>
        <div className="admin-actions"><button onClick={() => { const value = window.prompt('Novo nome', selected.username); if (value) void change({ username: value }, 'renomear usuário'); }}>Renomear</button><button onClick={() => { const value = window.prompt('Nova senha'); if (value) void change({ password: value }, 'redefinir senha'); }}>Redefinir senha</button><button onClick={() => void change({ state: selected.state === 'active' ? 'disabled' : 'active' }, selected.state === 'active' ? 'desativar conta e parar processos' : 'reativar conta')}>{selected.state === 'active' ? 'Desativar' : 'Ativar'}</button><button onClick={() => void change({ state: 'deleted' }, 'excluir conta, parar processos e preservar arquivos')}>Excluir conta</button><button onClick={() => { if (window.confirm(`Parar a sessão de ${selected.username}? Todos os processos serão cancelados; arquivos preservados.`)) void client.stop(selected.id).then(refresh).catch(() => setStatus('Falha ao parar sessão')); }}>Parar sessão</button></div>
        <h4>Permissões efetivas</h4><div className="permission-grid">{availableCapabilities.map(capability => <label key={capability}><input type="checkbox" checked={permissions.includes(capability)} onChange={event => void permission(capability, event.target.checked)} />{capability}</label>)}</div>
        <h4>Sessões web</h4>{sessions.filter(session => !session.revoked_at).map(session => <div className="admin-session" key={session.id}>{session.id.slice(0, 8)} · {new Date(session.created_at).toLocaleString('pt-BR')}<button onClick={() => { if (window.confirm(`Revogar acesso web de ${selected.username}? Processos e janelas continuam.`)) void client.revoke(session.id).then(() => client.sessions(selected.id).then(setSessions)).catch(() => setStatus('Falha ao revogar sessão')); }}>Revogar acesso</button></div>)}</> : <p>Selecione uma conta para gerenciar.</p>}
        <h3>Backup</h3>{backup && <div className="backup-form"><label><input type="checkbox" checked={backup.enabled} onChange={event => setBackup({ ...backup, enabled: event.target.checked })} /> Ativado</label><label>Frequência (horas)<input type="number" min="1" value={backup.frequency_hours} onChange={event => setBackup({ ...backup, frequency_hours: Number(event.target.value) })} /></label><label>Destino absoluto<input value={backup.destination} onChange={event => setBackup({ ...backup, destination: event.target.value })} placeholder="/var/backups/aetherdesk" /></label><label>Retenção<select value={backup.retention_mode} onChange={event => setBackup({ ...backup, retention_mode: event.target.value as BackupPolicy['retention_mode'] })}><option value="replace">Substituir backup anterior</option><option value="days">Manter por dias</option></select></label>{backup.retention_mode === 'days' && <label>Dias<input type="number" min="1" value={backup.retention_days || 7} onChange={event => setBackup({ ...backup, retention_days: Number(event.target.value) })} /></label>}<button onClick={() => void client.configureBackup(backup).then(() => setStatus('Backup configurado')).catch(() => setStatus('Falha ao configurar backup'))}>Salvar configuração</button></div>}
        <h3>Auditoria recente</h3>{audit.slice(0, 20).map(row => <div className="audit-row" key={row.id}>{new Date(row.at).toLocaleString('pt-BR')} · {row.operation} · {row.target_id?.slice(0, 8)}</div>)}
      </main></div></div>;
}

export function SettingsApp({ theme, onTheme }: { theme: 'dark' | 'light'; onTheme: (theme: 'dark' | 'light') => void }) {
  return <div className="admin-app settings-app"><h2>Configurações pessoais</h2><label>Tema<select value={theme} onChange={event => onTheme(event.target.value as 'dark' | 'light')}><option value="dark">Escuro</option><option value="light">Claro</option></select></label><p>Janelas, posições e tema são salvos na sua conta.</p></div>;
}
