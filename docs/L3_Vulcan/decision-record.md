# Decisões e bloqueios — W001/I001

Data: 22/11/2026. Estado: políticas U003/U004 definidas pelo responsável nesta conversa; contratos W001 congelados para W002. O host Linux final, destino de teste e limites medidos pertencem à homologação W004.

| ID | Decisão ou proposta | Evidência/pendência |
|---|---|---|
| D001 | Aplicação independente que adota a organização Vulcan Stable-v1.0.0 sem declarar conformidade formal. | Remoto identificado e 177 arquivos comparados; ver `source-and-prototype.md`. |
| D002 | Um registro de composição; Boundary apenas para HTTP/WS; caso de uso autoriza antes dos efeitos. | Compatível com exemplos e `AGENTS.md` da edição verificada. |
| D003 | Imagem recriável e volume por ID imutável; banco e segredos externos. | Protótipo de troca de imagem passou; host final ainda não testado. |
| U001 | Resolvida para a edição Stable-v1.0.0 no commit remoto `4ab5824a7c7c962e96ac4480e8c254d023ba75df`. | Comparação completa dos arquivos rastreados da edição; URL e commit registrados. |
| U002 | Docker Linux foi validado como mecanismo de protótipo. Runtime do servidor alvo e quotas permanecem pendentes. | Prova local passou; não há host Linux de homologação identificado. |
| U003 | Logout e revogação administrativa invalidam a sessão de autenticação sem interromper processos, PTYs ou janelas. Novo login restaura o desktop. Parar sessão é ação distinta e encerra processos. Excluir usuário encerra processos e mantém arquivos. | Decisão explícita do responsável em 22/11/2026. |
| U004 | Backup configurável na aplicação, desativado por padrão; administrador define frequência, destino e retenção por prazo ou substituição da cópia anterior. | Decisão explícita do responsável em 22/11/2026; destino do ensaio W004 ainda não selecionado. |

## Transições propostas

| Evento | Sessão web | PTY | Ambiente | Volume |
|---|---|---|---|---|
| Logout | Revogada imediatamente | Continua em execução e reconectável no próximo login | Continua em execução | Preservado |
| Revogação administrativa | Sessão indicada revogada imediatamente | Continua em execução e reconectável após novo login | Continua em execução | Preservado |
| Desativação | Todas revogadas; novo login negado | Encerrado por impossibilidade de retorno | Parado | Preservado |
| Revogação de permissão | Sessão mantida, autorização reavaliada | Fluxo afetado encerrado/negado na próxima ação | Conforme outras permissões | Preservado |
| Parada de sessão administrativa confirmada | Revogada | Encerrado, com processos cancelados | Parado | Preservado |
| Exclusão de conta confirmada | Todas revogadas; conta marcada como excluída | Encerrado, com processos cancelados | Parado | Preservado |
| Reinício/atualização | Revalidação de sessão | Reconexão depende de novo PTY | Recriado com a imagem pinada | Reanexado |

O gate W001 foi **aprovado tecnicamente** com o protótipo no daemon Docker Linux, referência remota confirmada, contratos v1, modelo de ameaça e políticas do responsável. A aprovação não afirma segurança contra escape, capacidade do host final nem aceite do produto; essas evidências continuam obrigatórias em W002–W004.
