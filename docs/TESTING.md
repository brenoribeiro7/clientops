# ClientOps — testes e CI

Gates orientados a riscos: autorização, histórico, valores e transições corretas; porcentagem de coverage não substitui esses critérios. **Nenhum teste do produto foi executado em CL-00:** esse registro continua histórico. As seções de evidência registram CL-01 e o subconjunto de identidade/configuração CL-02; os domínios comerciais posteriores continuam futuros.

## Camadas

| Camada | Ferramentas/ambiente | Prova necessária |
|---|---|---|
| Domain/unit | pytest + funções puras/Clock falso | Estados, dinheiro, datas, condições e snapshots |
| Repository/integration | pytest + PostgreSQL17 real | CHECK/FK/unique, queries scoped, rollback/locks |
| API integration | HTTPX ASGI + DB real | JSON/status/headers/ETag e projeções |
| Auth/security | API + browser real onde necessário | Cookie, CSRF/CORS, forced-change, bearer, acesso por objeto |
| React component | Vitest/RTL/user-event; MSW só transporte | Ações, erros, foco, todos estados UI |
| E2E | Playwright + app/DB/volume reais | Hero Flow e fronteiras de persona |
| Migration | Alembic + DB vazio/anterior | Upgrade, drift, constraints e preservação |
| Smoke/operacional | Compose + browsers/restore | Saúde, restart, jobs, persistência e headers |

Não usar SQLite para integração/API. Cada worker pytest ganha database clientops_test_<run>_<worker> isolado, role sem acesso a produção. Aplicar migrations uma vez por database. Casos simples usam rollback; casos concorrentes/API com commit limpam tabelas entre casos no banco dedicado. Não compartilhar transação externa entre conexões de teste concorrente. Storage é TemporaryDirectory por caso.

Concorrência exige duas conexões/processos e barreiras/eventos, sem sleep arbitrário; execução serial não prova race safety. E2E usa DB/volume por worker ou execução serial com seed/reset via CLI de teste, nunca endpoint HTTP reset/clock em produção. Fixtures sintéticas, IDs isolados e bearers gerados no teste.

FakeClock fixo/avançável, capturado uma vez por comando/job, cobre igualdade no limite. Backend E2E pode receber clock fixo só APP_ENV=test pelo harness; produção rejeita essa configuração. Frontend usa server_now para regra e clock Playwright para timers. SO/locale do runner não determinam business_today.

Toda execução futura parte de /home/breno/Projects/clientops. Preflight deve verificar root real e Git/toolchain antes de CL-01; se ausentes, parar, sem inicializar Git no pai /home/breno/Projects. Este CL-00-FIX apenas verifica documentos e paths; não instala ferramentas nem executa testes de runtime.

## Matriz crítica

IDs referenciam SECURITY/PHASES. Cada ID inclui exemplos parametrizados e asserções de resultado/ausência de efeito.

