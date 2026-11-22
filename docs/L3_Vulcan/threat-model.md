# Modelo de ameaça inicial — W001/I001

Ativos: arquivos e PTYs de cada conta; credenciais e sessões; banco de contas/permissões; socket do runtime; backups; dados de métricas. Agentes: membro malicioso autenticado, navegador comprometido, programa não confiável executado no terminal e administrador da aplicação. O administrador do host é autoridade externa ao produto.

| Ameaça | Fronteira | Controle exigido | Prova posterior |
|---|---|---|---|
| IDOR e troca de `account_id` | Navegador → API | Recurso pessoal derivado da sessão, autorização antes de efeito | Testes negativos API/WS com duas contas |
| Path traversal e symlink | API → namespace | Resolver dentro do ambiente, `openat2`/política equivalente, negar fuga por link; não usar concatenação de path do host | `../`, links e corridas de troca em Linux |
| Programa tenta ler outra conta | Contêiner → host/outro volume | Volume exclusivo, nenhum mount alheio, usuário não privilegiado, capabilities removidas, rede restrita | Bash e programa tentando caminho/volume de outra conta |
| Escape pelo daemon | Serviço/broker → Docker | Socket acessível só ao broker, allowlist de operações, imagem pinada, sem modo privilegiado | Inspeção de configuração e teste de negação |
| Revogação tardia | Evento → WS/PTy | Versão de permissão e sessão reavaliadas antes de cada ação; revogação fecha fluxo imediatamente | Revogar com conexão aberta |
| Backup expõe dados | Configuração → destino | Destino fora dos volumes, credencial segregada, proteção de acesso, manifesto e restauração verificada | Inspeção de permissões e ensaio de restore |
| Logs capturam conteúdo | Boundary → observabilidade | Evento administrativo só com ator/operação/alvo/hora/resultado; redação de erros | Revisão de logs com fixtures sensíveis |
| Consumo excessivo após logout | Ambiente persistente → host | Quotas por ambiente, limite de sessões/PTYs e monitoramento; administrador pode parar sessão | Teste de carga e parada explícita |

O protótipo de W001 prova separação básica de volumes e raiz, não prova todos esses controles. Qualquer fuga efetiva ou leitura cruzada bloqueia W002/W004 conforme o estágio.
