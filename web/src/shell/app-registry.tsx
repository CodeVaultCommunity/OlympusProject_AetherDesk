import type { ReactNode } from 'react';
import type { WindowKind } from '../window-state';
import { ideDescriptor } from '../apps/ide/descriptor';
import { containersDescriptor } from '../apps/containers/descriptor';
import { aiDescriptor } from '../apps/ai/descriptor';

export type AppDescriptor = {
  kind: WindowKind;
  title: string;
  description: string;
  capability: string;
  alternativeCapability?: string;
  icon: ReactNode;
};

const shape = (children: ReactNode) => <svg aria-hidden="true" viewBox="0 0 24 24" fill="none"
  stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{children}</svg>;

export const appRegistry: readonly AppDescriptor[] = [
  { kind: 'explorer', title: 'Explorador', description: 'Arquivos e pastas', capability: 'files.read',
    icon: shape(<><path d="M3 7h7l2 2h9v10H3z" /><path d="M3 7V5h7l2 2" /></>) },
  { kind: 'editor', title: 'Editor', description: 'Código e texto', capability: 'files.read',
    icon: shape(<><path d="m8 7-5 5 5 5m8-10 5 5-5 5m-2-14-4 18" /></>) },
  { kind: 'terminal', title: 'Terminal', description: 'Bash interativo', capability: 'terminal.open',
    icon: shape(<><rect x="2.5" y="4" width="19" height="16" rx="2" /><path d="m6 9 3 3-3 3m6 0h5" /></>) },
  { kind: 'monitor', title: 'Monitor', description: 'Recursos do sistema', capability: 'metrics.self',
    icon: shape(<><path d="M3 19h18M5 16V9m5 7V5m5 11v-4m5 4V7" /></>) },
  { kind: 'admin', title: 'Administração', description: 'Contas e ambientes', capability: 'accounts.view',
    icon: shape(<><circle cx="12" cy="8" r="3" /><path d="M5 20v-2a7 7 0 0 1 14 0v2M3 20h18" /></>) },
  { kind: 'settings', title: 'Configurações', description: 'Preferências pessoais', capability: 'preferences.read',
    icon: shape(<><circle cx="12" cy="12" r="3" /><path d="M12 2v3m0 14v3M2 12h3m14 0h3M5 5l2 2m10 10 2 2M19 5l-2 2M7 17l-2 2" /></>) },
  ideDescriptor,
  { ...containersDescriptor, alternativeCapability: 'workloads.control.other' },
  aiDescriptor,
];

export function visibleApps(permissions: readonly string[]): AppDescriptor[] {
  const granted = new Set(permissions);
  return appRegistry.filter(app => granted.has(app.capability) ||
    !!app.alternativeCapability && granted.has(app.alternativeCapability));
}

export function appByKind(kind: WindowKind): AppDescriptor {
  const descriptor = appRegistry.find(app => app.kind === kind);
  if (!descriptor) throw new Error(`Unknown app: ${kind}`);
  return descriptor;
}
