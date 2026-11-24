# Portão W004 — aplicativos isolados

Plano `c1cf6012-e0a4-4f5a-a7fc-52a6ff0363fd` v5. **Gate técnico local W004 aprovado em 24/11/2026** para os três aplicativos isolados. Base do workspace: `f0e1b6377226b5c56db2467f021c06c510fff6c0` com alterações não commitadas desta execução. A integração com shell, HTTP e serviços reais pertence à W005; este gate não afirma que ela ocorreu.

| Item | Aceite isolado e evidência |
| --- | --- |
| I010 IDE | `web/src/apps/ide/` exporta componente, contrato, descriptor e fixture. Abre arquivo pela árvore, mantém 12 abas no máximo, salva por revisão, recupera rascunho por conta/workspace/caminho, impede perda dirty, compara conflito, oferece busca/replace, Git diff/stage/commit/push e deploy com preview/job, terminal ancorável e split, estado LSP honesto. Quatro testes de componente e seis E2E nos três motores passaram. Terminal real, Git remoto e backend homologado são integração W005/I014. |
| I011 Containers | `web/src/apps/containers/` exporta componente, contrato, descriptor e fixture. Dono vê logs/métricas só próprios; admin control-only vê metadados e ações limitadas; sem capacidade não consulta dados. Build/ações usam ID de operação e confirmação de alvo/consequência; UI acompanha job, falha health/rollback, quota/scan/proxy, secret somente por referência. Cinco testes de componente e nove E2E nos três motores passaram. Listagem/cancelamento e política de rotas reais são integração W005. |
| I012 IA | `web/src/apps/ai/` exporta componente, contrato, descriptor e fixture. Chat externo exige disclosure, mostra provider/dados/retention/uso, permite cancelar, exportar e excluir. Secret é somente gravação. Approval em chrome próprio mostra tool, origem/servidor/versão, alvo, risco, consequência, argumentos, schema e expiração; hash/versão divergentes bloqueiam a UI e o backend I009 revalida replay/revogação. Quatro testes de componente e 12 E2E nos três motores passaram. Provider externo real permanece desabilitado até configuração e I014. |

## Verificações e tamanhos

- `pnpm test`: 23 testes frontend, zero falha; `pnpm lint` sem avisos; `pnpm exec tsc --noEmit` passou. Há uma mensagem inofensiva do canvas não implementado por jsdom durante axe no teste Containers; axe real passou no navegador.
- `node scripts/run-e2e.mjs tests/e2e/containers.spec.ts tests/e2e/ide.spec.ts tests/e2e/ai.spec.ts`: 27/27 E2E aprovados em Chromium, Firefox e WebKit. Inclui viewport CSS 390 px, teclado/Escape/foco, owner/admin/forbidden, conflito/recuperação, rollback, mismatch de ticket/revogação e axe WCAG A/AA. Não substitui leitor de tela nem zoom nativo.
- Build Vite isolado dos três `fixture.html`, manifesto em `web/.tmp/w004-bundles/`: Containers 12,47 kB bruto/4,34 kB gzip, IA 12,62/4,67, IDE 15,22/5,71. O limite local de 25 KiB gzip por chunk do app foi atendido; dependências compartilhadas são medidas separadamente. React compartilhado 69,32 KiB gzip, terminal tardio 84,76 KiB, Monaco tardio 747,90 KiB mais workers compartilhados 293,15 KiB. O chunk Monaco é grande e exige medição de carregamento/rede e decisão de orçamento no release candidate W005/I014; o tamanho isolado do app não representa download total.
- Capturas das jornadas críticas, inclusive aprovação, em `web/.tmp/w004-captures/` para os três motores. São artefatos locais descartáveis, sem dados reais. Fixtures fake não dão evidência de servidor integrado.

## Handoff W005

Registrar descriptors no catálogo e tipos de janela com capacidade efetiva; injetar `accountScope` estável da conta na IDE e remount ao trocar sessão. Criar adapters HTTP autenticados para `IdeClient`, `ContainersClient` e `AiClient`, sem aceitar owner/path/host arbitrário do navegador. Harmonizar estados/nomes de erro dos serviços I007–I009 e implementar listagem/cancelamento de jobs, propostas de tools, event stream e provider/model config antes de expor os botões. Preservar os contratos v1 e introduzir endpoints versionados, migrações/backup de fixture e kill switches. Não habilitar provider externo, Git remoto, deploy público ou tools externas sem políticas e testes I013/I014. A UI é defesa de apresentação; autorização, idempotência, approval, ownership e redaction são revalidados no servidor.

W005 está liberada apenas para I013 após este gate. W006 permanece bloqueada até W005.