| ID | Cenário e resultado exigido |
|---|---|
| DOM-01 | Todas transições Quote legais/ilegais; terminais; SENT imutável; EXPIRED derivado; sem REJECTED |
| DOM-02 | Todas transições OS e cancelamentos permitidos; sem reabertura/retorno |
| DOM-03 | Required pendente impede complete; opcional/vazio permite; resolução obrigatória CONFIRMED/NOT_AVAILABLE |
| DOM-04 | Estrutura checklist congela no start; respostas só IN_PROGRESS; terminais bloqueiam filhos |
| DOM-05 | Decimal, 0.005×1.00→0.01, soma arredondada por linha, zero quote, overflow/scale/floats/exponent/NaN |
| DOM-06 | Valid/due hoje não vence, ontem vence; midnight local/UTC, timezone alterado e DST |
| DOM-07 | Overlap parcial/total/contido, adjacency sem conflito, outro técnico/terminal excluído; warning salva |
| DOM-08 | Charge só COMPLETED, uniqueOS, terminais/overdue/sem parcial |
| DOM-09 | Archive preserva histórico, impede nova seleção/send, permite execução existente; FKs de ownership |
| DOM-10 | Quote→OS única inclusive cancelada; duplicate DRAFT sem snapshot/access/approval |
| BP-01 | Singleton initial com trade_name/phone/email/address/timezone NULL; nenhum empty sentinel/default; PATCH parcial/null/whitespace coerente; is_complete false até cada um dos cinco campos válido; logo não obrigatório; is_complete/missing_fields não graváveis |
| BP-02 | Timezone escolhida explicitamente/IANA; rejeitar inválida; não inferir host/browser/env; primeira escolha sem acknowledge, troca válida com acknowledge; proibir limpar timezone configurada ou regredir profile completo |
| BP-03 | Cada campo essencial faltante bloqueia send/start409 sem snapshot/token/evento/transição; login/conta/profile/cadastro/health funcionam; sem timezone, operação civil409 e metadados opcionais null; FakeClock em fusos explícitos sem default de produção |
| AUTH-01 | Login válido sessão nova/hash; inválido/inexistente genérico/dummy |
| AUTH-02 | DISABLED não loga, revoga sessões; enable não revive |
| AUTH-03 | Logout revoga/limpa cookie; repetição sem sessão204/origem válida |
| AUTH-04 | Idle30min/absolute12h nos limites; touch60s monotônico; polling não renova; máximo5 sessões |
| AUTH-05 | Expired/revoked negam GET/mutation/stream; fixation/touch não ressuscitam |
| AUTH-06 | Reset revoga todas; temporária24h; entrega one-time/no-store; disabled permanece |
| AUTH-07 | Troca exige senha atual/política/CSRF, revoga demais e emite nova; rehash |
| AUTH-08 | must_change_password só session/change/logout; todos módulos/arquivos negados; troca limpa flag |
| AZ-01 | Técnico não lista/abre OS alheia nem amplia por filtro; objeto inacessível404 |
| AZ-02 | Evidência GET/HEAD de outra OS negada; report negado; reatribuição remove acesso |
| AZ-03 | Técnico sem quotes/charges/dashboard/users/profile; role/owner overposting negado |
| AZ-04 | Anônimo privado401; público bearer não autentica privado; cookie não autentica público |
| AZ-05 | DTO/timeline/erro técnico sem email/client.notes/quote value/charge/keys |
| AZ-06 | Admin opera OS atribuída com ator correto; disabled não executa; último Admin protegido |
| PUB-01 | Bearer válido lê snapshot/logo/aprova; GET sem estado/evento viewed |
| PUB-02 | Ausente/malformado/desconhecido mesma401; query não aceita bearer |
| PUB-03 | Expirado/revogado401; rotação invalida anterior; TTL independente da validade comercial |
| PUB-04 | Cancelado revoga/401; comercial expirado com bearer válido GET200/approve409 |
| PUB-05 | APPROVED legível; repeat200 timestamp idêntico/um evento; token inválido prevalece |
| PUB-06 | approve/approve, approve/cancel e rotate races: um resultado serializado válido |
| PUB-07 | Resposta send perdida: SENT, segredo irrecuperável, rotate sem novo snapshot |
| PUB-08 | Fragmento limpo; token ausente URL/log/referrer/telemetry/cache/storage; WhatsApp query sem segredo; reload orienta reabrir |
| PUB-09 | Snapshot interno preenchido com ID/phone/email/address e Client.notes canários; DTO público tem exatamente client {name} e NÃO contém client.phone, client.email, client.address, client.id, client.notes, inclusive null; sem cópia em snapshot/HTML/estado/erro; contatos business preservados; repetir em SENT/APPROVED e contexto anônimo de link encaminhado |
| HIS-01 | Alterar Client/Business após SENT não muda snapshot/valores/logo |
| HIS-02 | Alterar Client/Equipment/User após start não muda execution; Business/logo após complete não muda report, mesmo render atrasado |
| HIS-03 | Fotos/checklist/notes/confirmation terminais imutáveis por todos endpoints |
| HIS-04 | Timeline append-only e rollback junto à mudança; payloads sanitizados |
| UP-01 | JPEG/PNG/WebP válidos → JPEG, orientação, alpha branco, dimensões/hash corretos |
| UP-02 | Extensão falsa, MIME/magic mismatch, SVG/GIF/HEIC/arquivo truncado rejeitados |
| UP-03 | Limite bytes exato/+1, multipart/chunked excessivo, quota20 concorrente |
| UP-04 | Lado/pixels no limite/acima, bomb e animação/APNG/WebP |
| UP-05 | EXIF/GPS/ICC/XMP/comments removidos; original ausente; output limitado |
| UP-06 | Upload/stream unauthorized; /uploads negado; estado/version revalidado após decode |
| UP-07 | Filename traversal, key falsa, symlink/path absoluto nunca lidos; erro sem path |
| UP-08 | Rollback/crash e coleta de órfão somente24h; referência histórica retida |
| UP-09 | Deadline/memória/decode simultâneo/disconnect não deixam recursos sem limite |
| UP-10 | Logo limites distintos, logo antiga retida e acesso público por bearer correto |
| UP-11 | iPhone físico/Safari suportado: câmera e biblioteca passam pelo input web→upload ServiceEvidence→conclusão do Hero; registrar MIME/formato efetivos e versões; gate real CL-05/CL-06 detalhado abaixo, sem presumir formato |
| AUT-01 | Mesmo job duas vezes/duas instâncias não duplicam linha/evento |
| AUT-02 | Intervalo perdido recupera SENT antigo, SCHEDULED atrasada e charge vencida |
| AUT-03 | Ação resolve condição+alert atomicamente; job false resolve residual |
| AUT-04 | Reagendar além janela resolve; aproximar reativa mesma linha; sem snooze |
| AUT-05 | Não fabricar alerta retroativo para condição já falsa; 72h/24h boundaries |
| AUT-06 | Timezone NULL no onboarding: automations faz no-op CONFIGURATION_REQUIRED sem criar/resolver alert; após escolha explícita reavalia normalmente, sem timezone fallback |
| REP-01 | Complete cria snapshot/PENDING atomicamente; erro PDF não desfaz COMPLETED |
| REP-02 | Retry mantém snapshot apesar de cadastros alterados; READY nunca regenera |
| REP-03 | Dois jobs/retry/crash publicam um PDF; backoff/deadline/retry manual/hash |
| REP-04 | READY ausente/corrompido gera incidente; restore recupera bytes sem re-render |
| REP-05 | pt-BR integral, glifo fora da fonte representado por código Unicode sem alterar snapshot, logo, 0/20 fotos,100 checklist, texto máximo, multipágina e limite30MiB |
| CON-01 | Dois PATCH mesma tag: um200/outro412, sem lost update |
| CON-02 | Sem tag428; estado ilegal409 com tag atual; repetições conforme API |
| CON-03 | Complete vs uncheck/upload/reassignment serializa sob lockOS |
| CON-04 | Job versus raiz: não deixa ACTIVE falso após comando |
| CON-05 | Duas charges/conversões quote: unique409; ownership mismatch FK |
| CON-06 | Reset/disable vs login/mutação/touch não permite sessão após commit revogador |
| CON-07 | Deadlock/retry/rollback não duplicam timeline/files/bearer |
| SEC-01 | CSRF todo unsafe/multipart, Origin/Referer missing/null/malicioso, loginCSRF/CORS/trusted proxy |
| SEC-02 | XSS em texto/caption, CSP, PDF sem fetch externo/HTML/SSRF |
| SEC-03 | Canary secrets em erro/login/reset/public/upload ausentes de logs/timeline/fields |
| SEC-04 | Limits porIP/login/bearer/user/global em múltiplos workers, janelas, fail-closed/Retry-After |
| SEC-05 | CL-01/CL-02: headers efetivos /q estritos em navegação/deep-link/fallback, sem herdar CSP privada; script-src sem unsafe-inline em todas rotas; eventual style inline privado mínimo documentado/testado, sem ampliar política global |
| API-01 | Envelope/status/headers/casing/datas/Decimal/DTO por papel |
| API-02 | Paginação/filter/sort/search literal, desempate e interseção agenda |
| API-03 | extra fields/mass assignment, null vs omissão, quotas/size/erros sem input |
| API-04 | OS COMPLETED com report READY e sem Charge não cria attention/alert/dívida nem altera pending_charges/overdue_charges; completed_today conta serviço; ação contextual permite criar cobrança, que então aparece em lista/indicadores |
| UI-01 | Todos normal/loading/empty/error/disabled/success de UI_UX |
| UI-02 | Keyboard/focus/dialog/labels/contrast/status/touch/reflow; axe+manual,4 viewports |
| UI-03 | Double-click/network/412 sem success falso, dados locais preservados, caches limpos |
| UI-04 | Somente se Web Share opcional for implementado: disponível/indisponível/cancelado/falha; gesto e link correto com fragmento, sem query/token logs; Copiar link sempre funcional, nenhuma alegação de entrega |
| OPS-01 | Compose cold start/migrate/health/scheduler/restart com DB/files preservados |
| OPS-02 | Backup/restore verifica hashes e histórico; secrets fora de artifacts |

