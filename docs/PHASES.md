# ClientOps — fases, gates e evidências

Cada fase precisa satisfazer o gate anterior e entregar evidência real. O parágrafo abaixo preserva o histórico da correção documental CL-00-FIX; o estado operacional atual da Foundation está na seção “Execução CL-01”.

## Read-first original — histórico CL-00 em 25/09/2026

| Item | Evidência e resultado |
|---|---|
| Diretório atual | pwd → /home/breno/Projects |
| Repositório | .git no diretório pai existe vazio/read-only; sem HEAD, config, objects ou refs; não caracteriza checkout válido visível |
| Ferramenta Git | git rev-parse/status não executáveis: /bin/bash: git: command not found, exit127; command -v git sem saída; caminhos comuns ausentes |
| Branch | Não aplicável/determinável neste workspace sem metadados Git |
| HEAD | Não aplicável; arquivo .git/HEAD ausente |
| Working tree | Estado Git indisponível; inventário inicial de arquivos regulares vazio |
| Estrutura | Somente diretórios .git, .agents e .codex, todos vazios; nenhuma subárvore de produto |
| Instruções locais | Nenhum AGENTS.md em workspace ou ancestrais inspecionados |
| Implementação/config | Nenhuma encontrada por rg --files --hidden e find |
| Documentação existente | Nenhuma; anexo do usuário fora do workspace é a fonte de entrada |
| Conflitos materiais | Nenhum artefato anterior para conflitar; originais pre-CL-00 não disponíveis separadamente |

Anexo lido: /home/breno/.codex/attachments/e37aa8a6-56e5-4cf9-adcc-e061cc6f25eb/Pasted text.txt, 3094 linhas. Fonte consolidada inclui baseline/auditoria/UI. Não se inferiu workspace vazio antes da inspeção. Nenhum diretório especial foi modificado; Git não foi instalado/inicializado.

A inspeção acima descreve o CL-00 original, não o root oficial nem a prontidão atual. B01 corrigiu a utilização do diretório pai como root; o gate original não permanece válido.

## Root oficial e read-first CL-00-FIX

**Project/repository root: /home/breno/Projects/clientops.** /home/breno/Projects é somente o diretório pai. Os nove documentos ficam em /home/breno/Projects/clientops/docs; todos os caminhos relativos futuros partem desse root. git init, quando autorizado em CL-01, só poderá ocorrer dentro de /home/breno/Projects/clientops. Não inicializar, mover ou reaproveitar o .git vazio do pai.

O FIX começou com pwd=/home/breno/Projects, nove Markdown em docs/, sem clientops/ e sem código. Os nove documentos foram lidos integralmente antes da primeira alteração. Não havia AGENTS.md local/ancestral nem conflito com implementação. Foram capturados conteúdo/hash de cada documento para comparação antes/depois. Somente esses nove arquivos foram movidos ao novo root, sem sobrescrever destino existente; docs/ antigo ficou vazio e diretórios especiais permaneceram intocados.

Git, Node, npm, uv e Docker não estão disponíveis no PATH desta execução; python3 está disponível na versão 3.12.3, diferente da linha 3.13.x definida em ARCHITECTURE. Não instalar ferramentas nesta correção. Root físico foi estabelecido; repositório Git ainda não existe nele, logo branch/HEAD/status Git são indisponíveis.

**Preflight bloqueador de CL-01:** antes do bootstrap, conferir cwd/root real, permissões e presença/funcionamento de Git e toolchain definida em ARCHITECTURE. Se root real não puder ser estabelecido ou Git/toolchain continuarem indisponíveis, CL-01 não pode prosseguir. Somente quando CL-01 estiver autorizada e esse preflight passar, inicializar Git no root oficial se necessário e verificar que git rev-parse --show-toplevel resolve exatamente esse root; checkout em outro root impede continuar.

Fonte da correção: /home/breno/.codex/attachments/0bcdf7f3-88d6-4c85-ba6d-d87f28d502d2/Pasted text.txt. As instruções B01/B02/B03/H01/H02/M01/M02 do usuário são a autoridade para estas alterações; não há mudança silenciosa de baseline.

