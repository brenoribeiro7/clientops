# ClientOps — arquitetura e operação

Especificação CL-00 com reconciliação da Foundation CL-01 em 30/09/2026. [DOMAIN](DOMAIN.md) governa invariantes, [SECURITY](SECURITY.md) governa controles, [API](API.md) governa HTTP. As partes comerciais continuam contratos futuros; a infraestrutura CL-01 descrita como implementada abaixo existe no repositório.

Project/repository root oficial: **/home/breno/Projects/clientops**. /home/breno/Projects é somente o diretório pai. Todos os caminhos relativos deste documento partem do root oficial; os nove documentos ficam em /home/breno/Projects/clientops/docs. Git não é inicializado em CL-00-FIX. Quando autorizado em CL-01, git init só poderá ocorrer dentro de /home/breno/Projects/clientops; é proibido inicializar o repositório no diretório pai. CL-01 não poderá prosseguir se o root real não puder ser estabelecido ou se Git/toolchain continuarem indisponíveis; preflight e evidência em PHASES.

## Contexto e containers

~~~mermaid
flowchart LR
 A[Admin desktop] --> W[Web React / TLS reverse proxy]
 T[Técnico smartphone] --> W
 C[Cliente sem conta /q] --> W
 W -->|/api/v1 mesma origem| F[FastAPI monólito modular]
 F --> P[(PostgreSQL)]
 F --> S[(Volume privado)]
 X[Scheduler externo simples] --> J[Management commands / mesma imagem API]
 J --> P
 J --> S
 A -.compartilha manualmente.-> C
~~~

Sem serviços externos obrigatórios. WhatsApp é destino de navegação voluntária para compartilhar texto; não integra a API. Uma instalação/um banco/um BusinessProfile. Produção pressupõe HTTPS e origem única. API e banco não são expostos diretamente à internet; somente o proxy recebe tráfego.

### Foundation CL-01 implementada

A composição atual contém `web`, `api`, `db` e `migrate`; `test` e `browser-test` existem somente no override de testes. O scheduler foi adiado para CL-05, quando haverá o primeiro job executável. A API roda como UID/GID 10001, o Nginx como 101, e apenas `127.0.0.1:8080` é publicado na composição base. Os volumes nomeados são `pg_data` e `private_files`; o web não monta arquivos privados.

As redes dedicadas são `edge` (`172.28.0.0/28`) e `backend` interna (`172.28.1.0/28`). O proxy ocupa `172.28.0.2` e a API confia exatamente em `172.28.0.2/32`; headers `X-Forwarded-*` de qualquer outro cliente são removidos antes de serem interpretados. A API usa uma conexão PostgreSQL runtime sem DDL, enquanto o serviço one-shot de migration recebe a credencial DDL separada.

O storage atual é um probe técnico do readiness: cria arquivo aleatório exclusivo com modo 0600 por `dirfd`, não segue symlink, confirma escrita/leitura, sincroniza e remove o arquivo. Ele não expõe upload, chave de negócio nem a interface FileStorage operacional prevista para CL-05.

## Runtimes e dependências

| Camada | Linha escolhida | Política |
|---|---|---|
| Python | CPython 3.13.x, GIL padrão | Mesma minor em dev, CI e Docker |
| Node | 24.x LTS; npm 11.x | Somente build/dev/test; sem Node no runtime da API |
| PostgreSQL | 17.x | Mesma major em todos os testes e deploy |
| Frontend | React 19.x, TypeScript 5.9.x, Vite 8.x, Tailwind 4.x, React Router 7.x em modo biblioteca/SPA | Sem SSR, framework full-stack ou RSC |
| Backend | FastAPI >=0.135.4,<1; Pydantic >=2.9,<3; SQLAlchemy >=2.0,<2.1; Alembic >=1.16,<2; psycopg >=3.2,<4 | ORM síncrono; endpoints de I/O síncronos no threadpool |
| Complementos backend | Uvicorn, pydantic-settings 2.x, argon2-cffi 25.x, email-validator 2.x, python-multipart; Pillow 12.x e fpdf2 2.x em CL-05 | Intervalos e transitivas resolvidos/lockados na fase de entrada |
| Complementos frontend | Primitives Radix 1.x via componentes shadcn selecionados; lucide-react; clsx/tailwind-merge; Sonner; TanStack Query 5.x | ClientOps controla wrappers; Query apenas no espaço autenticado |
| Testes/tooling | pytest, HTTPX, Ruff, mypy; Vitest 4.x, RTL, Playwright 1.x, axe-core, ESLint, Prettier, openapi-typescript | Versões exatas no lock; pypdf apenas teste de relatório |

