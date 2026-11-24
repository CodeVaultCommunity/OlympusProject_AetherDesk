import { useCallback, useEffect, useRef, useState } from 'react';
import type { ContainersClient, WorkloadAction, WorkloadJob, WorkloadMetrics, WorkloadSummary } from './contracts';
import './containers.css';

const terminal = new Set(['completed', 'failed', 'superseded', 'cancelled']);
const statusText: Record<string, string> = {
  running: 'Em execução', stopped: 'Parado', failed: 'Falhou', rolled_back: 'Revertido',
  removed: 'Removido', absent: 'Ausente', error: 'Erro no runtime',
};
const jobText: Record<string, string> = {
  pending: 'Em andamento', completed: 'Concluído', failed: 'Falhou',
  superseded: 'Substituído por pedido mais recente', cancelled: 'Cancelado',
};
const jobErrorText: Record<string, string> = {
  HEALTH_FAILED: 'A verificação de saúde falhou; consulte o estado e a versão anterior.',
  QUOTA_EXCEEDED: 'A quota da conta foi atingida.',
  SCAN_REJECTED: 'A análise de segurança bloqueou a imagem.',
  PROXY_DENIED: 'A rota solicitada foi bloqueada pela política de rede.',
  DEPLOY_DISABLED: 'A publicação foi suspensa pelo interruptor operacional.',
  SAFE_MODE: 'O pedido foi suspenso pelo modo seguro.',
};
const consequence: Record<WorkloadAction, string> = {
  deploy: 'Publicar o template selecionado e reiniciar a aplicação.',
  start: 'Iniciar a aplicação com o último template aprovado.',
  stop: 'Interromper a aplicação e as conexões ativas.',
  restart: 'Reiniciar a aplicação e interromper conexões ativas.',
  remove: 'Remover a aplicação. O volume será eliminado após a retenção configurada.',
};
const actionLabel: Record<WorkloadAction, string> = {
  deploy: 'Publicar', start: 'Iniciar', stop: 'Parar', restart: 'Reiniciar', remove: 'Remover',
};

type Pending = { workload: WorkloadSummary; action: WorkloadAction; operationId: string };

