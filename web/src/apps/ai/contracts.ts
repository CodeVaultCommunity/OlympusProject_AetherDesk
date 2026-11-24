export type ProviderInfo = { name: string; models: string[]; external: boolean; enabled: boolean;
  dataSent: string; retentionDays: number; costPerThousand?: string };
export type ChatMessage = { id: string; role: 'user' | 'assistant' | 'tool'; content: string; status: string };
export type Conversation = { id: string; provider: string; title: string; updatedAt: string };
export type ToolProposal = { id: string; name: string; version: string; source: string;
  serverVersion?: string; risk: 'read' | 'write' | 'destructive'; target: string;
  consequence: string; arguments: Record<string, unknown>; schemaDigest: string };
export type ApprovalTicket = { id: string; tool: string; version: string; argumentsHash: string;
  expiresAt: number; nonce: string };
export type Usage = { usedChars: number; limitChars: number; cost: string; limitCost: string };
export interface AiClient {
  providers(): Promise<ProviderInfo[]>;
  saveProvider(name: string, model: string, secret?: string): Promise<void>;
  conversations(): Promise<Conversation[]>;
  create(provider: string): Promise<Conversation>;
  messages(id: string): Promise<ChatMessage[]>;
  stream(id: string, prompt: string, disclosureAccepted: boolean, signal: AbortSignal,
    onChunk: (chunk: string) => void): Promise<void>;
  export(id: string): Promise<unknown>;
  delete(id: string): Promise<void>;
  usage(): Promise<Usage>;
  proposals(): Promise<ToolProposal[]>;
  requestApproval(proposal: ToolProposal): Promise<ApprovalTicket>;
  approve(ticket: ApprovalTicket): Promise<void>;
  invoke(proposal: ToolProposal, ticket: ApprovalTicket, operationId: string): Promise<unknown>;
}
