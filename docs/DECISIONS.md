# ClientOps — decisões CL-00

Registro de decisões não triviais. Data de referência: 25/09/2026. Todas classificadas **REQUIRED V1**, exceto itens explicitamente OPTIONAL/NON-BLOCKING ou POST-V1 em PRODUCT. Parâmetros normativos ficam em DOMAIN/SECURITY/API; este registro explica escolhas e oferece rastreabilidade.

CL-00-FIX incorpora os findings B01/B02/B03/H01/H02/M01/M02 por instrução explícita do usuário após rejeição do gate anterior. Essas correções prevalecem sobre os trechos originais afetados. Não há funcionalidade nova REQUIRED V1: Web Share é OPTIONAL/NON-BLOCKING e HEIC continua fora do escopo atual. Gates adicionais verificam requisitos já existentes de privacidade, segurança e uso mobile.

## D01 — Monólito modular e fronteiras

- **Decision:** estrutura de aplicação single-tenant.
- **Context:** pequena instalação, stack congelada e fluxo que atravessa proposta/execução/histórico.
- **Options considered:** monólito por feature; camadas globais genéricas; microservices.
- **Chosen option:** módulos por domínio em backend/app/modules; React SPA com layouts Admin/Técnico/Público; SQLAlchemy síncrono e serviços transacionais explícitos.
- **Rationale:** transações locais e queries legíveis atendem o fluxo sem infraestrutura distribuída.
- **Consequences:** deploy conjunto, um banco, FileStorage/Clock como poucas fronteiras substituíveis; nenhuma organization_id/tenant plumbing.
- **Rejected alternatives:** microservices/CQRS/brokers/event bus/repositories genéricos por cerimônia.
- **Revisit trigger:** necessidade demonstrada de múltiplas instalações compartilharem produto, somente POST-V1/CR.

**Correção B01:** root de projeto/repositório congelado em /home/breno/Projects/clientops, com docs/ interno. /home/breno/Projects é apenas pai. Os nove Markdown foram movidos; Git não foi inicializado. git init, quando autorizado em CL-01, só pode ocorrer dentro do root oficial. Root real não estabelecido ou Git/toolchain indisponíveis bloqueiam o início/prosseguimento de CL-01; não confundir especificação pronta para reauditoria com ambiente pronto para bootstrap.

## D02 — HTTP e concorrência

- **Decision:** API pragmática versionada e prevenção de atualização perdida.
- **Context:** Admin/técnico/jobs e público podem agir no mesmo recurso.
- **Options considered:** last-write-wins; optimistic version; locks em toda leitura; infraestrutura idempotency genérica.
- **Chosen option:** /api/v1, snake_case, envelope de erro único, paginação offset limitada, ETag/If-Match em agregados, locks de raiz para transições e constraints PostgreSQL; exceções explícitas de repetição em API.
- **Rationale:** version evita sobrescrever formulário antigo, lock valida estado atual, unique impede duplicatas estruturais.
- **Consequences:** 428/412/409 distintos; filhos incrementam version da raiz; sem retry automático de create; read-only não bloqueia globalmente.
- **Rejected alternatives:** isolamento SERIALIZABLE universal, Redis locks, idempotency-key middleware com replay de segredos.
- **Revisit trigger:** conflitos medidos tornarem paginação/locks inadequados; nunca retirar garantias para simplificar.