Continuação em 28/09/2026, conforme /home/breno/.codex/attachments/c19e635c-7021-4e7d-966e-fe5a8ddeb995/Pasted text.txt: inventário físico e ferramentas foram inspecionados novamente, e as seções alteradas dos nove documentos foram relidas antes de editar. O root contém apenas docs/ e os nove Markdown esperados; docs/ do pai permanece vazio. Nesta continuação, somente API.md (delimitador da tabela de public-access) e PHASES.md (evidência final) receberam ajustes; as correções anteriores foram preservadas.

## CL-00 — Specification, Architecture & Contracts

- **Objetivo:** transformar baseline em contratos implementáveis e auditáveis.
- **Escopo exato:** read-first, pesquisa oficial proporcional, decisões de arquitetura/domínio/security/API/UI/tests/deploy, fases e gate; somente nove Markdown.
- **Fora:** todo bootstrap/código/dependência/migration/workflow/commit/push/PR e CL-01.
- **Dependência:** anexo consolidado fornecido.
- **Entregáveis:** PRODUCT, ARCHITECTURE, DOMAIN, SECURITY, API, UI_UX, TESTING, PHASES, DECISIONS.
- **Verificações:** links internos, inventário, cobertura das40 decisões, máquinas de estado, schemas e contratos cruzados; revisão de escopo. Não executar testes de produto inexistentes.
- **Docs requeridas:** todas as nove.
- **DoD:** seções103/104 do pedido cobertas, zero crítica estrutural pendente, zero CR bloqueador e somente docs alteradas.
- **Audit gate:** gate original rejeitado; aplicar CL-00-FIX e submeter à reauditoria independente antes de qualquer CL-01.
- **Evidência:** comandos read-only/inventário, fontes oficiais, verificação documental e relatório final.

## CL-01 — Foundation

- **Objetivo:** base executável/reproduzível que preserva contratos.
- **Escopo exato:** bootstrap monorepo backend/frontend nos layouts decididos, runtimes/locks, FastAPI composition + health/errors/config/Clock/DB; React/Vite/router com três layouts ainda sem fluxos de negócio; tokens/wrappers mínimos; PostgreSQL, Alembic metadata e baseline vazio revisado; Docker/Compose/proxy/volumes; CI inicial lint/typecheck/test-smoke/build/migration/smoke; geração de contrato TS a partir de OpenAPI.
- **Fora:** autenticação pronta, tabelas de produto, usuários seed, clientes/quote/OS/cobranças/automação funcional.
- **Dependências:** reauditoria independente CL-00-FIX aceita, root real /home/breno/Projects/clientops estabelecido e preflight Git/toolchain aprovado; decisões fechadas. Na condição atual de ferramentas ausentes, CL-01 não pode prosseguir.
- **Entregáveis:** app shells, health/live/ready, config validada, containers cold start e locks; primeira migration sem domínio; documentação de setup sem segredo.
- **Testes:** CI CL-01 de TESTING; banco vazio upgrade head/check, health200/503 por falhaDB, web build, envelope genérico, Clock/config unit, componentes de foundation/keyboard; SEC-05 verifica headers CSP separados público/privado no build servido/deep links.
- **Docs:** ARCHITECTURE/TESTING/PHASES/DECISIONS com patches/digests/versões realmente resolvidos; UI_UX se wrapper exigir esclarecimento sem mudar baseline.
- **DoD:** Compose simples sobe, DB privado/volume privado, build/types/lint/smoke/migration passam; secrets fora do frontend/repo.
- **Audit gate:** confirmar root/preflight e que nenhum tenant/JWT/framework genérico/negócio foi introduzido; locks reprodutíveis e readiness depende de migration. /q estrita e script-src sem unsafe-inline; eventual necessidade mínima de style inline privado documentada por componente/diretiva/rota, sem relaxamento global.
- **Evidência:** versões, logs cold start/checks, schema inicial e inventário de alterações.

## CL-02 — Identity, Sessions & Security