## E2E bloqueador

Fixtures: Climatech com os cinco campos BusinessProfile completos e timezone America/Bahia configurada explicitamente só para esta demonstração/teste, Ana Admin, Marcos/Lucas técnicos, senha fornecida ao harness, cliente novo, JPEG sintético. Fixture de onboarding separada começa com cinco NULL, sem timezone pré-selecionada; não reutilizar seed completo para ocultar BP-01..03. Contextos browser independentes; sem mockar API/banco/bearer/upload/PDF.

1. Admin login → cliente/equipamento opcional → quote DRAFT com itens → send, link capturado só em memória.
2. Contexto CUSTOMER abre link, verifica fragmento limpo/snapshot/valores, aprova; Admin vê APPROVED.
3. Admin cria OS vinculada e agenda Marcos; checklist required. Cenário específico verifica overlap.
4. Técnico390px login/troca obrigatória se necessária → própria OS → start → checklist → foto → observação → confirmação.
5. Complete → COMPLETED/PENDING; harness invoca o mesmo comando CLI report ou aguarda scheduler com timeout controlado.
6. Admin vê READY, baixa PDF; pypdf em teste extrai texto/acentos/número/checklist, hash do download confere.
7. CL-06 estende charge PENDING vencida → job → alerta ACTIVE → mark-paid → RESOLVED/dashboard.

