# Portão W001 — evolução AetherDesk

Data: 23/11/2026. Plano `c1cf6012-e0a4-4f5a-a7fc-52a6ff0363fd` v3. Commit `f0e1b6377226b5c56db2467f021c06c510fff6c0`.

## Aceite individual

- I001: **aceito tecnicamente com limites registrados**. [Baseline](W001-baseline.md) mapeia as 12 seções do relato e L001–L032, distingue inspeção atual de números herdados, registra TypeScript e dez testes Python seguros. Nenhum segredo ou dado pessoal foi registrado. Docker, browser e carga não foram repetidos nesta onda porque a W001 não altera containers/bancos persistentes; essas provas continuam em W002/W006.
- I002: **aceito tecnicamente para contratos de desenvolvimento**. [Contratos](W001-contracts.md) registram matriz R003–R028, defaults de segurança, modelos de interface/dados, falhas, testes, lifecycle, migração, rollback, threat model, orçamento e ownership. Decisões U001–U010 têm resultado ou bloqueio explícito. A revisão de segurança do broker em Linux e a política operacional de backup continuam exigidas antes dos consumidores finais.

## Integração e condição de avanço

O código de aplicação não mudou. `git diff HEAD~1 HEAD -- apps web scripts` não mostrou mudanças nos caminhos de aplicação/medição desde a revisão anterior, mas os p95 do portão Vulcan continuam **históricos**; uma comparação de performance exige nova execução com dataset e ambiente identificados. A incompatibilidade entre README da raiz e `gate-W004.md`, e as divergências de envelope/rotas entre v1 documentada e implementação, passam como trabalho explícito a W002/W005.

Portão **aprovado tecnicamente para iniciar W002** com as seguintes travas: egress, Dockerfile de usuário, providers de IA e proxy público ficam desabilitados; broker/daemon só em fixture Linux até inspeção de processo/mount; RPO, RTO e retenção são configuráveis sem meta fixa, conforme decisão do responsável em 23/11/2026, e o destino/chave precisam ser configurados antes de backup real; release em produção permanece fora de escopo. Esta aprovação não antecipa aceite de W002 nem dispensa testes de browser, multiusuário, isolamento, migração e restore.

Revisão técnica e de segurança: comparação estática dos módulos `shell`, `identity`, `administration`, `runtime`, `files`, `terminal`, `backup` e contratos existentes; controles novos foram classificados como pendentes de teste. Executor/revisor técnico: Codex. Nenhuma revisão externa ou aceite humano é alegado.
