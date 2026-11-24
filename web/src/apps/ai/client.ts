import { ApiError, requestV2 } from '../../clients';
import type { AiClient } from './contracts';
const q = encodeURIComponent;
const body = (value: unknown): RequestInit => ({ method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(value) });
function csrf() { return document.cookie.split('; ').find(part => part.startsWith('aether_csrf='))?.split('=')[1] || ''; }
export const aiClient: AiClient = {
  providers: () => requestV2('/ai/providers'),
  saveProvider: async (name, model, secret) => { await requestV2('/ai/provider', body({ name, model, secret })); },
  conversations: () => requestV2('/ai/conversations'),
  create: provider => requestV2('/ai/conversations', body({ provider })),
  messages: id => requestV2(`/ai/conversations/${q(id)}/messages`),
  async stream(id, prompt, disclosureAccepted, signal, onChunk) {
    const response = await fetch(`/api/v2/ai/conversations/${q(id)}/stream`, {
      ...body({ prompt, disclosureAccepted }), signal, credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf(), 'X-AetherDesk-API-Version': '2' },
    });
    if (!response.ok) {
      const error = await response.json().catch(() => null);
      throw new ApiError(response.status, error?.error?.code || error?.detail || `HTTP_${response.status}`);
    }
    if (!response.body) throw new ApiError(503, 'STREAM_UNAVAILABLE');
    const reader = response.body.getReader();
    const decoder = new TextDecoder(); let buffer = '';
    try {
      while (true) {
        const next = await reader.read();
        if (next.done) break;
        buffer += decoder.decode(next.value, { stream: true });
        if (buffer.length > 131072) throw new ApiError(502, 'STREAM_TOO_LARGE');
        let index: number;
        while ((index = buffer.indexOf('\n')) >= 0) {
          const line = buffer.slice(0, index); buffer = buffer.slice(index + 1);
          if (!line) continue;
          const event = JSON.parse(line) as { type: string; text?: string; code?: string };
          if (event.type === 'chunk') onChunk(event.text || '');
          if (event.type === 'error') throw new ApiError(502, event.code || 'STREAM_FAILED');
        }
      }
    } finally { reader.releaseLock(); }
  },
  export: id => requestV2(`/ai/conversations/${q(id)}/export`),
  delete: async id => { await requestV2(`/ai/conversations/${q(id)}`, { method: 'DELETE' }); },
  usage: () => requestV2('/ai/usage'),
  proposals: () => requestV2('/ai/tools/proposals'),
  requestApproval: proposal => requestV2('/ai/tools/approvals', body({ proposalId: proposal.id })),
  approve: async ticket => { await requestV2(`/ai/tools/approvals/${q(ticket.id)}/approve`, body({ nonce: ticket.nonce })); },
  invoke: (proposal, ticket, operationId) => requestV2('/ai/tools/invoke', body({ proposalId: proposal.id,
    ticketId: ticket.id, nonce: ticket.nonce, operationId })),
};