- **Objetivo:** identidade e autorização seguras, perfil da empresa.
- **Escopo exato:** tabelas users/sessions/business_profiles/rate_limit_buckets/timeline_events (somente contextos existentes, progressão em DOMAIN); CLI Admin/reset segura; criação técnico/senha temporária/troca; login/logout/cookie/CSRF/origin; revogação/lifecycle; RBAC fixo e scopes base; BusinessProfile nullable no onboarding, is_complete derivado dos cinco campos e timezone IANA escolhida explicitamente. Estrutura comum de logs/rate limiting; UI login/troca/conta/config.
- **Fora:** clientes/orçamentos/OS/cobrança/alertas e upload de logo. Logo será entregue em CL-05 junto ao pipeline completo; até lá campo permanece null e UI não promete upload.
- **Dependências:** CL-01 PASS; perfil completo antes de send/start em fases posteriores.
- **Entregáveis:** migrações identidade/profile/infra/timeline, fluxos sessão e telas, autorização reusable explícita, perfil.
- **Testes:** AUTH-01..08, AZ-base, SEC-01/03/04/05, BP-01/02 e BP-03 no domínio/endpoints existentes, email/cookie/lastAdmin/CLI; integração PostgreSQL; Playwright login/troca/logout/onboarding e gates existentes. BP-03 send/start será completado com endpoints em CL-04/CL-05.
- **Docs:** SECURITY/API/DOMAIN/TESTING/PHASES; registrar medição Argon2 no container real e origem/cookie dev/prod.
- **DoD:** disabled/reset impedem novas operações/sessões anteriores, forced-change não vaza módulos, CSRF passa teste negativo, setup sem senha default.
- **Audit gate:** provar com requests reais proteção server-side/segredos fora de logs, inclusive rotas ainda mínimas; nenhum timezone default de produção/empty sentinel. Revalidar SEC-05 com telas reais e toda eventual exceção mínima de style inline privado; /q nunca herda relaxamento.
- **Evidência:** testes, esquema, headers sanitizados e medição de hashing sem senha/log sensível.

## CL-03 — Clients & Equipment

- **Objetivo:** cadastros operacionais com archive e ownership.
- **Escopo exato:** migrations Client/Equipment, API/Admin UI, search/filter/pagination, archive/restore, equipment dentro do cliente, timeline contextual básica.
- **Fora:** quote público, OS executável, charge e gestão genérica de ativos.
- **Dependências:** CL-02 identity/profile/scope PASS.
- **Entregáveis:** fluxos de cliente/equipamento com estados UI e vínculo seguro; dados fictícios mínimos de teste.
- **Testes:** DOM-09, ownership composto, archive sem delete, API/UI/a11y; T sem listagem/edição; gates anteriores e migration.
- **Docs:** DOMAIN/API/UI_UX/TESTING/PHASES.
- **DoD:** cadastro/arquivo/restauração completos sem campos pessoais não autorizados, quatro viewports, sem exposição técnica indevida.
- **Audit gate:** histórico não apagado e APIs não dependem de esconder botão.
- **Evidência:** fixtures cruzadas de clientes/equipamentos e resultados de API/browser.

## CL-04 — Quotes

- **Objetivo:** proposta histórica com aprovação segura pública.
- **Escopo exato:** Quote/Items/Access, BRL/Decimal, state machine, snapshot interno e projeção pública client {name}, send/cancel/duplicate; bearer/hash/TTL/revoke/rotate, /q com fragmento/memória, GET read/POST approve, copiar link/WhatsApp manual sem bearer em query; timeline comercial e UI completa. Logo pode ser null até CL-05. Web Share API somente OPTIONAL/NON-BLOCKING, com fallback Copiar link; sua ausência não impede o gate.
- **Fora:** PDF de orçamento, REJECTED/EXPIRED persistidos, entrega automática/e-mail/APIWhatsApp, portal ou criação automática de OS.
- **Dependências:** CL-03 PASS e profile completo.
- **Entregáveis:** migrations/contratos/telas/Admin+público, idempotência approve e immutability; snapshot com logo optional já definido.
- **Testes:** DOM-01/05/06/10, PUB-01..09, BP-03/send, HIS-01, CON-01/02/07/público, CSRF/leakage/security + E2E até APPROVED; UI-04 somente se Web Share opcional implementado.
- **Docs:** DOMAIN/SECURITY/API/UI_UX/TESTING/PHASES; sources/DECISIONS se implementação revelar incompatibilidade real.
- **DoD:** duas aprovações não duplicam, concorrência cancel/approve serializa, token nunca em API URL/log/query, alteração cadastro não altera proposta; DTO público exclui client.phone/email/address/id/notes e send bloqueia profile incompleto.
- **Audit gate:** revisar segredo desde emissão até clipboard/WhatsApp, error paths/traces; zero quebra do snapshot.
- **Evidência:** testes concorrentes reais, comparação snapshot antes/depois e network/log scans sanitizados.