CL-01 resolveu Python 3.13.15, uv 0.12.19, Node 24.21.0, npm 11.19.0 e PostgreSQL 17.6. `backend/uv.lock`, `frontend/package-lock.json` e `infra/images.env` congelam dependências e digests. Nada usa `latest`; dependências de fases futuras só entram quando usadas. As versões diretas resolvidas e os comandos de verificação estão em [TESTING](TESTING.md).

## Monorepo final

~~~text
docs/                 os nove contratos e documentação evolutiva
backend/
  app/
    main.py            composição FastAPI e dependências
    core/              config, db, clock, errors, security, logging, rate_limits
    modules/
      identity/        users, sessions, password flow
      business/        singleton e logo
      clients/         clients + equipment
      quotes/          items + snapshots + public access
      services/        OS + checklist + evidence + completion
      reports/         snapshot render e retries
      billing/         charge
      operations/      alerts, dashboard, consultas de agenda
      timeline/        append de eventos + leitura filtrada
    storage/           contrato FileStorage + filesystem adapter
    jobs/              evaluate_automations, generate_reports, maintenance
    cli/               create_admin, reset_password, seed_demo
  migrations/          Alembic; sem criação em CL-00
  tests/               unit, integration, api, security, migration
frontend/
  src/
    app/               router, providers, layouts admin/technician/public
    features/          auth, business, clients, quotes, services, billing, operations
    components/ui/     wrappers ClientOps e primitives selecionadas
    components/shared/ status, EmptyState, ErrorState, FormField
    lib/               api client, erros, datas, formatação
    contracts/         tipos de OpenAPI gerados; sem regras de negócio
    styles/            tokens e Tailwind
  tests/               componentes e fixtures
e2e/                   Playwright
infra/                 configuração proxy/container, posteriormente
.github/workflows/     somente a partir de CL-01
~~~

Em cada módulo backend: router, schemas, service, models e repository quando há queries próprias. Não exigir arquivos vazios nem uma interface por classe. Regras puras de dinheiro/estado podem viver em domain.py local. Router valida transporte/identidade e chama serviço; serviço autoriza objeto, obtém locks, valida regras, persiste e emite timeline; repository faz queries explícitas e nunca commit. SQLAlchemy Session é unidade de trabalho, sem framework genérico adicional.

Serviços recebem Clock, Session e FileStorage quando necessários, por dependências FastAPI ou construção explícita em CLI. Não importar HTTP no domínio, nem consultar storage por path fornecido pelo usuário. Não serializar models ORM diretamente. Módulos acessam comandos/queries explícitos dos demais, sem event bus; composição pode coordenar OS/report/alert/timeline na mesma transação.

Frontend: layouts distintos com lazy loading. Guards de rota melhoram UX, mas API decide permissão. Server state via Query no app privado; formulários usam estado React local. Fetch central trata CSRF, ETag, envelopes, AbortSignal e 401/403. Nenhum retry automático para mutações. Queries não fazem retry em 401/403/404. Página /q tem provider isolado, fetch próprio com credentials omit, bearer fora de Query/devtools/URL após leitura. Logout limpa caches de dados; nenhum dado privado vai a localStorage/IndexedDB/service worker.