Pode haver cenários menores isolados, mas um final conecta passos1–6. Variantes NOT_AVAILABLE, falha/retry PDF, segundo técnico sem acesso e aprovação repetida são obrigatórias. Screenshots/video/trace só sintéticos; desabilitar captura de headers/bodies secretos ou sanitizar antes de publicar. Artifact com token/senha/cookie não é publicado.

## Gate de foto real iOS — UP-11 (CL-05 e CL-06)

Executar em iPhone físico com iOS/Safari dentro da support matrix, usando build servido como na produção e dados de demonstração. Não substituir por Playwright WebKit, viewport emulado, arquivo JPEG injetado ou conversão manual prévia. CL-05 fornece primeira evidência funcional; CL-06 repete no candidato a release e registra cobertura das versões Safari/iOS declaradas.

1. No input web real da tela de ServiceEvidence, capturar uma foto pela câmera de objeto/cenário sem dados pessoais.
2. No mesmo fluxo da aplicação, selecionar também uma foto da biblioteca. Ambos os caminhos precisam ser exercitados, sem presumir que fornecem o mesmo formato.
3. Registrar em evidência de teste, para cada origem: modelo do iPhone, versões iOS/Safari, build, modo de aquisição, File.type fornecido pelo browser, Content-Type efetivo da parte multipart, extensão, tamanho/dimensões e formato identificado por magic bytes/decoder. Se MIME vier vazio, registrar isso; não inferi-lo pela extensão. Não guardar EXIF/GPS/credencial ou foto pessoal no relatório.
4. Enviar cada imagem pelo input da aplicação e confirmar resposta de upload, criação de ServiceEvidence e imagem sanitizada legível. Percorrer checklist/observações/resolução e concluir o Hero Flow, com relatório disponível ao Admin; podem ser dois cenários isolados ou uma OS com as duas evidências.
5. Registrar PASS/FAIL separadamente para câmera e biblioteca. Não declarar antecipadamente que Safari converterá ou fornecerá JPEG, HEIC ou qualquer outro formato.