## CL-05 — Service Operations

- **Objetivo:** atendimento mobile completo com histórico e relatório.
- **Escopo exato:** OS/agenda/overlap warning, técnico único/projeção mobile; checklist/notes/evidence, confirmação duas variantes, imutabilidade/start/completion snapshots; FileStorage/pipeline e logo completo; Report/PDF/CLI retry + scheduler técnico; timeline de execução.
- **Fora:** cobrança/automação comercial/dashboard final, múltiplos técnicos, offline/GPS, templates globais, relatório público.
- **Dependências:** CL-04 PASS; snapshot/public contracts existentes.
- **Entregáveis:** migrations/telas/streams autorizados, agenda hoje/semana, reportPENDING/FAILED/READY, PDF pt-BR, recovery/storage.
- **Testes:** DOM-02..04/07, AZ-01/02/05/06, BP-03/start, HIS-02..04, UP-01..11, REP-01..05, CON-03/05/06; Hero1–6, mobile/a11y/browser. UP-11 usa iPhone real/Safari suportado, câmera e biblioteca pelo input web/upload ServiceEvidence até concluir Hero; registra MIME/formato efetivamente entregues.
- **Docs:** DOMAIN/ARCHITECTURE/SECURITY/API/UI_UX/TESTING/PHASES; evidência render/limites e backup.
- **DoD:** técnico conclui com checklist/resolução, terminal não muda, PDF falho não desfaz OS e retry usa snapshot original, storage nunca público; start exige profile completo e UP-11 tem evidência real de câmera/biblioteca.
- **Audit gate:** limites decoder/arquivo, autorização por objeto, races complete/upload/uncheck, Unicode/tabelas/fotos/quebras no container CI. Não presumir formato do Safari: se ambiente suportado entregar HEIC e o fluxo falhar, registrar blocker antes da release e exigir suporte seguro autorizado ou revisão explícita da support matrix; sem essas decisões/teste não aprovar gate.
- **Evidência:** PDF sintético/hash/texto, imagens sanitizadas/EXIF removido, testes/visualização, logs de retry e relatório UP-11 com dispositivo/versões/origem/MIME/formato por câmera e biblioteca. Emulação ou JPEG pré-convertido não substitui iPhone real.

## CL-06 — Product Closure

- **Objetivo:** completar acompanhamento, demo e release v1.
- **Escopo exato:** Charge única, automações3/alerts/state reconciliation, dashboard action-first, timeline final/projeções, seed relativo Climatech, hardening, CI final/E2E3 engines, backup/restore/smoke, docs operacional/comercial e auditoria/release.
- **Fora:** todos POST-V1 de PRODUCT; release não autoriza escopo adicional.
- **Dependências:** CL-05 PASS, Hero1–6 estável.
- **Entregáveis:** migrations financeiro/alertas, scheduler comercial e monitoramento, dashboard/charge UX, seed sem PII, evidence bundle/checklist de release.
- **Testes:** DOM-08/AUT-01..06/API-04/CON-04/fullAPI/security; fullHero1–7,4viewports, Safari/iOS/Android reais, migration/upgrades, OPS-01/02. Repetir UP-11 no candidato a release em iPhone/Safari suportado, câmera e biblioteca, registrando MIME/formato e conclusão.
- **Docs:** todas nove reconciliadas com implementação, versões reais, instruções de setup/CLI/backup/deploy e limitações; manter fontes de verdade sem duplicar regras.
- **DoD:** escopo REQUIRED V1 completo, zero falha crítica, artifacts sem secrets, demo coerente no clock, restore testado e operação de jobs comprovada; OS COMPLETED sem Charge não gera pendência artificial e indicadores contam somente cobranças existentes; UP-11 aprovado nas versões declaradas.
- **Audit gate:** audit produto/domínio/security/UX/delivery; regressões obrigatórias e nenhuma promessa não comprovada. Sem evidência real UP-11 não há PASS. Falha por HEIC entregue em ambiente suportado bloqueia release até decisão explícita A (suporte seguro) ou B (revisão da support matrix) e nova verificação; HEIC continua fora do escopo até essa decisão.
- **Evidência:** jobs/checks reais, roteiro demo, screenshots sintéticos por persona, hashes/PDF, relatório de browsers, restore e inventário final.

Release executável/deploy só em sua fase e dentro de autorização daquela execução. Nesta CL-00 não se cria workflow, container, seed, teste ou fonte de aplicação.

