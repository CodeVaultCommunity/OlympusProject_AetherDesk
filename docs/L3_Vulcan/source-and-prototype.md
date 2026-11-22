# Fonte Vulcan e prova Linux — W001/I001

## Fonte inspecionada em 22/11/2026

- URL indicada no plano: `https://github.com/CodeVaultCommunity/OlympusProject_VulcanEcosystem`.
- `git ls-remote ... HEAD`: `4ab5824a7c7c962e96ac4480e8c254d023ba75df`.
- Clone raso dessa revisão em `.reference-vulcan/`; commit de 10/11/2026, assunto `First Commit`, árvore de trabalho limpa na inspeção.
- Edição mais alta presente: `versioning/Stable-v1.0.0`. SHA-256 de seu `README.md`: `272AF70253CD5CB5E878D007BC2AAC3826E2042ECF918A35544D1CEEC9FC02C1`.
- Os 177 arquivos dessa edição rastreados no clone remoto foram comparados por caminho e SHA-256 com a cópia local `E:\Alkimim\Projetos\CodeVault\OlympusProject\L3-VulcanEcosystem`; diferenças: **0**. Arquivos locais de ambiente virtual e cache ficaram fora da comparação.
- A revisão Git da cópia local é `43d660034eead80d80a606354c970902526c89ae`, com modificações e a edição Stable ainda não rastreada. A igualdade citada se limita aos 177 arquivos da edição Stable, não ao repositório local inteiro.
- O contrato formal da edição exige Minerva completo, `realization.json` e grafo de conhecimento. AetherDesk usa sua organização como adaptação e não declara conformidade formal.

## Protótipo executado

Ambiente: Docker Desktop 28.3.3, daemon Linux `amd64`, cgroups v2; imagens locais `alpine:3.20` (digest `d9e853e87e55...`) e `busybox:1.36.1` (digest `73aaf090f3d8...`). Comando de reprodução na raiz do projeto:

```powershell
& 'docs/L3_Vulcan/prototype/verify.ps1'
```

O script cria dois volumes exclusivos, prepara propriedade UID 10001, constrói duas imagens com `/dados.txt` apontando para um arquivo no volume, executa cada conta com rede desabilitada, raiz somente leitura, sem capacidades Linux, sem novos privilégios e com limites de processos, memória e CPU. Remove os volumes e imagens criados ao final. Não toca em volumes de terceiros.

Resultado observado em 22/11/2026:

```text
FASE 1: contas separadas na mesma imagem
alice pwd=/ arquivo=alice uid=10001
bob pwd=/ arquivo=bob uid=10001
FASE 2: reabertura preserva arquivos distintos
alice
bob
FASE 3: imagem base substituida, volume preservado
alice apos atualizacao=alice
bob apos atualizacao=bob
RESULTADO: PASSOU
```

Isto demonstra raiz `/` por contêiner, mesmo caminho com conteúdo distinto, leitura por programa (`awk`), reabertura e preservação na troca da imagem. Não demonstra ainda resistência a escape, symlink malicioso, concorrência, quotas reais, PTY ou permissões da API. Docker Desktop também não substitui o ensaio no servidor Linux alvo. Esses pontos permanecem para W002–W004; a seleção e o acesso ao host de homologação continuam pendentes.
