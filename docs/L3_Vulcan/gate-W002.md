# Portão W002 — 22/11/2026

**I002 aceito:** identidade com migração `001_initial.sql`, Argon2id, bootstrap único, sessões, papéis, permissões individuais, exclusão lógica, outbox de eventos, auditoria e Boundary HTTP com cookies e CSRF. Cinco testes de identidade/HTTP passaram em `uv run python -m unittest ...`; incluem senha não legível, ID/ambiente estáveis após renomear, revogação efetiva, negação por outra conta e mutação negada sem CSRF.

**I003 aceito:** imagem Debian com Bash, usuário 10001, volume persistente por ID, raiz somente leitura, sem rede/capabilities e limites de recursos. Teste Docker Linux confirmou dois ambientes separados, um contêiner sob chamadas concorrentes, `cd /`, `/dados.txt`, processo persistente após reabertura, parada que encerra processo e dados que sobrevivem à recriação. `AppComposition` processa desativação/exclusão sem remover volume.

**I004 aceito:** shell React/TypeScript com login, área de trabalho, lançadores, gerenciador de janelas, barra de tarefas, estados de sincronização e contrato de persistência. `pnpm build` passou. Inspeção no navegador local em modo fixture confirmou abrir, minimizar, maximizar, mover, redimensionar, alternar pelo taskbar e restaurar janela e posição após recarga; login foi inspecionado sem fixture. Capturas constam do registro de inspeção desta execução. O modo fixture só existe em desenvolvimento.

**Integração:** `AppComposition` ligou identidade e runtime; o teste integrado demonstrou que logout e revogação preservam o processo, parada encerra processo e revoga autenticação, exclusão remove contêiner e mantém volume. A suíte combinada passou: 7 testes em 35 s. `pyproject.toml`/`uv.lock` e `web/pnpm-lock.yaml` fixam dependências; `launch.py` registra a aplicação e a Boundary de identidade. Interfaces de W001 foram mantidas.

**Portão:** W002 passou tecnicamente. Riscos destinados a W003/W004: APIs de arquivos/PTy/métricas/desktop/backup ainda não existem; HTTPS, instalação Linux final, testes negativos de symlink e carga permanecem obrigatórios. Nenhum desses módulos posteriores foi aceito por este portão.
