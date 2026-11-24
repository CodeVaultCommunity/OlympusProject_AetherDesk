# Portão W006 — homologação local e aceite final

Plano `c1cf6012-e0a4-4f5a-a7fc-52a6ff0363fd` v5. Em 24/11/2026, **a execução técnica de I014 está concluída na fixture Docker local e o aceite final do responsável está pendente**. Não há promoção para produção. O candidate testado é o ZIP SHA-256 `9f6d75022c942993d9ff4d3a9543ffd1bc3230785389e51e4e2538a4f1514db2`, do commit `44b4152bf6547ace7ea192adf447383c279be067`, aprovado nos quatro jobs da [CI #3](https://github.com/CodeVaultCommunity/OlympusProject_AetherDesk/actions/runs/45408601796).

`homologation-W006.md` registra procedimentos, ambiente, amostras, resultados e limites. `traceability-W006.md` cobre individualmente R001–R028 e L001–L032. Capturas dos menus reais de aba e relatórios de zoom nativo ficam em `evidence-W006/`. Nenhum arquivo de aplicação foi alterado após gerar o ZIP; os scripts W006 ensaiam o mesmo candidate imutável.

| Eixo | Resultado técnico local |
|---|---|
| Backend, contratos e segurança funcional | 138 testes Python sobre módulos extraídos do ZIP, zero skips/falhas; fixture broker separada confirmou isolamento, revogação, quotas, auditoria/nonces e restart. |
| Bundle de produção | 59 E2E aprovados, um skip Chromium intencional com crash coberto na suíte anterior, zero falhas; Chromium, Firefox e WebKit. |
| D013 nativo/assistivo | Zoom nativo 99 amostras/3 motores/3 resoluções; duplicação pelo menu real Chromium e Firefox; WebKit minibrowser sem abas; crash real Firefox/WebKit; Orca/Firefox anunciou seis atalhos e controles, com abertura/fechamento por teclado. |
| Desempenho | 20 contas/8 simultâneos, 100/10.000 arquivos, 240 amostras de lista e leitura, 30 ecos PTY, 100 jobs únicos; percentis e limites no relatório. Sem SLO de host independente. |
| Recuperação | Migração e três cenários de snapshot/restore do ZIP aprovados; cada cenário sintético <60 s, sem perda dos dados modelados; chave incorreta rejeitada. Rollback de código via restauração de snapshot v1. |
| Supply chain | ZIP/SBOM do runner idênticos aos locais; zero críticos, zero altos corrigíveis e zero alto/crítico nos locks; 86 HIGH sem correção informada no Debian 13.8. |

## Decisão específica ainda necessária

O responsável já autorizou Docker local descartável e aceitou os 86 HIGH **somente para essa homologação com dados sintéticos**. Para fechar o portão W006, precisa decidir se aceita **este candidate como homologado tecnicamente apenas nesse perfil**, com estes limites explícitos:

1. Desempenho de login, arquivos, PTY e jobs medido na fixture; CPU de métricas, PTY através de WSS/browser, carga/soak prolongado e metas de build/deploy/Git/IA em servidor independente seguem sem aceite de capacidade. Nenhum SLO de produção é inferido.
2. Orca foi exercitado em Firefox; axe/teclado nos três motores. Duplicação nativa do menu não se aplica ao minibrowser WebKit do Playwright, que não possui abas. A sessão clonada foi verificada nele pela suíte W002.
3. Backup e restore de fixture não provam RPO/RTO em armazenamento real, off-host nem custódia externa da chave. O número de 60 s é apenas orçamento do cenário sintético.
4. As 86 HIGH residuais têm aceite restrito já dado. Distribuição/produção exigem re-scan, notices/licenças/marcas, host Linux independente, proxy/TLS/domínio/registry, backup/chaves e decisão de risco separados.

**Estado operacional até a resposta:** W006/I014 pronto para revisão; o índice WOP registra `execution_status=executed`, `acceptance_status=pending` e `plan_status=in_progress`, com referência a este relatório. Aceite local e publicação da branch não autorizam operação externa.
