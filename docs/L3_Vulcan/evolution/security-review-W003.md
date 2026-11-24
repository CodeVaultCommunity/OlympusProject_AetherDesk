# Revisão de segurança W003

Plano `c1cf6012-e0a4-4f5a-a7fc-52a6ff0363fd` v5. Escopo: componentes isolados I006–I009 e fixtures descartáveis, sem exposição HTTP global ou promoção de produção.

| Caso | Controle e evidência | Limite antes da W005/W006 |
| --- | --- | --- |
| Capability revogada deixa atalho/janela acessível | `visibleApps` filtra capacidades efetivas; E2E de revogação fecha app/janela e endpoint existente ainda nega acesso | Repetir na composição global W005 |
| Wallpaper malformado ou com metadata | assinatura/decodificação/tamanho, recodificação canvas, hash, storage local por conta e limpeza; E2E nos três motores | CSP e inspeção assistiva/nativa em W006 |
| Dockerfile malicioso e cache entre contas | usuário não fornece Dockerfile; builder gera somente FROM/COPY/LABEL/USER/WORKDIR, sem RUN, contexto limitado e sem cache/rede; imagem por digest, labels owner e scan obrigatório | Scanner de release real, dependências/base e artefatos verificáveis em I014 |
| Privilege escalation, host mount, socket e egress de workload | teste Docker real confere rootfs readonly, UID 10001, cap-drop, quotas, sem bind, rede none ou bridge interna sem porta publicada | Política de bridge, proxy público e host Linux independente em W005/W006 |
| Secret exposto por config/env/log | vault AES-GCM com scope, somente ref no banco, stdin para tmpfs; teste real confirma ausência no Docker inspect/volumes; admin não recebe logs privados | Não habilitar template sem `/bin/sh` e comando explícito; redigir logs de app em integração |
| SSRF, metadata, redirect, DNS rebinding ou rota de outro owner | host UUID, owner e IP/subnet fixados; proxy não aceita URL externa nem segue redirect e remove credenciais; testes de collision/rebinding/IDOR | HTTP integrado, WebSocket, TLS, domínio e colisão pública em W005/W006 |
| Git hook/config/filtro do repositório executa código | argv fixo, hooks/global config/prompts desativados, repo config hostil recusada, path e remote allowlisted | Revalidar no broker e egress reais W005 |
| Token Git ou AI reaparece em saída | askpass fixo recebe token só em env de processo, secret por scope, stderr Git/Docker não devolvido; chat audit sem conteúdo | Teste HTTP remoto/egress e logs integrados W005/W006 |
| Prompt injection autoriza tool destrutiva | saída externa é dado; registry pinado, capability e ticket exato antes do efeito, replay bloqueado, revogação por bloco e `unknown` para efeito incerto | UI confiável de aprovação e registro efetivo das tools em W004/W005 |
| Job duplo ou status falso | `operation_id`, lease/fencing, supersessão de pendente, teste de 100 workloads sem start duplicado | Crash/restart e múltiplos processos no release candidate W005/W006 |

As fixtures de scanner, provider e upstream HTTP são controladas, não um atestado de serviço externo. Os módulos permanecem desabilitados na composição global até a onda apropriada. Evidência W003 não certifica produção.