Se dispositivo/browser suportado entregar HEIC e o fluxo falhar, o resultado é **finding bloqueador antes da release**. Exige decisão explícita: **A)** suporte seguro a HEIC (pipeline/limites/dependências/testes revisados e autorizados), ou **B)** revisão explícita da support matrix e dos compromissos de produto. Nenhuma alternativa é aplicada silenciosamente nesta correção; HEIC segue fora do escopo atual. Reexecutar UP-11 após a decisão. Sem dispositivo/evidência real, gate permanece não executado e não pode ser marcado PASS. Web Share não é dependência desse gate.

## Migration gate

PostgreSQL17 vazio → alembic upgrade head → todas revisions → constraints/índices esperados → alembic check sem drift. CL-01 revisão vazia revisada é válida como foundation; CL-02+ models/tabelas reais. Autogenerate sempre revisado. CHECKs, índices parciais e data migrations têm assertions específicas, pois drift não detecta tudo.

Cada migration faz upgrade do vazio e do schema anterior com dados representativos. Downgrade só quando declarado seguro; release usa backup/forward fix, sem downgrade destrutivo automático. create_all não substitui migrations em API/E2E.

## CI final e progressão

~~~mermaid
flowchart TD
 C[Checkout e locks] --> L[Lint e format]
 C --> T[Typecheck Python e TS]
 C --> U[Unit backend e componentes]
 C --> M[PostgreSQL vazio + migrate + drift]
 M --> I[Repository + API + security]
 L --> B[Build frontend e imagens]
 T --> B
 U --> E[E2E Chromium / Firefox / WebKit]
 I --> E
 B --> E
 E --> S[Compose smoke e artifacts audit]
~~~

GitHub Actions contents:read por padrão, actions por SHA/imagens por digest; PR sem secrets produção/deploy, inclusive forks. Locks frozen, cache só dependências; timeouts e bancos isolados. Não esconder checks por path filtering que ignore migrações/segurança. Sem continue-on-error em gate obrigatório.

| Fase | Gates novos | Evidência |
|---|---|---|
| CL-01 | Preflight root/Git/toolchain; Ruff/ESLint/format, mypy/tsc, unit/component smoke base, build, migrate-empty/drift, health/Compose, SEC-05 foundation | Logs reais e locks/versões; headers CSP por rota |
| CL-02 | AUTH/AZ base/CSRF/profile/users, BP-01/02 e BP-03 no domínio/rotas existentes, SEC-05 e login/troca/logout/onboarding Playwright | DB/browser/cookie sanitizados; CSP privada/pública; BP-03/send e start completados em CL-04/05 |
| CL-03 | Client/Equipment API/domain/UI, archive e ownership | Migration e fixtures cruzadas |
| CL-04 | Quote/money/PUB-01..09/HIS-01/concurrency/E2E aprovação; UI-04 só se opcional implementado | Snapshot, DTO público mínimo, rede/log leakage |
| CL-05 | OS/agenda/checklist/upload/report, CON-03, Hero1–6 e UP-11 real iPhone | PDF/hash/texto, mobile/retry; câmera/biblioteca e MIME/formato reais |
| CL-06 | Charge/AUT-01..06/API-04/dashboard/timeline, fullE2E3 engines/security/restore; repetir UP-11 real | Demo/release audit e prova de foto no iPhone/Safari suportado |

Gates anteriores continuam executando. Fluxos críticos em3 engines conforme entram; UI4 viewports, Hero técnico390/Admin1440. Safari real/iOS e Android Chrome recebem smoke manual no release; Playwright WebKit não substitui esses ambientes. UP-11 é gate manual explícito CL-05/CL-06 com evidência real vinculada à fase/release, além do CI automatizado. Nenhum teste de Web Share é exigido se a melhoria opcional não for implementada.

Evidência deve registrar comando/job, versões/env, clock/fixtures e resultado passed/failed; “planejado” nunca é PASS de runtime. Release exige zero falhas críticas e Hero/segurança/histórico comprovados. Coverage auxilia identificação de lacunas; flaky exige causa corrigida.

## Evidência CL-01 — 30/09/2026