O frontend público recebe apenas a projeção comercial autorizada, com client {name}, nunca o snapshot interno completo. O servidor seleciona CSP por documento/rota: /q mantém política estrita, independente de componentes privados. script-src 'unsafe-inline' é proibido em todas as experiências; qualquer necessidade mínima de style inline no app privado exige registro de componente/diretiva/rotas e verificação CL-01/CL-02 conforme SECURITY, sem relaxar headers globais ou /q. Web Share API é somente OPTIONAL/NON-BLOCKING no compartilhamento Admin, com fallback Copiar link; não exige serviço/dependência nova nem alteração do bearer.

## Persistência e transações

PostgreSQL READ COMMITTED. Uma transação por comando; timeline e mudança de domínio fazem commit juntos. Leituras não alteram estado comercial. Version integer em agregados mutáveis e If-Match previnem edição perdida. Transições usam SELECT FOR UPDATE na raiz, validam versão e estado sob lock e incrementam version uma vez. Toda mutação de filho da OS também bloqueia/incrementa a OS; idem QuoteItem com Quote. Sem bulk ORM que contorne essas regras.

Ordem de locks: usuário ator/usuário técnico necessário (UUID crescente), BusinessProfile quando usado, Client, Equipment, Quote, ServiceOrder, Charge, Report, Alert. Ler public access apenas para localizar Quote, depois lock Quote e reler access sob lock: aprovar/cancelar/rotacionar não invertem locks. Subtransações não fazem commit independente de efeitos comerciais. Desabilitar/resetar usuário bloqueia a mesma linha usada para autorização de comandos; comando que começou antes pode terminar antes da desabilitação, mas nenhum posterior ao commit pode ser autorizado.

Agenda serializa alterações por técnico bloqueando User, incluindo antigo/novo técnico em ordem. Detectar overlaps sob esses locks; overlaps continuam permitidos. Jobs travam a mesma raiz e reconciliam condição atual, não usam apenas um resultado antigo de SELECT. Nenhuma transação fica aberta durante upload/decode ou geração PDF.

| Operação | Unidade atômica |
|---|---|
| Send quote | Validar cadastro ativo, calcular itens, congelar snapshot, SENT, hash de bearer, timeline |
| Aprovar público | Lock Quote, validar bearer/estado/data, APPROVED/approved_at e um evento |
| Iniciar OS | Validar assignment/estado, congelar execution_snapshot, started_at, timeline |
| Concluir OS | Validar checklist/resolução, congelar report_snapshot, COMPLETED, criar ServiceReport PENDING, resolver alert, timeline |
| Registrar pagamento/cancelar | Charge + resolução de alerta + timeline |
| Falha PDF | Somente report status/attempt/retry; nunca desfazer OS |

Deadlock/serialization failures podem repetir internamente transação sem efeitos externos até duas vezes; se esgotar, 503 RETRYABLE_TRANSACTION. Bearer só é retornado após commit. Nenhuma dependência de exactly-once de rede; semânticas de repetição em API.

## FileStorage e histórico de arquivos

Contrato mínimo: put_new(stream, content_type) → key opaca, size e SHA-256; open_read(key) → stream; delete_unreferenced(key) para compensação/coleta. Escrita exclusiva, nome CSPRNG, fsync e rename atômico no mesmo filesystem antes de confirmar referência no banco. Chaves nunca são paths aceitos da API. Adapter normaliza/confina a chave ao root, recusa symlinks e não sobrescreve chave existente. Domínio conhece somente key e metadados.

Upload autentica/autoriza antes do corpo, valida e reencoda em staging privado; depois bloqueia OS e revalida permissão/estado/version/quota, persiste arquivo final e linha. Rollback remove arquivo se possível; se houver crash, maintenance elimina apenas órfãos com mais de 24h. Remover evidência antes da conclusão retira referência sob lock e programa/coleta arquivo; após conclusão é proibido. Logo substituída ganha nova key, e snapshots continuam referindo a key antiga.

Inventário de referências para coleta inclui profile, quote snapshots, execution/report snapshots, evidence e report. Conteúdo referenciado jamais é coletado. Backups combinam banco e volume em janela de manutenção com writes pausados; restore em ambiente isolado verifica hashes e integridade antes de servir. Backup diário, retenção inicial 7 diários/4 semanais, acesso restrito e criptografia no destino. Limite v1: um host; sem promessa de HA ou storage distribuído.