## Definition of Ready de CL-01

PASS abaixo significa **contrato especificado**, não autorização para bootstrap nem implementação validada. Preflight operacional abaixo é separado e continua bloqueador.

| Pergunta obrigatória | Resultado | Fonte e resposta |
|---|---|---|
| Estrutura monorepo? | PASS | Root /home/breno/Projects/clientops; ARCHITECTURE: backend/frontend/docs/e2e/infra/.github relativos a ele |
| Runtimes/versions? | PASS | Python3.13, Node24/npm11, PG17; linhas stack e lock policy definidos |
| Dependências-base? | PASS | Tabela ARCHITECTURE; entrada por fase |
| Comunicação frontend/backend? | PASS | SPA/REST /api/v1 mesma origem, sessão cookie, CSRF; público Bearer separado |
| Configuração? | PASS | Catálogo required/optional/secret/public; onboarding NULL/timezone explícita; sem secrets frontend |
| Schema inicial mínimo? | PASS | CL-01 Alembic baseline vazio; domínio começa CL-02 |
| Validação de migration? | PASS | PG17 vazio upgrade head, check e constraints específicas |
| Fronteiras de módulos? | PASS | Layout, serviços/transações/repositories/Clock/FileStorage definidos |
| Gates primeiro CI? | PASS | Lint/typecheck/unit/component smoke/build/health/migration/Compose |
| Design/component foundation? | PASS | Radix/shadcn selecionados, tokens/contratos, persona layouts e acessibilidade |
| Decisões que CL-01 não reabre? | PASS | Stack, single-tenant, cookie, CSRF, público fragment, snapshots, entidades/estados, navegação, fases e scope |

Resolver patches compatíveis e validar ambiente não reabre essas escolhas. Mudança material passa Change Request de PRODUCT, com evidência e impacto, antes da implementação afetada.

| Preflight operacional CL-01 | Situação nesta correção |
|---|---|
| Root físico correto estabelecido | PASS — /home/breno/Projects/clientops/docs contém os nove documentos |
| Git/toolchain disponíveis | FAIL — Git, Node, npm, uv e Docker ausentes do PATH; Python disponível 3.12.3, alvo 3.13.x; nenhuma instalação autorizada no FIX |
| Reauditoria independente aceita | Pendente — esta entrega será submetida à reauditoria |

Na data da correção CL-00-FIX, CL-01 **não podia prosseguir** naquele ambiente/estado. Esse registro é histórico e foi superado pelo preflight posterior descrito abaixo.

## Execução CL-01 — 30/09/2026

O preflight posterior estabeleceu o root `/home/breno/Projects/clientops`, Git funcional, Python 3.13.15, uv 0.12.19, Node 24.21.0, npm 11.19.0, Docker 29.1.3 e Compose 2.40.3. O baseline dos nove documentos está no commit `84f7c4a`; a implementação ocorre em `feat/cl-01-foundation`, sem merge para `main`.

A Foundation local está implementada: locks, FastAPI/config/Clock/erros/logs, PostgreSQL 17 com roles separadas, revisão vazia `0001_foundation`, health live/ready, probe técnico do volume, shells React, Nginx/CSP/TLS, contratos OpenAPI→TypeScript, Compose, testes e workflow. Scheduler e FileStorage operacional permanecem CL-05. Nenhuma entidade ou autenticação CL-02+ foi criada.

T01–T24 passaram localmente; a matriz e os comandos estão em TESTING. O ciclo real de banco indisponível preservou live 200, produziu ready 503 e recuperou ready 200 sem restart da API. A recriação de containers sem `--volumes` preservou `pg_data`, revisão `0001_foundation` e marcador 0600 de `private_files`; apenas o marcador de teste foi removido.

O workflow define `backend-quality`, `frontend-quality`, `database-migration`, `contract-drift`, `compose-smoke`, `security-foundation` e `cl01-gate`. O gate usa `!cancelled()` para preservar cancelamento do workflow e, nos demais resultados, exige `success` de cada job; failure/skipped ou qualquer valor diferente falha o gate. O repositório `brenoribeiro7/clientops` é público, usa `main` como branch padrão e mantém `main` em `84f7c4aa5af9dc292b109cf6602d3dd302ac870e`; a feature é `feat/cl-01-foundation`.

