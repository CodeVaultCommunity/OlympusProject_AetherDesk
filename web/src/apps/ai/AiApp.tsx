import { useCallback, useEffect, useRef, useState } from 'react';
import type { AiClient, ApprovalTicket, ChatMessage, Conversation, ProviderInfo, ToolProposal, Usage } from './contracts';
import './ai.css';

function canonical(value: unknown): string {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && typeof value === 'object') return '{' + Object.keys(value).sort()
    .map(key => JSON.stringify(key) + ':' + canonical((value as Record<string, unknown>)[key])).join(',') + '}';
  return JSON.stringify(value);
}
async function argsHash(value: Record<string, unknown>): Promise<string> {
  const bytes = new TextEncoder().encode(canonical(value));
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('');
}
const riskLabel = { read: 'Leitura', write: 'Mutação', destructive: 'Destruição' };
const errorText: Record<string, string> = {
  APPROVAL_MISMATCH: 'A ferramenta, os argumentos ou a versão mudaram. Solicite nova aprovação.',
  APPROVAL_REPLAY: 'Esta aprovação já foi usada. Solicite uma nova.',
  APPROVAL_EXPIRED: 'A aprovação expirou. Solicite uma nova.',
  SESSION_REVOKED: 'Sua sessão foi revogada. Faça login novamente.',
  TOOL_SOURCE_DISABLED: 'O servidor da ferramenta foi desabilitado.',
  TOOL_FAILED: 'O resultado da ferramenta é incerto. Consulte a auditoria antes de repetir.',
  PROVIDER_DISABLED: 'O provedor está desabilitado.',
};
function errorMessage(error: unknown) {
  const code = error instanceof Error ? error.message : String(error);
  return errorText[code] || code;
}