Toolchain local: Python 3.13.15, uv 0.12.19, Node 24.21.0, npm 11.19.0, Docker 29.1.3 e Compose 2.40.3. Os locks foram conferidos com `uv lock --check`, `uv sync --locked` e `npm ci`. SHA-256: `uv.lock` = `95dea2545c85cc97e054214634dfa596b6c92835f4e34ba5b9b126697484fe8c`; `package-lock.json` = `43b44efa5008ecaf9942993d85c0f7e401d406a7d49ece2a4c9621e691fd3341`.

Dependências backend diretas: Alembic 1.20.0, FastAPI 0.141.1, psycopg 3.3.6, Pydantic 2.13.5, pydantic-settings 2.15.0, SQLAlchemy 2.0.54 e Uvicorn 0.54.0. Ferramentas backend: HTTPX 0.28.1, mypy 2.3.1, pytest 9.1.1, pytest-cov 7.1.0 e Ruff 0.16.9. Dependências frontend diretas: React/React DOM 19.3.0, React Router 7.18.4, TypeScript 5.9.3, Vite 8.3.1, Tailwind 4.3.3, Vitest 4.1.11, Playwright 1.63.0, openapi-typescript 7.13.0, lucide-react 1.48.0, clsx 2.1.1 e tailwind-merge 3.7.0.

Imagens fixadas em `infra/images.env`: Python `sha256:2325bb286ec344af3e5898cc224b5844e2707ac6e26b1632516fd3edc84a5e26`; uv `sha256:04d046b13e60d6bcec73cbc5e1cad25d680dea90c8573340950a0ac2d1aef424`; Node `sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6`; PostgreSQL `sha256:f3bd19c606e442c3d7bdfa8002e03fe260a1023351e0ea4598032022b68dd6e3`; Nginx `sha256:ce2bd4775ed6859d35f47d65401ee9f35f1dd00b32ed05f0ce38b68aa1830195`; Playwright `sha256:eff16c30e6f3f4af0a03fa4b706120d5e9b0891c344a27d64559aff5900a4a27`.

Comandos locais de qualidade são os documentados no README. PostgreSQL real usa `docker compose ... run --rm test pytest -m postgres`; os testes Compose/artefatos usam `uv run --locked pytest -m "compose or artifacts"`. A matriz browser roda dentro da imagem Playwright fixada com `docker compose ... run --rm browser-test`; a prova TLS usa a mesma imagem contra `https://web:8443`.

| ID | Estado local | Evidência CL-01 |
|---|---|---|
| T01 | PASS | Versões aprovadas, `uv lock --check`, `uv sync --locked`, `npm ci`, dois locks sem alteração |
| T02 | PASS | pytest `test_config.py`: validação fail-fast e valores secretos sanitizados |
| T03 | PASS | pytest `test_clock.py`: UTC/FakeClock determinísticos |
| T04 | PASS | pytest `test_errors.py`: envelopes 404/422/500 sem detalhes internos |
| T05 | PASS | pytest `test_request_logging.py`: UUID, logs allowlist e proxy confiável/não confiável |
| T06 | PASS | pytest health e queda real do PostgreSQL: live continua 200 |
| T07 | PASS | PostgreSQL 17 + revisão exata + volume: ready 200 mínimo |
| T08 | PASS | `test_compose_lifecycle.py`: DB parado produz ready 503 sanitizado/live 200 e recupera ready 200 sem restart da API |
| T09 | PASS | `test_migrations.py`: revisão stale produz 503 e revisão correta recupera 200 |
| T10 | PASS | `test_storage_health.py` + container UID 10001: permissões, symlink, limpeza e probe real |
| T11 | PASS | PostgreSQL 17 vazio: somente `alembic_version=0001_foundation`; upgrade/check sem drift |
| T12 | PASS | role runtime lê revisão e recebe erro ao tentar DDL |
| T13 | PASS | dois processos Alembic concorrentes terminam 0 e mantêm a revisão exata |
| T14 | PASS | 7 testes Vitest/RTL + Playwright nas quatro larguras: três shells sem conteúdo comercial |
| T15 | PASS | Playwright/Nginx: rotas, deep links, 404; API/assets não usam fallback SPA |
| T16 | PASS | RTL/user-event + Playwright/axe: teclado, foco, Drawer, landmarks, reflow, zero serious/critical |
| T17 | PASS | Playwright nos três engines: CSP real em `/q`, `/login`, `/admin/*`, `/tech/*`; inline bloqueado |
| T18 | PASS | HTTP e HTTPS reais: cache/headers corretos; HSTS somente em HTTPS |
| T19 | PASS | ESLint, Prettier, TypeScript, Vitest e Vite build concluídos com exit 0 |
| T20 | PASS | export OpenAPI determinístico, `openapi-typescript --check` e cópia stale rejeitada |
| T21 | PASS | cold start db→migrate→api→web e ciclo real de falha/recuperação; migration precede API |
| T22 | PASS | containers removidos sem volumes: revisão e marcador 0600 persistiram; marcador de teste removido |
| T23 | PASS | scans do bundle, histórico de imagens e logs não encontraram os segredos sentinela |
| T24 | PASS | inspeção Compose: só web publicado; DB/API privados; web sem `private_files`; ready interno |