export function ContainersApp({ client, permissions }: {
  client: ContainersClient; permissions: readonly string[];
}) {
  const canRead = permissions.includes('workloads.read');
  const canCreate = permissions.includes('workloads.create');
  const canBuild = permissions.includes('workloads.build');
  const canDeploy = permissions.includes('workloads.deploy');
  const canControl = permissions.includes('workloads.control');
  const canSecrets = permissions.includes('workloads.secrets');
  const canRoute = permissions.includes('workloads.route');
  const canAdmin = permissions.includes('workloads.control.other');
  const [mine, setMine] = useState<WorkloadSummary[]>([]);
  const [others, setOthers] = useState<WorkloadSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [view, setView] = useState<'mine' | 'admin'>(canRead ? 'mine' : 'admin');
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);
  const [notice, setNotice] = useState('');
  const [logs, setLogs] = useState<{ id: string; text: string } | null>(null);
  const [metrics, setMetrics] = useState<{ id: string; data: WorkloadMetrics } | null>(null);
  const [project, setProject] = useState('');
  const [name, setName] = useState('');
  const [template, setTemplate] = useState('');
  const [approvedTemplates, setApprovedTemplates] = useState<string[]>([]);
  const [secretName, setSecretName] = useState('');
  const [secretRef, setSecretRef] = useState('');
  const [pending, setPending] = useState<Pending | null>(null);
  const [job, setJob] = useState<WorkloadJob | null>(null);
  const [busy, setBusy] = useState(false);
  const lastOperation = useRef<{ id: string; run: () => Promise<void> } | null>(null);
  const confirmRef = useRef<HTMLDivElement>(null);
  const rows = view === 'mine' ? mine : others;
  const selected = rows.find(row => row.id === selectedId) || rows[0];
  const selectedKey = selected?.id;
  const selectedOwner = selected?.owner;

  const refresh = useCallback(async () => {
    try {
      const [owned, controllable, templates] = await Promise.all([
        canRead ? client.listMine() : Promise.resolve([]),
        canAdmin ? client.listControllable() : Promise.resolve([]),
        canDeploy ? client.templates() : Promise.resolve([]),
      ]);
      setMine(owned.filter(row => row.owner === 'self'));
      setOthers(controllable.filter(row => row.owner === 'other'));
      setApprovedTemplates(templates);
      setTemplate(old => templates.includes(old) ? old : templates[0] || '');
      setOffline(false); setNotice('');
    } catch {
      setOffline(true); setNotice('Sem conexão. Verifique a rede e tente atualizar.');
    } finally { setLoading(false); }
  }, [client, canAdmin, canRead, canDeploy]);
  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);
  useEffect(() => {
    if (!pending) return;
    const previous = document.activeElement as HTMLElement | null;
    const dialog = confirmRef.current;
    dialog?.querySelector('button')?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); setPending(null); return; }
      if (event.key !== 'Tab' || !dialog) return;
      const buttons = [...dialog.querySelectorAll('button')];
      const first = buttons[0], last = buttons[buttons.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('keydown', onKey); previous?.focus(); };
  }, [pending]);

  useEffect(() => {
    if (!job || terminal.has(job.status)) return;
    let active = true;
    const timer = window.setInterval(() => {
      void client.job(job.id).then(next => {
        if (!active) return;
        setJob(next);
        if (terminal.has(next.status)) void refresh();
      }).catch(() => { if (active) setNotice('Sem conexão com o job. Reconsulte antes de repetir a ação.'); });
    }, 1000);
    return () => { active = false; window.clearInterval(timer); };
  }, [client, job, refresh]);

  useEffect(() => {
    if (!selectedKey || selectedOwner !== 'self' || !canRead) return;
    let active = true;
    void Promise.all([client.logs(selectedKey), client.metrics(selectedKey)])
      .then(([nextLogs, nextMetrics]) => {
        if (active) { setLogs({ id: selectedKey, text: nextLogs.slice(0, 65536) });
          setMetrics({ id: selectedKey, data: nextMetrics }); }
      }).catch(() => { if (active) setNotice('Logs ou métricas indisponíveis.'); });
    return () => { active = false; };
  }, [client, selectedKey, selectedOwner, canRead]);

  async function startJob(run: () => Promise<WorkloadJob>, operationId: string) {
    setBusy(true); setNotice('');
    try {
      const next = await run();
      setJob(next);
      lastOperation.current = { id: operationId, run: async () => { setJob(await run()); } };
      if (terminal.has(next.status)) await refresh();
    } catch {
      setNotice('Pedido incerto. Consulte o job antes de repetir com a mesma chave.');
      lastOperation.current = { id: operationId, run: async () => { setJob(await run()); } };
    } finally { setBusy(false); }
  }

  async function consultLastOperation() {
    if (!lastOperation.current) return;
    setBusy(true);
    try { await lastOperation.current.run(); setNotice('Pedido consultado com a mesma chave.'); }
    catch { setNotice('Consulta indisponível. Tente novamente com a mesma chave.'); }
    finally { setBusy(false); }
  }

  function requestAction(workload: WorkloadSummary, action: WorkloadAction) {
    setPending({ workload, action, operationId: crypto.randomUUID() });
  }

  async function confirmAction() {
    if (!pending) return;
    const { workload, action, operationId } = pending;
    setPending(null);
    await startJob(() => client.request(workload.id, action, operationId,
      action === 'deploy' ? template : undefined), operationId);
  }

  async function build() {
    if (!project.trim()) { setNotice('Informe o projeto antes de iniciar o build.'); return; }
    const operationId = crypto.randomUUID();
    await startJob(() => client.build(project.trim(), operationId), operationId);
  }
  async function create() {
    if (!project.trim() || !name.trim()) { setNotice('Informe projeto e nome da aplicação.'); return; }
    setBusy(true);
    try { await client.create(project.trim(), name.trim()); await refresh();
      setName(''); setNotice('Aplicação criada. Selecione um template aprovado para publicar.'); }
    catch { setNotice('Não foi possível criar a aplicação. Verifique nome e quota.'); }
    finally { setBusy(false); }
  }

  async function saveSecretReference() {
    if (!selected || !secretName.match(/^[a-z][a-z0-9_]{0,40}$/) ||
        !secretRef.match(/^[0-9a-f-]{36}$/i)) {
      setNotice('Informe um nome e uma referência de secret válidos.'); return;
    }
    const operationId = crypto.randomUUID();
    setBusy(true);
    try {
      await client.configureSecrets(selected.id, { [secretName]: secretRef }, operationId);
      setSecretRef(''); setSecretName(''); setNotice('Referência salva. O valor do secret nunca é exibido.');
    } catch { setNotice('Não foi possível salvar a referência.'); }
    finally { setBusy(false); }
  }

  async function openRoute(workload: WorkloadSummary) {
    setBusy(true);
    try {
      const { host, ticket } = await client.routeTicket(workload.id);
      if (host !== workload.route || !/^[0-9a-f]{12}\.apps\.local$/.test(host))
        throw new Error('Rota inesperada');
      const form = document.createElement('form');
      form.method = 'POST'; form.action = `${window.location.protocol}//${host}/__aetherdesk/open`;
      const field = document.createElement('input');
      field.type = 'hidden'; field.name = 'ticket'; field.value = ticket;
      form.append(field); document.body.append(form); form.submit(); form.remove();
    } catch { setNotice('Não foi possível abrir a aplicação. Verifique a rota e a sessão.'); }
    finally { setBusy(false); }
  }

  if (!canRead && !canAdmin) return <section className="containers-app"><p role="alert">Sem permissão para ver aplicações.</p></section>;
  return <section className="containers-app" aria-label="Containers">
    <header className="containers-header"><div><h2>Aplicações</h2><p>Projetos e containers da sua conta</p></div>
      <button onClick={() => void refresh()} disabled={loading}>Atualizar</button></header>
    {offline && <p className="containers-alert" role="alert">Offline — ações indisponíveis até reconectar.</p>}
    {notice && <div className="containers-notice" role="status">{notice}
      {notice.includes('incerto') && <button disabled={busy || offline}
        onClick={() => void consultLastOperation()}>Consultar pedido</button>}</div>}
    <nav className="containers-tabs" aria-label="Visões">
      {canRead && <button aria-current={view === 'mine' ? 'page' : undefined} onClick={() => setView('mine')}>Minhas aplicações</button>}
      {canAdmin && <button aria-current={view === 'admin' ? 'page' : undefined} onClick={() => setView('admin')}>Controle administrativo</button>}
    </nav>
    {view === 'mine' && canCreate && <form className="containers-build" onSubmit={event => { event.preventDefault(); void create(); }}>
      <label>Projeto <input value={project} onChange={event => setProject(event.target.value)} placeholder="Nome do projeto" /></label>
      <label>Aplicação <input value={name} onChange={event => setName(event.target.value)} placeholder="Nome da aplicação" /></label>
      <button type="submit" disabled={busy || offline}>Criar aplicação</button>
      {canBuild && <button type="button" disabled={busy || offline} onClick={() => void build()}>Criar build aprovado</button>}
      <small>Dockerfile livre, mounts do host e flags Docker não são aceitos.</small>
    </form>}
    <div className="containers-body"><aside aria-label="Lista de aplicações">
      {loading ? <p>Carregando aplicações…</p> : rows.length === 0 ? <p>Nenhuma aplicação nesta visão.</p> : rows.map(row =>
        <button key={row.id} className={selected?.id === row.id ? 'selected' : ''}
          aria-current={selected?.id === row.id ? 'true' : undefined}
          onClick={() => setSelectedId(row.id)}><strong>{row.name}</strong><span>{row.project}</span>
          <small>{statusText[row.observed] || row.observed}</small></button>)}</aside>
      <main>{selected ? <>
        <div className="containers-detail-head"><div><h3>{selected.name}</h3><p>{selected.project} · {statusText[selected.observed] || selected.observed}</p></div>
          <span className="containers-health">Saúde: {selected.health}</span></div>
        <dl className="containers-facts"><div><dt>Template</dt><dd>{selected.template || 'Nenhum'}</dd></div>
          <div><dt>Porta interna</dt><dd>{selected.port ?? 'Sem rota'}</dd></div>
          <div><dt>Rota</dt><dd>{selected.route || 'Desativada'}</dd></div>
          <div><dt>Volume</dt><dd>{selected.volume}</dd></div></dl>
        <div className="containers-actions">
          {selected.owner === 'self' && canRoute && selected.route &&
            <button disabled={busy || offline} onClick={() => void openRoute(selected)}>Abrir aplicação</button>}
          {selected.owner === 'self' && canDeploy && <label>Template aprovado <select value={template}
            onChange={event => setTemplate(event.target.value)}>
            {approvedTemplates.length === 0 && <option value="">Nenhum template disponível</option>}
            {approvedTemplates.map(item => <option key={item} value={item}>{item}</option>)}
          </select></label>}
          {selected.owner === 'self' && canDeploy && <button disabled={busy || offline || !template.trim()}
            onClick={() => requestAction(selected, 'deploy')}>Publicar</button>}
          {((selected.owner === 'self' && canControl) || (selected.owner === 'other' && canAdmin)) && <>
            {selected.owner === 'self' && selected.observed === 'stopped' && selected.template &&
              <button disabled={busy || offline} onClick={() => requestAction(selected, 'start')}>Iniciar</button>}
            <button disabled={busy || offline} onClick={() => requestAction(selected, 'stop')}>Parar</button>
            <button disabled={busy || offline} onClick={() => requestAction(selected, 'restart')}>Reiniciar</button>
            <button disabled={busy || offline} onClick={() => requestAction(selected, 'remove')}>Remover</button></>}
        </div>
        {selected.observed === 'rolled_back' && <p className="containers-alert" role="status">A versão anterior foi restaurada após falha de saúde.</p>}
        {selected.owner === 'self' ? <>
          {canSecrets && <div className="containers-secrets"><h4>Referência de secret</h4>
            <p>Informe somente o ID de um secret já salvo no cofre. O valor não aparece aqui.</p>
            <label>Nome <input value={secretName} onChange={event => setSecretName(event.target.value)} /></label>
            <label>ID da referência <input value={secretRef} onChange={event => setSecretRef(event.target.value)} /></label>
            <button disabled={busy || offline} onClick={() => void saveSecretReference()}>Salvar referência</button></div>}
          <div className="containers-observe"><div><h4>Métricas</h4>{metrics?.id === selected.id ? <dl>
            <div><dt>CPU</dt><dd>{metrics.data.cpu}</dd></div><div><dt>Memória</dt><dd>{metrics.data.memory}</dd></div>
            <div><dt>Rede</dt><dd>{metrics.data.network}</dd></div><div><dt>Processos</dt><dd>{metrics.data.pids}</dd></div>
          </dl> : <p>Indisponíveis</p>}</div><div><h4>Logs privados</h4><pre>{logs?.id === selected.id ? logs.text || 'Sem logs disponíveis.' : 'Carregando logs…'}</pre></div></div>
        </> : <p className="containers-privacy">Controle administrativo não inclui acesso a logs, métricas privadas ou secrets de outras contas.</p>}
      </> : <p>Selecione uma aplicação.</p>}</main></div>
    {job && <aside className="containers-job" role="status"><strong>Job {job.action}: {jobText[job.status]}</strong>
      {job.errorCode && <span>Motivo: {jobErrorText[job.errorCode] || job.errorCode}</span>}
      {job.status === 'pending' && <button onClick={() => void client.cancel(job.id).then(setJob)
        .catch(() => setNotice('Cancelamento incerto. Consulte o job.'))}>Cancelar job</button>}
      {job.status === 'failed' && <button disabled={busy || offline}
        onClick={() => void consultLastOperation()}>Consultar pedido</button>}</aside>}
    {pending && <div className="containers-backdrop"><div ref={confirmRef} role="alertdialog" aria-modal="true"
      aria-labelledby="containers-confirm-title" aria-describedby="containers-confirm-detail" className="containers-confirm">
      <h3 id="containers-confirm-title">{actionLabel[pending.action]} {pending.workload.name}</h3>
      <p id="containers-confirm-detail">{consequence[pending.action]}</p>
      <div><button onClick={() => setPending(null)}>Cancelar</button><button onClick={() => void confirmAction()}>
        Confirmar</button></div></div></div>}
  </section>;
}