export function AiApp({ client, permissions }: { client: AiClient; permissions: readonly string[] }) {
  const canChat = permissions.includes('ai.chat');
  const canTools = permissions.includes('ai.tools');
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [providerName, setProviderName] = useState('');
  const [model, setModel] = useState('');
  const [secret, setSecret] = useState('');
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [prompt, setPrompt] = useState('');
  const [streamText, setStreamText] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [disclosure, setDisclosure] = useState(false);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [proposals, setProposals] = useState<ToolProposal[]>([]);
  const [selected, setSelected] = useState<ToolProposal | null>(null);
  const [ticket, setTicket] = useState<ApprovalTicket | null>(null);
  const [approved, setApproved] = useState(false);
  const [panel, setPanel] = useState<'chat' | 'tools' | 'settings'>('chat');
  const [status, setStatus] = useState('Carregando IA…');
  const [offline, setOffline] = useState(false);
  const [busy, setBusy] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const approvalRef = useRef<HTMLDivElement>(null);
  const provider = providers.find(item => item.name === providerName);

  const refresh = useCallback(async () => {
    try {
      const [nextProviders, nextConversations, nextUsage, nextProposals] = await Promise.all([
        client.providers(), client.conversations(), client.usage(),
        canTools ? client.proposals() : Promise.resolve([]),
      ]);
      setProviders(nextProviders); setConversations(nextConversations); setUsage(nextUsage);
      setProposals(nextProposals);
      setProviderName(old => old || nextProviders.find(item => item.enabled)?.name || '');
      setOffline(false); setStatus('IA atualizada');
    } catch { setOffline(true); setStatus('Offline. Não é possível enviar mensagens ou aprovar ações.'); }
  }, [client, canTools]);
  useEffect(() => { if (!canChat) return; const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer); }, [canChat, refresh]);
  function chooseProvider(name: string) { setProviderName(name); setDisclosure(false); setModel('');
    setConversation(null); setMessages([]); }
  useEffect(() => {
    if (!selected) return;
    const before = document.activeElement as HTMLElement | null;
    const dialog = approvalRef.current;
    dialog?.querySelector('button')?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); setSelected(null); setTicket(null); return; }
      if (event.key !== 'Tab' || !dialog) return;
      const controls = [...dialog.querySelectorAll('button')];
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', key);
    return () => { document.removeEventListener('keydown', key); before?.focus(); };
  }, [selected]);
  useEffect(() => () => abort.current?.abort(), []);

  async function openConversation(item: Conversation) {
    try { setMessages(await client.messages(item.id)); setConversation(item); setProviderName(item.provider);
      setDisclosure(false); setStatus('Conversa aberta'); }
    catch (error) { setStatus(errorMessage(error)); }
  }
  async function createConversation() {
    if (!provider?.enabled) { setStatus('Selecione um provedor habilitado.'); return; }
    try { const next = await client.create(provider.name); setConversations(old => [next, ...old]);
      setConversation(next); setMessages([]); setStatus('Conversa criada'); }
    catch (error) { setStatus(errorMessage(error)); }
  }
  async function send() {
    if (!conversation || !prompt.trim() || streaming || offline || !provider || conversation.provider !== provider.name) return;
    if (provider.external && !disclosure) { setStatus('Leia e aceite o envio de dados ao provedor antes de continuar.'); return; }
    const text = prompt.trim();
    const controller = new AbortController(); abort.current = controller;
    setPrompt(''); setStreamText(''); setStreaming(true); setStatus('Resposta em andamento');
    setMessages(old => [...old, { id: crypto.randomUUID(), role: 'user', content: text, status: 'completed' }]);
    try {
      await client.stream(conversation.id, text, disclosure, controller.signal,
        chunk => setStreamText(old => old + chunk));
      if (!controller.signal.aborted) {
        setMessages(await client.messages(conversation.id)); setStreamText(''); setStatus('Resposta concluída');
        setUsage(await client.usage());
      }
    } catch (error) { setStatus(controller.signal.aborted ? 'Resposta cancelada.' : errorMessage(error)); }
    finally { setStreaming(false); abort.current = null; }
  }
  async function saveProvider() {
    if (!provider || !model) { setStatus('Selecione provedor e modelo.'); return; }
    setBusy(true);
    try { await client.saveProvider(provider.name, model, secret || undefined); setSecret('');
      setStatus('Configuração salva. O secret não pode ser lido de volta.'); }
    catch (error) { setStatus(errorMessage(error)); }
    finally { setBusy(false); }
  }
  async function exportConversation() {
    if (!conversation) return;
    try {
      const data = await client.export(conversation.id);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a'); link.href = url; link.download = `conversa-${conversation.id}.json`;
      link.click(); URL.revokeObjectURL(url); setStatus('Conversa exportada');
    } catch (error) { setStatus(errorMessage(error)); }
  }
  async function deleteConversation() {
    if (!conversation) return;
    try { await client.delete(conversation.id);
      setConversations(old => old.filter(item => item.id !== conversation.id));
      setConversation(null); setMessages([]); setStatus('Conversa excluída'); }
    catch (error) { setStatus(errorMessage(error)); }
    finally { setDeleteConfirm(false); }
  }
  async function requestTicket(proposal: ToolProposal) {
    setBusy(true); setApproved(false); setTicket(null);
    try {
      const next = await client.requestApproval(proposal);
      const hash = await argsHash(proposal.arguments);
      if (next.tool !== proposal.name || next.version !== proposal.version || next.argumentsHash !== hash ||
          next.expiresAt <= Date.now() / 1000) throw new Error('APPROVAL_MISMATCH');
      setTicket(next); setStatus('Pedido de aprovação vinculado aos argumentos exibidos.');
    } catch (error) { setStatus(errorMessage(error)); }
    finally { setBusy(false); }
  }
  async function approveAndInvoke() {
    if (!selected || !ticket || busy || approved) return;
    if (ticket.expiresAt <= Date.now() / 1000) { setTicket(null); setStatus(errorText.APPROVAL_EXPIRED); return; }
    setBusy(true);
    try {
      await client.approve(ticket); setApproved(true);
      await client.invoke(selected, ticket, crypto.randomUUID());
      setStatus(`Ferramenta ${selected.name} concluída. Consulte a atividade para detalhes.`);
      setSelected(null); setTicket(null); setProposals(old => old.filter(item => item.id !== selected.id));
    } catch (error) { setTicket(null); setStatus(errorMessage(error)); }
    finally { setBusy(false); }
  }
  if (!canChat) return <section className="ai-app"><p role="alert">Sem permissão para usar IA.</p></section>;
  return <section className="ai-app" aria-label="IA"><header className="ai-header"><h2>Assistente de IA</h2>
    <nav aria-label="Seções"><button aria-current={panel === 'chat' ? 'page' : undefined}
      onClick={() => setPanel('chat')}>Chat</button>{canTools && <button aria-current={panel === 'tools' ? 'page' : undefined}
      onClick={() => setPanel('tools')}>Ferramentas</button>}<button aria-current={panel === 'settings' ? 'page' : undefined}
      onClick={() => setPanel('settings')}>Configuração</button></nav><button onClick={() => void refresh()}>Atualizar</button></header>
    <p className="ai-status" role="status">{status}</p>
    {panel === 'chat' && <div className="ai-chat"><aside aria-label="Histórico"><h3>Conversas</h3>
      <button disabled={offline} onClick={() => void createConversation()}>Nova conversa</button>
      <ul>{conversations.map(item => <li key={item.id}><button aria-current={conversation?.id === item.id ? 'page' : undefined}
        onClick={() => void openConversation(item)}>{item.title}</button></li>)}</ul></aside>
      <main><div className="ai-disclosure"><label>Provedor <select value={providerName}
        onChange={event => chooseProvider(event.target.value)}>{providers.map(item => <option key={item.name}
          value={item.name} disabled={!item.enabled}>{item.name}</option>)}</select></label>
        {provider && <p>{provider.external ? 'Externo' : 'Local'} · Enviados: {provider.dataSent} · Retenção: {provider.retentionDays} dias</p>}
        {provider?.external && <label><input type="checkbox" checked={disclosure}
          onChange={event => setDisclosure(event.target.checked)} />Aceito enviar estes dados ao provedor</label>}</div>
        <div className="ai-messages" aria-live="polite">{messages.map(item => <article key={item.id}>
          <strong>{item.role === 'user' ? 'Você' : item.role === 'assistant' ? 'Assistente' : 'Ferramenta'}</strong>
          <p>{item.content}</p><small>{item.status}</small></article>)}
          {streaming && <article><strong>Assistente · respondendo</strong><p>{streamText}</p></article>}</div>
        <div className="ai-compose"><label>Mensagem <textarea value={prompt} maxLength={16384}
          onChange={event => setPrompt(event.target.value)} /></label><button disabled={!conversation || offline || streaming || !prompt.trim()}
          onClick={() => void send()}>Enviar</button>{streaming && <button onClick={() => abort.current?.abort()}>Cancelar resposta</button>}</div>
        {conversation && <div className="ai-history-actions"><button onClick={() => void exportConversation()}>Exportar conversa</button>
          <button onClick={() => setDeleteConfirm(true)}>Excluir conversa</button></div>}</main></div>}
    {panel === 'tools' && canTools && <div className="ai-tools"><h3>Atividade de ferramentas</h3>
      <p>Conteúdo de respostas, arquivos e logs é tratado como dado; não concede permissões.</p>
      <ul>{proposals.map(proposal => <li key={proposal.id}><strong>{proposal.name}</strong> · {riskLabel[proposal.risk]}
        · {proposal.source === 'native' ? 'Nativa' : `Servidor externo ${proposal.source} ${proposal.serverVersion || ''}`}
        <button onClick={() => { setSelected(proposal); setTicket(null); setApproved(false); }}>Revisar ação</button></li>)}</ul>
      {!proposals.length && <p>Nenhuma ação pendente.</p>}</div>}
    {panel === 'settings' && <div className="ai-settings"><h3>Configuração e permissões</h3>
      <p>Capacidades: {permissions.join(', ') || 'nenhuma'}. Ferramentas exigem autorização do servidor.</p>
      <label>Provedor <select value={providerName} onChange={event => chooseProvider(event.target.value)}>
        {providers.map(item => <option key={item.name} value={item.name} disabled={!item.enabled}>{item.name}</option>)}</select></label>
      <label>Modelo <select value={model} onChange={event => setModel(event.target.value)}><option value="">Selecione</option>
        {provider?.models.map(name => <option key={name}>{name}</option>)}</select></label>
      <label>Secret do provedor (somente gravação) <input type="password" value={secret}
        autoComplete="off" onChange={event => setSecret(event.target.value)} /></label>
      <button disabled={busy || offline} onClick={() => void saveProvider()}>Salvar configuração</button>
      {usage && <p>Uso: {usage.usedChars}/{usage.limitChars} caracteres · custo {usage.cost}/{usage.limitCost}</p>}
      <p>Histórico retido conforme o provedor. Exporte ou exclua uma conversa no Chat.</p></div>}
    {selected && <div className="ai-backdrop"><div className="ai-approval" ref={approvalRef} role="alertdialog"
      aria-modal="true" aria-labelledby="ai-approval-title" aria-describedby="ai-approval-detail">
      <h3 id="ai-approval-title">Aprovar {selected.name}</h3><div id="ai-approval-detail">
        <p>Origem: {selected.source === 'native' ? 'Nativa' : `Servidor externo ${selected.source} · versão ${selected.serverVersion}`}</p>
        <p>Tool versão {selected.version} · risco: {riskLabel[selected.risk]}</p>
        <p>Alvo: {selected.target}</p><p>Consequência: {selected.consequence}</p>
        <p>Argumentos exatos enviados:</p><pre>{canonical(selected.arguments)}</pre>
        <p>Schema: {selected.schemaDigest}</p>
        {ticket && <p>Expira em {new Date(ticket.expiresAt * 1000).toLocaleString('pt-BR')}</p>}</div>
      <div><button onClick={() => { setSelected(null); setTicket(null); }}>Negar</button>
        {!ticket ? <button disabled={busy || offline} onClick={() => void requestTicket(selected)}>Solicitar ticket</button> :
          <button disabled={busy || offline || approved} onClick={() => void approveAndInvoke()}>Aprovar esta ação</button>}</div></div></div>}
    {deleteConfirm && <div className="ai-backdrop"><div className="ai-approval" role="alertdialog" aria-modal="true"
      aria-label="Excluir conversa"><p>Excluir a conversa selecionada e seu histórico?</p>
      <button onClick={() => setDeleteConfirm(false)}>Cancelar</button>
      <button onClick={() => void deleteConversation()}>Excluir definitivamente</button></div></div>}
  </section>;
}