A execução browser completa registrou 87 PASS e 3 skips. Os skips são o teste `Drawer administrativo restaura foco` em Chromium 1024, Chromium 1440 e Firefox 1440: nesses viewports a sidebar substitui o Drawer. Cobertura equivalente passa em Chromium 390, Chromium 768 e WebKit 390; nenhum job ou engine foi pulado. O subconjunto SEC-05 em HTTPS registrou mais 6 PASS.

O workflow GitHub Actions está implementado e tem teste estático para SHAs, padrões proibidos e resultados do gate. Como evidência histórica anterior à integração, o repositório público `brenoribeiro7/clientops` teve `main` em `84f7c4aa5af9dc292b109cf6602d3dd302ac870e` quando publicou `feat/cl-01-foundation`; o SHA pré-correção documental `6776fa2464cb09d66b318d103e85e74ec48f094e` recebeu o run real histórico `36732984184`, conclusão `success`, com `backend-quality`, `frontend-quality`, `database-migration`, `contract-drift`, `compose-smoke`, `security-foundation` e `cl01-gate` em `success`. O estado integrado da CL-01 é o PR `#1` merged e `main` em `2bc0ef608d97536ead0007b528507b1b770cb319`. IDs e SHAs posteriores permanecem no relatório externo de cada execução para evitar loop de commits.

O incidente local de `dev-env.py --force` confirmou que credenciais regeneradas não atualizam roles de um `pg_data` já inicializado. Rotação exige procedimento coordenado; apagar volume só é permitido em ambiente descartável.

## Evidência local CL-02 — 01/10/2026

Execuções locais após a continuação: 50 testes pytest sem PostgreSQL, 34 testes PostgreSQL reais, 8 testes Compose/artefatos e 9 testes Vitest passaram. A matriz HTTP Playwright executou 108 casos em Chromium 390/768/1024/1440, Firefox 1440 e WebKit 390: 100 pass e 8 skips deliberados (Drawer desktop e o caso de segurança compartilhado executado uma vez em Chromium 390). O fluxo HTTPS production-like adicionou 9 pass em Chromium 390, incluindo cookie `__Host-` Secure/HttpOnly/Lax. Os casos usam API, Nginx, PostgreSQL, cookie e CSRF reais, sem mock do fluxo E2E. GitHub Actions no SHA final ainda não foi executado neste checkpoint documental.