## PDF decidido

fpdf2 em worker CLI da mesma imagem backend. Renderer recebe somente ReportSnapshotV1, imagens reencodadas obtidas por FileStorage e fontes locais Noto Sans com licença incluída. A4, margens 15 mm, cabeçalho/rodapé, Unicode pt-BR, tabela/checklist com cabeçalho repetido, texto quebrável e evidências em páginas adicionais. Nada busca URL, interpreta HTML fornecido por usuário ou executa scripts. Render trata valores como texto. Glifos fora da fonte empacotada são representados visivelmente por [U+XXXX], sem remover o caractere do snapshot nem falhar permanentemente por entrada Unicode válida; pt-BR precisa renderizar integralmente sem substituição.

Comando generate_reports a cada minuto, separado das três automações comerciais. Advisory lock global de sessão exclusivo do comando limita a um renderer por instalação; concorrente sai sem erro e o próximo tick retoma. Tenta PENDING/FAILED elegíveis com advisory lock de sessão por report UUID, sem transação aberta durante render. Locks retidos na conexão até finalizar; crash libera. Retry HTTP tenta o mesmo lock por report sem esperar: se ocupado, retorna202 sem zerar contadores de tentativa em andamento. Após gravar novo arquivo, transação relê report e publica somente se não READY. Snapshot é aquele congelado na conclusão, incluindo logo/evidências; retry nunca relê cadastros. Primeiro sucesso fixa storage_key/hash/generated_at e torna documento imutável.

Falha persiste código sanitizado e incrementa attempts; intervalos após falhas 1–5: 1, 5, 30, 120, 360 minutos; após sexta falha, next_attempt_at nulo e retry manual Admin. Retry manual reinicia contador de ciclo, preserva total_attempts e snapshot. READY ignora retry e devolve referência atual. Limite por render 60 s/512 MiB em subprocesso; até um render simultâneo por instalação. CI validará 100 itens, 20 fotos e textos máximos, PDF até 30 MiB. Esses limites são gates futuros, não resultados medidos.

## Jobs e Docker

CL-01 implementa web (build frontend servido por proxy), api, db e migrate one-shot. A ordem é db saudável → migrate concluído → api pronta → web. Volumes `pg_data` e `private_files` são persistentes; web não monta `private_files`. TLS termina no proxy. A API usa uma réplica e um processo Uvicorn. O scheduler final continua parte da arquitetura, mas só será criado em CL-05 junto do primeiro job técnico executável; CL-01 não mantém processo inerte.

Objetivo futuro: docker compose up --build; provisionar segredos por arquivo externo/secret store antes. Inicializar Admin exige comando explícito com senha por TTY; startup nunca cria conta/senha default. Frontend só recebe configurações públicas. API não precisa de internet para executar atendimento.

evaluate_automations a cada 5 minutos; advisory lock global impede duas execuções simultâneas. Condições e unicidade estão em DOMAIN. Reprocessar todo conjunto elegível em lotes de 200, ordenado por PK e clock único do run; não filtrar apenas desde último run. Commit por raiz/alerta; falha sai nonzero e próxima execução recupera condições ainda verdadeiras. Sem mensagem automática nem BackgroundTasks scheduler.

maintenance diário: limpa sessões revogadas/expiradas há 30 dias, rate buckets vencidos há 24h e arquivos órfãos seguros. É higiene técnica, não quarta automação comercial. Log estruturado de início/fim/duração/contagens; última execução bem-sucedida exposta em log/monitoramento operacional, sem criar módulo de automações na UI. Aviso operacional se nenhum sucesso por 15 min. Backup e manutenção são invocações externas.

## Catálogo de configuração

R=required; O=optional com default; S=secret; P=pública. Validação de config falha no startup; nunca imprimir valores secretos. Produção rejeita debug, HTTP público, wildcard origins e segredos curtos.