Documentação [SQLAlchemy version counter](https://docs.sqlalchemy.org/en/20/orm/versioning.html) e [PostgreSQL locking](https://www.postgresql.org/docs/17/explicit-locking.html) sustenta os mecanismos. A ordenação de locks e semântica HTTP são decisões do projeto, não resultados de benchmark.

## D03 — Identidade, senha e sessão

- **Decision:** credenciais e ciclo de sessão.
- **Context:** cookie opaco é baseline; técnico provisionado por Admin com troca obrigatória.
- **Options considered:** Argon2id/bcrypt; sessão bearer opaca/JWT; CSRF origem apenas/token+origem.
- **Chosen option:** Argon2id64MiB/t3/p4, salt16/hash32; senha15–128 chars/512bytes; session256bits SHA-256; idle30min/absolute12h/touch60s; rotação em login/troca, sem periódica; cookie __Host- HttpOnly/Secure/Lax; HMAC-CSRF + origem confiável.
- **Rationale:** custo de hash explícito, revogação no banco e proteção contra CSRF com cookie; sem segredos persistidos no browser.
- **Consequences:** reset/disable revogam todas; credencial temporária24h e sessão restrita; email ASCII/IDNA lowercase consistente e unique; custo Argon2 será medido CL-02.
- **Rejected alternatives:** JWT/localStorage, e-mail password recovery v1, rotação a cada request e dependência de SameSite como única defesa.
- **Revisit trigger:** medição no host exigir ajuste justificado de capacidade/parâmetros, incidente de sessão ou expansão de requisitos após v1.

Parâmetros conferidos na [API argon2-cffi](https://argon2-cffi.readthedocs.io/en/25.1.0/api.html). O perfil escolhido existe; nenhuma latência local foi medida. [OWASP sessão](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) e [OWASP CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) fundamentam defesa em camadas; os timeouts e HMAC deste contrato são escolhas locais.

## D04 — Link público e WhatsApp

- **Decision:** autenticação pública e tratamento da perda de segredo.
- **Context:** snapshot pode ser aprovado sem conta; bearer não pode aparecer em URL de servidor/query/log.
- **Options considered:** token no path/query; fragmento convertido em cookie; fragmento/memória e Authorization header.
- **Chosen option:** 32bytes CSPRNG, SHA-256 apenas no banco, fragmento /q#token=..., replaceState imediato, credentials omit e Authorization:Bearer; TTL30dias, revogação/rotação com um acesso não revogado.
- **Rationale:** navegador não envia fragmento automaticamente; rotas públicas têm autenticação separada de Admin. Repetir approve válido retorna200/mesmo approved_at.
- **Consequences:** refresh requer reabrir link; raw secreto perdido requer rotate, não recuperação. Cancelar revoga. WhatsApp abre mensagem sem link secreto; Admin cola link previamente copiado no chat. Isso preserva proibição de query string e mensagem pré-preenchida sem CR.
- **Rejected alternatives:** wa.me?text contendo link/bearer, logging de URL compartilhada, portal/account, identidade jurídica do aprovador.
- **Revisit trigger:** entrega automatizada ou autenticação forte do cliente aprovada POST-V1.

**Correção B03:** DTO público por allowlist contém somente client {name}; client.phone/email/address/id/notes são ausentes do JSON/HTML/estado, ainda que snapshot interno preserve os dados históricos para Admin. Contatos comerciais business continuam públicos. Rationale: bearer pode ser encaminhado; campos cadastrais extras não são necessários à decisão de aprovar. PUB-09 verifica a fronteira.

**Melhoria M01 — OPTIONAL/NON-BLOCKING:** Web Share API pode abrir share sheet nativo a partir de gesto explícito e link em memória, quando suportada. Copiar link é fallback permanente; WhatsApp com colagem manual continua permitido, nunca com bearer em query. Não adicionar dependência/serviço, não prometer entrega, nem bloquear Hero Flow quando API não existir. UI_UX/SECURITY definem o contrato e teste condicional UI-04; [Web Share API](https://www.w3.org/TR/web-share/) é a fonte do mecanismo.

## D05 — Dinheiro e tempo

- **Decision:** tipos, arredondamento e fonte de tempo.
- **Context:** centavos e vencimento civil precisam ser determinísticos.
- **Options considered:** float/cents inteiros/Decimal; datas UTC para tudo/data civil separada.
- **Chosen option:** NUMERIC(14,2) dinheiro, NUMERIC(10,3) quantidade com limites menores explícitos, ROUND_HALF_UP por linha e soma das linhas; BRL e strings JSON. DATE civil, TIMESTAMPTZ instantes UTC, business_today no timezone atual, Clock injetado.
- **Rationale:** evita erro binário e confusão de fuso em validade/vencimento; permite testes nos limites.
- **Consequences:** sem cálculo frontend autoritativo; EXPIRED/OVERDUE derivados; timezone alterado afeta futuras regras civis, snapshots guardam timezone histórico.
- **Rejected alternatives:** floats, persistir EXPIRED/OVERDUE, chamadas de relógio espalhadas.
- **Revisit trigger:** multi-moeda/impostos/apuração financeira POST-V1.

**Correção B02:** BusinessProfile permite onboarding com trade_name/phone/email/address/timezone NULL, sem empty sentinel. is_complete é derivado de exatamente esses cinco campos válidos; logo opcional. Admin escolhe timezone IANA sem default de produção; America/Bahia existe só no seed Climatech/fixtures específicas. Sem timezone, business_today não é calculado por fallback: operações civis aguardam configuração, auth/profile/health continuam. Send/start exigem profile completo. Após escolha, timezone não pode ser limpa; após completude, campos essenciais não podem regressar a NULL, preservando execução/relatórios sem nova flag persistida. BP-01..03 verificam onboarding, validação e bloqueios.

## D06 — Histórico e documentos

- **Decision:** pontos de congelamento e atomicidade da conclusão.
- **Context:** cadastros mudam; proposta enviada e atendimento concluído precisam continuar explicáveis.
- **Options considered:** joins vivos no render; versioning engine; snapshots imutáveis pontuais.
- **Chosen option:** QuoteSnapshotV1 em send, ExecutionSnapshotV1 em start, ReportSnapshotV1 em complete; reportPENDING criado na transação; geração PDF posterior independente.
- **Rationale:** preserva o recebido/executado sem event sourcing e suporta falha de arquivo.
- **Consequences:** logos/evidências referenciadas retidas; READY arquivo/hash imutáveis; retry não relê cadastros; Cliente/Equipment archived sem delete comum.
- **Rejected alternatives:** re-render com dados atuais, reabrir COMPLETED, rollback da OS porque PDF falhou.
- **Revisit trigger:** correção formal de documento histórico ou retenção legal exigir processo aprovado, não overwrite.

## D07 — Arquivos, upload e autorização

- **Decision:** filesystem privado, sanitização e acesso.
- **Context:** imagens podem conter metadata/ataques e técnico só pode acessar sua OS.
- **Options considered:** pasta uploads pública; signed URLs/S3 agora; stream autenticado com adapter local.
- **Chosen option:** FileStorage mínimo put_new/open_read/delete_unreferenced; bytes8MiB, lados8192/pixels20M, JPEG/PNG/WebP estáticos, reencode JPEG85/lado2560 sem metadata; logo PNG512 separado; escopo validado antes de stream.
- **Rationale:** atende filesystem persistente v1 e permite adapter futuro sem expor paths.
- **Consequences:** subprocesso decoder limitado, output imutável, compensação/coleta24h e backup DB+volume; sem SVG/HEIC/animados.
- **Rejected alternatives:** confiar em extensão/MIME cliente, persistir original, servir /uploads, criar sistema genérico de documentos.
- **Revisit trigger:** volume/capacidade demandar S3/R2 POST-V1; preservar autorização e keys opacas. H02 também exige revisão explícita se aquisição de foto em iPhone/Safari suportado não cumprir Hero Flow.

**Gate H02:** UP-11 em CL-05 e CL-06 usa iPhone real/Safari suportado, captura câmera e seleção biblioteca pelo input web, upload ServiceEvidence e conclusão do Hero Flow. Registra MIME/formato efetivamente entregues, sem antecipar resultado. HEIC permanece fora do escopo; se for entregue em ambiente suportado e falhar, release bloqueada até **A)** suporte seguro autorizado a HEIC ou **B)** revisão explícita da support matrix, seguida de nova verificação. Emulação/JPEG pré-convertido não prova esse gate.

[Pillow Image](https://pillow.readthedocs.io/en/stable/reference/Image.html) documenta decode e proteção contra decompression bombs. Valores de bytes/pixels/tempo aqui são limites do projeto; não alegam desempenho medido nem que Pillow sozinho forneça isolamento de processo.

## D08 — Biblioteca PDF fechada

- **Decision:** renderer de ServiceReport.
- **Context:** apenas relatório PDF privado, pt-BR/imagens/logo/tabelas/quebras; execução em Docker/CI.
- **Options considered:** fpdf2 programático; WeasyPrint HTML/CSS; navegador headless.
- **Chosen option:** fpdf2 2.x, texto/tabelas/imagens explícitos, Noto Sans local, sem HTML/URL de usuário; CLI mesma imagem backend; testes de layout em CL-05.
- **Rationale:** escopo de relatório cabe no renderer programático e dispensa browser/Pango. Documentação suficiente para decidir sem spike de produção.
- **Consequences:** layout de relatório separado da UI web; páginas e tabelas precisam de implementação/testes; bytes do primeiro sucesso retidos, sem promessa de render determinístico entre versões.
- **Rejected alternatives:** WeasyPrint adicionaria dependência de sistema/HTML sem necessidade de reutilizar layout web; headless browser ampliaria peso/controle operacional. Não se alega que alternativas sejam inseguras em si.
- **Revisit trigger:** teste CL-05 demonstre incapacidade de atender contrato; justificar mudança do adapter conservando ReportSnapshot/HTTP. Mudança estrutural exige CR.

| Critério | fpdf2 escolhido | WeasyPrint considerado |
|---|---|---|
| Docker/CI | Python e dependências de imagem/fontes; sem browser | Python+Pango e dependências de sistema |
| Unicode pt-BR | Fontes Unicode TrueType locais | Fontes/layout HTML/CSS |
| Imagem/logo/tabela/página | Recursos documentados, composição programática | Adequado ao modelo HTML/CSS; não necessário aqui |
| Previsibilidade | Layout controlado pelo renderer/fixtures | Depende de CSS/layout e ambiente |
| Segurança | Sem busca remota/HTML; streams internos | Exigiria controlar recursos/HTML igualmente |
| Manutenção | Docs/changelog oficiais disponíveis | Docs oficiais disponíveis |
| Custo operacional | Escolha proporcional ao relatório v1 | Rejeitado por dependências adicionais neste caso |

Recursos fpdf2 verificados em [documentação principal](https://py-pdf.github.io/fpdf2/), [Unicode](https://py-pdf.github.io/fpdf2/Unicode.html) e [segurança](https://py-pdf.github.io/fpdf2/Security.html). Dependência Pango verificada em [WeasyPrint first steps](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html). Menor custo operacional aqui é inferência arquitetural da lista de dependências, não benchmark. Compatibilidade prática, qualidade visual e limite60s/30MiB serão verificados CL-05. **Decisão definitiva, nenhuma provisional but non-blocking necessária.**

## D09 — Jobs, alertas e rate limiting

- **Decision:** execução periódica sem broker.
- **Context:** exatamente três automações comerciais, com catch-up, idempotência e resolução; API precisa de limites entre processos.
- **Options considered:** BackgroundTasks/timers API; Celery/Redis; CLI+cron e PostgreSQL.
- **Chosen option:** automations5min, followup72h/upcoming24h/overdue civil, reavaliação do estado completo em lotes200, advisory lock global; alert único por regra/alvo pela vida toda com reativação. Report CLI1min e maintenance diário são técnicos. Rate fixed-window persistido atômico em tabela técnica.
- **Rationale:** banco já obrigatório dá constraints/locks e proteção consistente entre workers, sem infraestrutura adicional.
- **Consequences:** catch-up preserva pendências ainda existentes; sem alert retroativo resolvido; tolera falha até próximo run, monitorar15min sem sucesso; rate falha fechado.
- **Rejected alternatives:** watermark isolado que perde condição, request BackgroundTasks scheduler, event bus/fila externa, rate só na memória.
- **Revisit trigger:** volume comprovado exceder capacidade de polling/contadores; sem revisão por preferência abstrata.

**Correção H01:** ausência de Charge em OS COMPLETED não entra em attention nem gera alerta/dívida. Registrar cobrança segue contextual; lista/indicadores financeiros usam somente Charge existente. Não criar billing_required/dismissed/novo estado para compensar uma pendência artificial. API-04 prova que serviço legitimamente sem cobrança pode encerrar sem essa pendência; não altera as três automações.

## D10 — Componentes e browsers

- **Decision:** foundation de UI acessível/customizável.
- **Context:** baseline visual próprio, React/Tailwind, três experiências.
- **Options considered:** primitives próprias completas; Radix direto; shadcn selecionado baseado em Radix; template de dashboard.
- **Chosen option:** wrappers ClientOps com componentes shadcn/Radix selecionados e HTML nativo; tokens/estados/foco normativos, sem template inteiro; browsers modernos com política e floors em UI_UX.
- **Rationale:** evita reimplementar dialog/foco, conserva customização Tailwind e layout action-first.
- **Consequences:** código copiado é mantido pelo projeto; acessibilidade depende da composição; browser antigo fica fora; auditoria quatro viewports/manual.
- **Rejected alternatives:** dashboard default, sidebar Admin no técnico, suíte genérica pesada e primitives complexas feitas do zero.
- **Revisit trigger:** bug/compatibilidade exige substituir primitive dentro do wrapper sem mudar contrato visual/acessível.

**Esclarecimento M02:** /q conserva CSP estrita independente dos componentes privados. script-src 'unsafe-inline' é proibido em todas as rotas. Style inline privado somente quando necessidade mínima for demonstrada/documentada por componente, diretiva e rota, com verificação CL-01/CL-02 (SEC-05). Preferir wrapper/CSS; nenhuma exceção pré-aprovada, nenhum relaxamento global para Radix. Se atributo de estilo exigir exceção, restringir a style-src-attr do documento privado sem ampliar style-src-elem/script-src/público. A [especificação CSP3](https://www.w3.org/TR/CSP3/) distingue os controles; o escopo de exceção é decisão local.

[shadcn Tailwind4/React19](https://ui.shadcn.com/docs/tailwind-v4) confirma caminho compatível. [Radix accessibility](https://www.radix-ui.com/primitives/docs/overview/accessibility) descreve suporte a comportamento/foco/ARIA, sem certificar a aplicação. [Tailwind compatibility](https://tailwindcss.com/docs/compatibility) fundamenta floors; metas WCAG vêm de [WCAG2.2](https://www.w3.org/TR/WCAG22/).

## D11 — Runtimes, testes e CI

- **Decision:** linhas estáveis e validação fiel à produção.
- **Context:** CL-01 precisa iniciar sem redescobrir ambiente/framework; nenhum pacote pode ser instalado em CL-00.
- **Options considered:** newest sem lock; versões fixas de patch sem resolução; linhas suportadas+locks verificados.
- **Chosen option:** Python3.13, Node24/npm11, PostgreSQL17; demais linhas em ARCHITECTURE; patches/digests resolvidos e registrados em CL-01. PostgreSQL real isolado em integration, FakeClock, CI progressivo até E2E3 engines/Compose.
- **Rationale:** estabilidade e reprodução sem inventar matriz instalada; testes exercitam constraints reais.
- **Consequences:** resolver/testar locks é trabalho CL-01, não pendência estrutural; sem SQLite para integração; autogenerate revisado e drift obrigatório.
- **Rejected alternatives:** coverage como único gate, banco diferente de produção, latest deploy, claim de CI executado sem implementação.
- **Revisit trigger:** linha sem suporte/security fix ou incompatibilidade comprovada; mudança registrada antes de upgrade major.

Suporte de linhas verificado em [Python versions](https://devguide.python.org/versions/), [Node releases](https://nodejs.org/en/about/previous-releases) e [PostgreSQL versioning](https://www.postgresql.org/support/versioning/). [Vite8](https://vite.dev/blog/announcing-vite8) e [guia Vite](https://vite.dev/guide/) verificam a linha e requisito Node. [FastAPI releases](https://fastapi.tiangolo.com/release-notes/) documenta linha escolhida/Pydantic2. As versões são baseline deliberado, sem afirmar que todas sejam a última release.

Linhas frontend também conferidas em [TypeScript5.9](https://www.typescriptlang.org/docs/handbook/release-notes/typescript-5-9.html), [React Router7 declarativo](https://reactrouter.com/7.18.4/start/declarative/installation) e [Vitest4](https://v4.vitest.dev/guide/). Router7/Vitest4 são linhas deliberadamente anteriores às principais mais recentes, com documentação disponível; a matriz instalada/patch de segurança permanece gate CL-01. Não usar comandos de scaffolding latest que troquem silenciosamente essas majors.

## D12 — Topologia, configuração e recuperação

- **Decision:** deploy local simples com fronteiras privadas.
- **Context:** uma empresa, um host, arquivos históricos, secrets fora do frontend.
- **Options considered:** publicar API/storage separadamente; containers com bootstrap implícito; Compose com etapas explícitas.
- **Chosen option:** web/proxy, API, db, migration one-shot, scheduler CLI; volumes DB/files privados; mesma origem; catálogo required/optional/secret/public validado; backup coordenado diário.
- **Rationale:** atende docker compose up e separa DDL/runtime/segredos sem plataforma complexa.
- **Consequences:** zero conta default, CLI Admin explícita, API não serve se migration/config falhar; sem HA e com obrigação de restore testado.
- **Rejected alternatives:** volume público, secrets VITE_, dependência externa para fluxo básico, upload público, promessa de multi-host.
- **Revisit trigger:** necessidade operacional mensurada de HA/storage remoto, classificada POST-V1.

## Cobertura das 40 decisões obrigatórias

| # | Decisão fechada | Fonte normativa |
|---|---|---|
| 1 | Backend módulos por domínio/serviços/repos concretos | ARCHITECTURE — Monorepo |
| 2 | Frontend features, wrappers e layouts por persona | ARCHITECTURE — Monorepo |
| 3 | /api/v1 e additive-compatible v1 | API — Convenções |
| 4 | Envelope error/code/message/fields/details/request_id | API — Envelope |
| 5 | Offset page1,size20,max100 e sort allowlist | API — Convenções |
| 6 | ETag/If-Match + locks raiz + constraints | API/ARCHITECTURE |
| 7 | NUMERIC14,2/quantity10,3 e HALF_UP por linha | DOMAIN — Dinheiro |
| 8 | Argon2id65536KiB,t3,p4,salt16,hash32 | SECURITY — Senhas |
| 9 | 15–128chars/512bytes, blocklist, sem composição | SECURITY — Senhas |
| 10 | Idle1800s | SECURITY — Sessão |
| 11 | Absolute43200s | SECURITY — Sessão |
| 12 | Touch60s/rotação login e password change | SECURITY — Sessão |
| 13 | __Host-cookie/Secure/HttpOnly/Lax/Path=/host-only | SECURITY — Sessão |
| 14 | HMAC-CSRF header + origem/fail-closed | SECURITY — CSRF |
| 15 | ASCII local/IDNA domain/lowercase/254/unique | SECURITY/DOMAIN |
| 16 | Quote256bits/fragmento/memória/Authorization | SECURITY — Bearer |
| 17 | TTL30dias/revoke/rotate/cancel | DOMAIN/SECURITY |
| 18 | QuoteSnapshotV1 no send | DOMAIN — Quote |
| 19 | ExecutionSnapshotV1 no start/endereço próprio | DOMAIN — OS |
| 20 | ReportSnapshotV1 no complete e READY imutável | DOMAIN — Report |
| 21 | put_new/open_read/delete_unreferenced/filesystem | ARCHITECTURE — FileStorage |
| 22 | Evidência8MiB/logo2MiB | SECURITY — Upload |
| 23 | Evidência8192lado/20Mpx, output2560 | SECURITY — Upload |
| 24 | JPEG/PNG/WebP estáticos; nãoSVG | SECURITY — Upload |
| 25 | JPEG85/RGB/sem metadata; logoPNG512 | SECURITY — Upload |
| 26 | fpdf2/NotoSans/CLI privado | D08/ARCHITECTURE |
| 27 | Management commands+cron, sem broker | ARCHITECTURE — Jobs |
| 28 | Três automações cada5min,72h/24h/date | DOMAIN — Automações |
| 29 | Reavaliar todo conjunto atual/lock/upsert | DOMAIN/ARCHITECTURE |
| 30 | Uma linha por type/target, reativa mesma | DOMAIN — Alert |
| 31 | PostgreSQL fixed-window/HMAC scopes/valores | SECURITY — Rate limits |
| 32 | shadcn/Radix selecionados/wrappers próprios | UI_UX/D10 |
| 33 | Modernos atual/anterior+floors, Safari real e gate foto câmera/biblioteca UP-11 | UI_UX/TESTING |
| 34 | PG17 databases isolados por worker | TESTING — Camadas |
| 35 | Clock injetado/instante único/fake test-only | DOMAIN/TESTING |
| 36 | DAG lint/type/test/migration/build/E2E/smoke | TESTING — CI |
| 37 | web/api/db/migrate/scheduler +2volumes | ARCHITECTURE — Docker |
| 38 | Catálogo required/optional/secret/public; profile nullable no onboarding/timezone explícita | ARCHITECTURE/DOMAIN — Config |
| 39 | Preview read-only e save200+warnings | API — Agenda |
| 40 | USER/CUSTOMER_QUOTE_LINK/SYSTEM_AUTOMATION e allowlist | DOMAIN — Timeline |

## Decisões provisórias, CRs e evidência

As correções dos sete findings estão consolidadas para reauditoria; matriz de resolução/evidências em PHASES. Não há decisão estrutural provisória criada pelo FIX. Git/toolchain ainda indisponíveis são impedimento operacional explícito para CL-01, não autorização para instalar/bootstrap nesta correção. Patches de lock, desempenho, PDF e gate real iPhone são verificações futuras, sem autorização para mudar baseline silenciosamente. Suporte HEIC ou mudança da support matrix só poderá ser decidido explicitamente se o gate H02 exigir; não é funcionalidade adicionada agora.

As fontes de biblioteca acima foram consultadas no CL-00 original; Web Share/CSP3 foram consultadas na correção CL-00-FIX. Nenhum benchmark, teste de produto, dispositivo iPhone, instalação, Docker ou CI foi executado nesta correção. Afirmação de compatibilidade empírica desta aplicação permanece **não verificada** até os gates correspondentes; recursos documentados de biblioteca não equivalem a sucesso da aplicação.

Riscos residuais concretos: host/volume único e restore necessário; link pode ser encaminhado por quem o possui; custos Argon2/decode e layout PDF ainda precisam das medições/fixtures previstas; compatibilidade da aquisição de foto real em iPhone aguarda UP-11, sem presumir formato. Root corrigido, limitação Git/toolchain e read-first estão em PHASES, sem inventar branch/HEAD/diff.