O SHA pré-correção documental `6776fa2464cb09d66b318d103e85e74ec48f094e` recebeu o run real histórico `36732984184` com conclusão `success`. `backend-quality`, `frontend-quality`, `database-migration`, `contract-drift`, `compose-smoke`, `security-foundation` e `cl01-gate` foram todos `success`. Como a reconciliação documental cria novo SHA, esse run não é o gate final: o SHA final precisa de nova execução completa e verde, registrada no relatório externo para não criar loop de commits.

Nenhuma fase da v1 pode exigir infraestrutura paga ou produção pública 24/7 para fechar gate/release. Execução, testes e demo oficiais usam a baseline local definida em PRODUCT/ARCHITECTURE; deployment público permanece OPTIONAL/NON-BLOCKING, sem enfraquecer a arquitetura production-deployable.

Durante a execução, o uso de `infra/dev-env.py --force` regenerou credenciais enquanto o volume PostgreSQL descartável ainda guardava as anteriores. Somente esse `pg_data` técnico sem dados relevantes foi removido; `private_files` foi preservado. O procedimento operacional agora proíbe essa rotação sobre volume persistido e exige coordenação explícita futura.

## Reauditoria interna CL-00-FIX

O resultado original foi rejeitado pela auditoria independente; não é mantida a declaração anterior de prontidão. A correção atual será submetida a nova auditoria. O histórico read-first foi preservado como histórico, separado do root e do preflight atuais.

| Finding | Resultado documental | Correção e rastreabilidade |
|---|---|---|
| B01 — PROJECT ROOT | RESOLVED | Nove documentos movidos para /home/breno/Projects/clientops/docs; pai identificado; Git init futuro somente no root oficial; CL-01 bloqueada se root/Git/toolchain indisponíveis. ARCHITECTURE, PHASES, DECISIONS |
| B02 — BUSINESS PROFILE / TIMEZONE | RESOLVED | Cinco campos nullable no onboarding; is_complete derivado de trade_name/phone/email/address/timezone válidos; sem empty sentinel/default; send/start bloqueados; ausência de timezone sem fallback e seed isolado. DOMAIN, ARCHITECTURE, API, UI_UX, TESTING BP-01..03, DECISIONS |
| B03 — PUBLIC QUOTE DATA MINIMIZATION | RESOLVED | Cliente público apenas client {name}; contatos/endereço/ID/notas excluídos do DTO/HTML/estado; snapshot interno preservado e contatos business permitidos. DOMAIN, API, SECURITY, UI_UX, TESTING PUB-09, DECISIONS |
| H01 — OPTIONAL CHARGE VS DASHBOARD | RESOLVED | Ausência de Charge não gera attention/alert/dívida; ação contextual e indicadores sobre registros existentes; sem flags/estados compensatórios. PRODUCT, DOMAIN, API, UI_UX, TESTING API-04, DECISIONS |
| H02 — REAL IOS PHOTO FLOW | RESOLVED | Gate UP-11 CL-05/CL-06: iPhone/Safari real, câmera e biblioteca via input/upload/ServiceEvidence/Hero, registro MIME/formato efetivo; falha HEIC em ambiente suportado bloqueia release até decisão explícita A/B. SECURITY, UI_UX, TESTING, PHASES, DECISIONS |
| M01 — SHARING UX | RESOLVED | Web Share somente OPTIONAL/NON-BLOCKING com gesto/share sheet; fallback Copiar link; WhatsApp sem bearer em query. PRODUCT, ARCHITECTURE, SECURITY, UI_UX, TESTING UI-04 condicional, DECISIONS |
| M02 — PRIVATE CSP | RESOLVED | /q estrita; script-src unsafe-inline proibido; eventual style inline privado mínimo/documentado/verificado CL-01/CL-02, sem relaxamento global. ARCHITECTURE, SECURITY, UI_UX, TESTING SEC-05, PHASES, DECISIONS |

RESOLVED significa que o finding foi corrigido na especificação; não declara que os testes futuros passaram. No checkpoint histórico CL-00-FIX, H02 permanecia um gate futuro e Git/toolchain ainda impediam CL-01; o impedimento de toolchain foi superado pelo preflight posterior, enquanto H02 continua previsto para CL-05/CL-06. Nenhuma funcionalidade nova REQUIRED V1 foi acrescentada: onboarding/privacidade/optional Charge/segurança/mobile foram corrigidos, Web Share é opcional, HEIC não foi incorporado.