| Família | Casos CL-02 | Resultado | Restante adiado |
|---|---|---|---|
| AUTH-01..08 | login uniforme, temporary/forced change, cap/boundaries/touch, revoke/reset/logout/cookie | PASS — CL-02 COMPLETE | — |
| BP-01/BP-02 | singleton NULL, parcial/completo, timezone/today, acknowledge, não regressão | PASS — CL-02 COMPLETE | — |
| BP-03 | auth/profile/conta sem completude e tempo civil sem fallback | PASS — CL-02 APPLICABLE SUBSET | send CL-04; start CL-05 |
| AZ-01..06 | deny-by-default, papéis fixos, self/último Admin e User/Profile Admin-only | PASS — CL-02 APPLICABLE SUBSET | objetos Client/Quote CL-03/04; OS/arquivos CL-05; Charge CL-06 |
| SEC-01 | Origin/Referer/login-CSRF/CSRF em mutations CL-02 | PASS — CL-02 APPLICABLE SUBSET | multipart CL-05; público CL-04 |
| SEC-03 | bearer/senha/hash ausentes de respostas, timeline e logs CL-02 | PASS — CL-02 APPLICABLE SUBSET | canários de domínios futuros nas fases respectivas |
| SEC-04 | login IP/e-mail/instalação, reset/Admin e private/User; HMAC/concorrência/Retry-After | PASS — CL-02 APPLICABLE SUBSET | bearer público CL-04; upload CL-05 |
| SEC-05 | CSP/headers/deep links privados e `/q` isolado | PASS — CL-02 APPLICABLE SUBSET | integração pública Quote CL-04 |
| CON-01/06/07 | profile PATCH, sixth login, last Admin, login×disable/reset, password-change×private command, touch×revoke, two reset/disable, buckets multi-processo | PASS — CL-02 APPLICABLE SUBSET | concorrências de Quote/OS/Charge nas CL-04..06 |

O fixture browser é CLI e recusa qualquer `APP_ENV` diferente de `test`; `--reset` usa a role migrator apenas no banco descartável do gate. O workflow preserva os jobs CL-01 e define `identity-integration`, `identity-security`, `identity-e2e` e `cl02-gate`. Resultado GitHub real pertence ao SHA publicado e é registrado no relatório de execução, evitando inserir um SHA auto-referente no commit.

[SQLAlchemy version counter](https://docs.sqlalchemy.org/en/20/orm/versioning.html) cobre o caminho de flush; bulk updates exigiriam proteção própria e são evitados. [Alembic autogenerate/check](https://alembic.sqlalchemy.org/en/latest/autogenerate.html) documenta limites de detecção; constraints críticas têm inspeção adicional. São evidências documentais, não execução nesta fase.

## Evidência CL-03

CL-03 acrescenta testes de schema/grants e upgrade 0002→0003 com eventos CL-02 preservados; API real PostgreSQL cobre CRUD, ownership cruzado 404, mass assignment 422, archive/restore/no-op, busca literal, paginação, timeline allowlist, rollback e corridas coordenadas por barriers. A suíte prova two Client PATCH, archive/restore versus PATCH, two Equipment PATCH, create/mutation de Equipment versus archive do Client e stale ETag.

Vitest cobre lista/detalhe/papel e preservação do formulário no 412. O spec `@cl03` executa login Admin, Client/Equipment completos, timeline, archive/restore, isolamento de ownership e negação Técnico na matriz fixa Chromium 390/768/1024/1440, Firefox 1440 e WebKit 390. O proxy usa `$uri` no access log; canários de body/query ficam ausentes de app/proxy logs e valores privados não entram na timeline ou em artifacts Playwright CL-03, que desativa screenshot e trace.

| Requisito | Resultado CL-03 | Diferido |
|---|---|---|
| DOM-09 | PASS — CL-03 APPLICABLE SUBSET: archive/restore Client e Equipment, histórico preservado, sem cascade, ownership e bloqueio de novo Equipment em Client arquivado | seleção/send e snapshot Quote CL-04; execução/snapshot OS CL-05 |
| AZ-01..06 | PASS — CL-03 APPLICABLE SUBSET: Clients/Equipment/timeline Admin-only e ownership aninhado | Quote CL-04; OS/arquivos CL-05 |
| SEC-01/03/05 | PASS — CL-03 APPLICABLE SUBSET: CSRF/origin, payload/log allowlists, CSP e deep links | público Quote CL-04; multipart CL-05 |
| CON-01 | PASS — CL-03 APPLICABLE SUBSET: versões, locks raiz, races Client/Equipment e timeline atômica | Quote/OS/Charge CL-04..06 |

O workflow possui exatamente 14 jobs e `cl03-gate` exige sucesso explícito dos 13 jobs anteriores. Run e SHA finais são evidência externa do relatório de execução, sem criar referência auto-referente nestes documentos.
