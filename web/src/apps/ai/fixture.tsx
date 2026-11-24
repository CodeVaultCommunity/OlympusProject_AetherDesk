import { createRoot } from 'react-dom/client';
import { AiApp } from './AiApp';
import type { AiClient, ChatMessage, ToolProposal } from './contracts';

const mode = new URLSearchParams(location.search).get('mode');
let history: ChatMessage[] = [];
const proposal: ToolProposal = { id: 'p1', name: 'broker.remove', version: '2', source: 'third-party',
  serverVersion: '4', risk: 'destructive', target: 'workspace/demo/src/main.ts',
  consequence: 'Remover o arquivo do workspace', arguments: { path: 'src/main.ts' }, schemaDigest: 'sha256:fixture' };
const client: AiClient = {
  async providers() { return [{ name: 'fake', models: ['fast'], external: true, enabled: true,
    dataSent: 'mensagem e histórico desta conversa', retentionDays: 30 }]; },
  async saveProvider() {},
  async conversations() { return [{ id: 'c1', provider: 'fake', title: 'Conversa de teste', updatedAt: '2026-11-24' }]; },
  async create() { return { id: 'c2', provider: 'fake', title: 'Nova conversa', updatedAt: '2026-11-24' }; },
  async messages() { return history; },
  async stream(_id, prompt, accepted, signal, onChunk) {
    if (!accepted) throw new Error('DISCLOSURE_REQUIRED');
    history = [...history, { id: crypto.randomUUID(), role: 'user', content: prompt, status: 'completed' }];
    onChunk('Resposta parcial');
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(resolve, 150);
      signal.addEventListener('abort', () => { clearTimeout(timer); reject(new Error('cancelled')); }, { once: true });
    });
    history = [...history, { id: crypto.randomUUID(), role: 'assistant', content: 'Resposta parcial', status: 'completed' }];
  },
  async export() { return { messages: history }; }, async delete() { history = []; },
  async usage() { return { usedChars: 20, limitChars: 10000, cost: '0', limitCost: '1' }; },
  async proposals() { return [proposal]; },
  async requestApproval(item) {
    const encoded = new TextEncoder().encode(JSON.stringify(item.arguments));
    const digest = await crypto.subtle.digest('SHA-256', encoded);
    const hash = [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('');
    return { id: 'ticket', tool: item.name, version: item.version,
      argumentsHash: mode === 'mismatch' ? 'changed' : hash,
      expiresAt: Date.now() / 1000 + 60, nonce: 'nonce' };
  },
  async approve() { if (mode === 'revoked') throw new Error('SESSION_REVOKED'); },
  async invoke() {},
};
createRoot(document.getElementById('root')!).render(<AiApp client={client}
  permissions={mode === 'forbidden' ? [] : ['ai.chat', 'ai.tools']} />);