Arquivos movidos e com conteúdo alterado nesta correção, todos sob o root oficial:

- docs/PRODUCT.md
- docs/ARCHITECTURE.md
- docs/DOMAIN.md
- docs/SECURITY.md
- docs/API.md
- docs/UI_UX.md
- docs/TESTING.md
- docs/PHASES.md
- docs/DECISIONS.md

Verificação final documental: PASS. Inventário exato de nove documentos no root oficial, 14 links locais válidos, cinco exemplos JSON válidos, fences balanceados e 33 tabelas com colunas consistentes após corrigir o delimitador em API.md. Permanecem 16 entidades, 12 ADRs, cobertura sequencial das 40 decisões e sete fases CL-00..CL-06. A revisão cruzada dos nove documentos não encontrou contradição bloqueadora residual nos sete findings: referências ao root anterior são históricas, America/Bahia está restrita ao seed/fixtures, dados extras do cliente ficam internos, ausência de Charge é legítima, HEIC segue excluído, Web Share é opcional e /q não herda exceção privada de CSP.

Nenhuma funcionalidade nova REQUIRED V1 foi introduzida no CL-00-FIX. Naquele checkpoint histórico, a prontidão abaixo era somente para reauditoria documental, não liberava CL-01 e nenhum teste de runtime, browser/iPhone, build, Docker ou CI havia sido executado. O preflight, a implementação e a CI CL-01 posteriores estão registrados na seção de execução acima.

CL-00-FIX STATUS: READY FOR RE-AUDIT

## Execução CL-02 — checkpoint local de 01/10/2026

A feature `feat/cl-02-identity-sessions-security` implementa a migration `0002`, auth/session/cookie/CSRF/origin, rate limiting PostgreSQL, BusinessProfile/User/timeline, CLI segura, OpenAPI/TS, frontend privado e isolamento `/q`. O scope audit encontra somente as cinco tabelas autorizadas e nenhuma entidade CL-03+.

Os gates locais de unidade, PostgreSQL, Compose, frontend, HTTP multi-browser e HTTPS identity/security passaram conforme TESTING: 50 pytest sem PostgreSQL, 34 PostgreSQL, 8 Compose/artefatos, 9 Vitest, 100 HTTP Playwright pass/8 skips esperados e 9 HTTPS pass. O benchmark Argon2 hash/verify real está em SECURITY. Os jobs GitHub CL-02 estão definidos com `cl02-gate` exigindo `success` de todos os resultados; a execução GitHub no SHA final ainda será registrada. A fase permanece aberta para Implementation Audit e não é declarada CLOSED neste documento.

## Execução CL-03 — checkpoint de implementação

A feature `feat/cl-03-clients-equipment` implementa migration 0003, Client/Equipment, ownership aninhado, archive/restore versionado, timeline do cliente, OpenAPI/TS e telas Admin responsivas. Os jobs `clients-integration`, `clients-e2e` e `cl03-gate` elevam o workflow para 14 jobs e preservam os gates CL-01/02.

DOM-09 é `PASS — CL-03 APPLICABLE SUBSET`: archive/restore, histórico, ausência de cascade, ownership e rejeição de novo Equipment sob Client arquivado foram materializados. Quote selection/send e snapshot permanecem CL-04; execução e snapshot de OS permanecem CL-05. A fase aguarda Implementation Audit e não é declarada CLOSED neste documento.

## Execução CL-04 — checkpoint de implementação

A feature `feat/cl-04-quotes-public-approval` implementa migration 0004, Decimal/snapshot, máquina de Quote, lifecycle do acesso público, aprovação segura, timeline, OpenAPI/TS e as jornadas Admin e `/q`. Os locks de data civil seguem BusinessProfile→Client/Quote e os testes PostgreSQL coordenam as corridas comerciais, inclusive mudança de timezone e retry sem repetir rate limit/touch de sessão.

Os jobs `quotes-integration`, `quotes-e2e` e `cl04-gate` elevam o workflow para 17 jobs e preservam integralmente CL-01/02/03. O gate remoto pertence ao SHA publicado e será registrado no relatório de execução. ServiceOrder, Evidence, Report, Charge, Alert, scheduler, PDF e upload/logo persistido permanecem CL-05+; a fase não é declarada CLOSED neste documento.