| Variável | Classe | Contrato/default |
|---|---|---|
| APP_ENV | R/P | development, test, demo, production |
| DATABASE_URL | R/S | postgresql+psycopg; usuário runtime sem DDL |
| MIGRATION_DATABASE_URL | R/S em migrate | Credencial DDL só no job; separada do runtime |
| CSRF_HMAC_KEY | R/S | CSPRNG 32 bytes base64; não é secret de JWT |
| RATE_LIMIT_HMAC_KEY | R/S | CSPRNG 32 bytes; pseudonimiza IP/login |
| PUBLIC_BASE_URL | R/P | Origem HTTPS canônica, sem path/query/fragment |
| TRUSTED_ORIGINS | R/P | Lista exata scheme/host/port; produção origem canônica |
| TRUSTED_HOSTS | R/P | Hosts exatos; sem aceitar Host arbitrário |
| TRUSTED_PROXY_CIDRS | R | Somente IPs do proxy; X-Forwarded-* fora deles ignorado |
| PRIVATE_STORAGE_ROOT | R | Path absoluto privado, mesmo mount API/jobs |
| SESSION_IDLE_SECONDS | O | 1800; alteração exige revisar SECURITY/testes |
| SESSION_ABSOLUTE_SECONDS | O | 43200; idem |
| SESSION_TOUCH_SECONDS | O | 60; idem |
| QUOTE_TOKEN_TTL_SECONDS | O | 2592000 (30 dias); limite fixado nesta v1 |
| QUOTE_FOLLOWUP_HOURS | O | 72 |
| UPCOMING_SERVICE_HOURS | O | 24 |
| AUTOMATION_INTERVAL_MINUTES | O | 5; parâmetro scheduler, não por request |
| REPORT_INTERVAL_MINUTES | O | 1 |
| JOB_BATCH_SIZE | O | 200 |
| LOG_LEVEL | O | INFO; DEBUG vedado em produção |
| LOG_RETENTION_DAYS | O | 30 |
| VITE_API_BASE_PATH | O/P | /api/v1; nunca origin fornecida pelo usuário |

Cookie e limites de upload/rate são constantes versionadas do contrato, não opções livres por usuário. Sessões opacas dispensam chave global de assinatura: hash SHA-256 no banco; CSRF_HMAC_KEY tem finalidade distinta. Timezone e dados da empresa ficam em BusinessProfile, não em env; comandos capturam sua versão ao gerar snapshots. O singleton inicial tem trade_name, phone, email, address e timezone em NULL. Em CL-02, Admin preenche onboarding e escolhe explicitamente timezone IANA, sem valor pré-selecionado ou fallback de produção. is_complete é calculado pelo domínio sobre exatamente esses cinco campos válidos; logo é opcional. Send de Quote e start de OS exigem is_complete=true, sob lock, ou retornam BUSINESS_PROFILE_INCOMPLETE. Após completar, não permitir limpar campos essenciais; timezone escolhida só muda para outra válida. America/Bahia fica exclusivamente no seed Climatech/fixtures específicas. Sem timezone, regras civis aguardam configuração conforme DOMAIN/API; health/login e onboarding continuam disponíveis.

Schema inicial CL-01: metadados Alembic (`alembic_version`), revisão vazia `0001_foundation`, conexão e readiness; nenhuma tabela de domínio foi antecipada. `alembic check` não detectou drift. CL-02 acrescentará business_profiles, users, sessions, rate_limit_buckets e timeline_events; demais tabelas entram nas fases respectivas.

### Operação de credenciais locais

As senhas PostgreSQL do bootstrap são aplicadas apenas quando `pg_data` é inicializado. Regenerar `.local/compose.env` com `infra/dev-env.py --force` e manter um volume existente não altera as roles dentro do banco e causa incompatibilidade. Rotação futura deve atualizar banco e configuração de forma coordenada. Remover `pg_data` é aceitável somente em ambiente descartável sem dados relevantes; recriar containers com `docker compose down` preserva ambos os volumes.
