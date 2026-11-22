# Portão W001 — 22/11/2026

Item I001: **aceito tecnicamente**. O responsável definiu U003/U004 nesta conversa. Fonte remota identificada, 177 arquivos da edição Stable comparados sem diferença; protótipo Docker Linux passou para duas contas, raiz `/`, programa lendo `/dados.txt` e persistência após trocar a imagem. Evidências: `source-and-prototype.md`, `prototype/verify.ps1`, `architecture.md`, `contracts-v1.md`, `decision-record.md`, `threat-model.md`.

Critérios de passagem: contratos v1 de identidade, ambiente, arquivos, PTY, métricas, administração, auditoria e cliente web congelados; ownership dos módulos definido; matriz de permissão e transições registradas. W002 pode começar. Riscos residuais obrigatórios: isolamento por symlink e fuga, quotas, host Linux de homologação final, TLS, carga, backup/restauração e aceite funcional permanecem para W002–W004. A aprovação é do item técnico e do portão de onda, não do produto final.
