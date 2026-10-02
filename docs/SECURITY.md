# ClientOps — segurança v1.0

Requisitos normativos; testes em [TESTING](TESTING.md), HTTP em [API](API.md), campos persistidos em [DOMAIN](DOMAIN.md). Segurança não depende de controles de frontend.

## Senhas e provisionamento

Argon2id via argon2-cffi, parâmetros explícitos: memory_cost=65536 KiB (64 MiB), time_cost=3, parallelism=4, salt_len=16 bytes CSPRNG por hash, hash_len=32 bytes. Persistir string PHC completa. Rehash após login válido se parâmetros/algoritmo diferirem; nunca reduzir silenciosamente. Dummy hash válido com mesmos parâmetros para usuário inexistente; conta DISABLED ou temporária expirada usa verificação equivalente e erro genérico. Não prometer tempos exatamente idênticos.

Senha permanente: 15..128 caracteres Unicode, até 512 bytes UTF-8; espaços e colar/gerenciadores permitidos, sem trim, casefold ou normalização Unicode, sem composição artificial ou expiração periódica. Rejeitar senha igual à atual e lista local versionada de senhas comuns; não enviar senha a serviço externo. Mensagem de validação não ecoa entrada. Login tem limite pré-hash e no máximo duas verificações Argon2 simultâneas por processo; excedente retorna 429 com retry, sem fila sem limite. Medir custo no container alvo em CL-02, sem benchmarks inventados ou rebaixamento automático.

Comando create_admin lê senha por TTY sem echo, nunca argumento/env/log; transação serializa bootstrap e verifica unicidade. Admin adicional exige opção explícita do comando. Primeiro Admin recebe senha escolhida forte e must_change_password=false. Reset de emergência é comando restrito ao operador da instalação, mesmas regras de revogação; não há recuperação por e-mail.

Admin cria técnico/reset usuário: servidor gera 24 bytes CSPRNG, base64url sem padding (32 caracteres), exibe uma vez na resposta no-store, nunca recuperável. Persiste só Argon2, must_change_password=true e temporary_password_expires_at=now+24h. Admin entrega por canal externo, UI oferece copiar e limpa ao fechar. Reset não habilita conta DISABLED. Transação troca hash, revoga TODAS as sessões e registra evento sem credencial.

Login com temporária ainda válida cria sessão restrita. Enquanto must_change_password=true, allowlist exata: GET /auth/session, POST /auth/change-password e POST /auth/logout; assets estáticos e health são públicos por natureza. Todo outro recurso autenticado retorna 403 PASSWORD_CHANGE_REQUIRED, inclusive GET profile/agenda e uploads. Expiração da credencial temporária também invalida uso dessa sessão restrita. Change-password exige senha atual, nova válida, CSRF e origem; bloqueia User, revoga todas as sessões, limpa flag/expiry, grava hash e emite nova sessão/cookie/CSRF. Sem janela que permita reutilizar a sessão antiga após commit.

Login por e-mail: trim externo, validação sintática sem consulta DNS, domínio IDNA ASCII, local-part ASCII, lowercase do endereço inteiro, máximo 254 bytes. Não remover +tags nem pontos. Contrato define login case-insensitive inclusive local-part; UNIQUE email_normalized e CHECK lowercase/trim no PostgreSQL. E-mail de contato não é identidade e não é único. Mesmo normalizador na API, CLI, seed e testes.

## Sessão opaca

Gerar 32 bytes CSPRNG → base64url sem padding (43 chars). Cookie carrega raw bearer; banco guarda SHA-256 de 32 bytes com índice unique. Alta entropia dispensa Argon2 para tokens. Lookup pelo hash, nunca por ID previsível; comparar valores secretos com primitive constant-time quando comparação em memória for necessária.

Idle timeout 30 minutos; absolute timeout 12 horas desde criação. Expirado se now>=absolute_expires_at OU now>=last_seen_at+30min. Touch no máximo a cada 60 segundos em atividade autenticada autorizada, via update condicional monotônico, nunca depois de revoked_at/expiry. GET /auth/session, health e polling GET de report não renovam idle. Arredondamento conservador permite encerrar até 60 segundos antes da última atividade real; UX não promete precisão maior.

Login sempre gera sessão nova; cookie prévio não é promovido. Alteração de senha gera nova sessão e novo prazo absoluto. Não há refresh token nem rotação periódica de bearer durante requests comuns: evita corrida entre abas; timeout/revogação limitam exposição. Até cinco sessões ativas por User; sexto login revoga a mais antiga sob lock User. Logout revoga sessão atual e limpa cookie; chamadas sem sessão válida ainda limpam cookie e retornam 204 se origem válida.

Cada request privado verifica Session E User ACTIVE e restrição de senha, sem cache de autorização que permita bypass após desabilitar. Desabilitar revoga todas as sessões na mesma transação. Reabilitar não revive sessão. Reset/troca/logouts usam motivos internos allowlist. Rotação de CSRF_HMAC_KEY invalida tokens CSRF em memória, recuperáveis por GET session; revogação de sessões é procedimento separado.

Produção: cookie **__Host-clientops_session**, HttpOnly; Secure; SameSite=Lax; Path=/; sem Domain (host-only), Max-Age=43200. Expiração no servidor prevalece; touch não estende cookie/limite absoluto. Remover com mesmos atributos e Max-Age=0. Dev HTTP somente localhost usa nome clientops_session_dev, Secure=false e mesmas demais restrições; produção rejeita essa variante. Nenhum bearer/CSRF fica em localStorage, sessionStorage, IndexedDB, URL ou analytics.

## CSRF, origem e CORS

Todos POST/PUT/PATCH/DELETE autenticados por cookie exigem X-CSRF-Token. Token derivado HMAC-SHA256(CSRF_HMAC_KEY, raw_session_bearer) codificado base64url, retornado em login/GET session/change-password no corpo no-store e mantido em memória. Não é segundo cookie. Não deriva somente do ID público. HMAC validado constant-time; header ausente/inválido → 403 CSRF_FAILED.

Adicionalmente, unsafe requests devem ter Origin exatamente em TRUSTED_ORIGINS; se Origin ausente, usar origem parseada de Referer HTTPS confiável (HTTP localhost só dev); se ambos ausentes, Origin null ou inválidos, 403 ORIGIN_REJECTED. Origin presente e ruim nunca é compensado por Referer. Validar scheme/host/port, não prefixo textual; Host público é config, não dado do request. Sec-Fetch-Site cross-site é rejeitado como defesa adicional, sem depender da presença do header.

Login não tem sessão prévia: exige origem confiável, application/json e X-ClientOps-Request: browser-v1. Esses headers forçam preflight em origens externas; servidor nunca libera CORS a origem arbitrária. Login passa pelos limites próprios de instalação, IP e login normalizado; logout autenticado passa por PRIVATE_USER. Logout com sessão válida exige CSRF; sem sessão segue somente origem/header e não possui User key para PRIVATE_USER, permitindo limpar cookie expirado. GET nunca executa comando comercial.

Produção não necessita CORS; se configurado, somente origens explícitas, allow_credentials=true, headers mínimos, nunca wildcard/refletir Origin. Dev prefere Vite proxy; alternativa explícita localhost:5173→localhost:8000 com credenciais e origins definidos. API recebe apenas JSON (exceto multipart de upload); rejeita forms para comandos JSON e application/x-www-form-urlencoded. Docs interativas somente dev ou Admin autenticado.

Público quote usa Authorization: Bearer, credentials omit, não sessão: não exige CSRF, pois segredo não é ambient authority. POST público ainda exige origem confiável e JSON. Backend ignora cookie ao resolver autenticação pública; nunca aceita sessão Admin como alternativa ao bearer de quote. OPTIONS não autentica dado, só responde à allowlist.

## Autorização por objeto e projeções

| Recurso/ação | ADMIN | TECHNICIAN | CUSTOMER bearer |
|---|---|---|---|
| Perfil/usuários/clientes/equipamentos | Gerir conforme domínio | Sem endpoints de cadastro | Não |
| Quote/itens/link | Gerir | Não | Só ler projeção pública do próprio bearer (client {name}) e aprovar |
| Agenda | Geral e por técnico | Somente technician_id próprio imposto no servidor | Não |
| OS | Todas; criar/preparar/atribuir/cancelar | Ler próprias; start/checklist/notes/evidence/confirmation/complete nos estados válidos | Não |
| Evidência | Ler autorizada; mutar somente IN_PROGRESS | Idem, somente OS própria | Não |
| ServiceReport/PDF | Somente Admin autenticado | Só report_status na OS própria | Não |
| Charge/alert/dashboard | Admin | Não | Não |
| Timeline | Contextos administrativos | Eventos de execução permitidos da própria OS | Não |
| Conta | Própria senha/logout | Própria senha/logout | Sem conta |

Técnico recebe apenas Client {name,phone}, service_address da OS e equipamento {name,brand,model,serial_number,location_description}; descrições/técnico/agenda/checklist/observações/evidências/resolução necessários. Antes de start usa projeção atual mínima; depois usa execution_snapshot. Não recebe email, client.notes, outros equipamentos/OS, quote_id/commercial_snapshot/valores ou charge. DTO técnico não serializa execution_snapshot bruto. Recebe próprio histórico concluído/cancelado enquanto continua atribuído. Reatribuição antes de start remove imediatamente acesso do técnico anterior.

Role errado em coleção/módulo → 403 FORBIDDEN. ID de objeto inacessível para papel permitido → 404 NOT_FOUND indistinguível de inexistente; scoped query em todas leituras/streams. Sem autenticação em recurso privado → 401 AUTHENTICATION_REQUIRED antes de consultar ID. Criar/alterar nunca aceita role/status, created_by, completed_by, computed totals ou storage_key fora de schema explícito. Overposting é 422, não ignorado silenciosamente.

Minimização pública obrigatória: cliente do orçamento é **client {name}**, por allowlist de saída. client.phone, client.email, client.address, client.id e client.notes não podem existir no DTO público, inclusive como null, nem ser transportados em snapshot bruto, HTML/estado serializado ou erro. Snapshot interno pode preservar contatos/endereço/ID para Admin; não é serializado ao portador do link. business.trade_name/phone/email/address continuam públicos para identificação e contato da empresa. PUB-09 testa essa fronteira mesmo com todos os dados internos preenchidos e link encaminhado para outro contexto anônimo.

## Bearer público e compartilhamento

Quote secret: 32 bytes CSPRNG, base64url 43 caracteres; SHA-256 somente no banco. Expiração now+30 dias, revogação/rotação conforme DOMAIN. Emissão entrega URL **https://host/q#token=<secret>** uma única vez no corpo de send/rotate, com Cache-Control:no-store. GET Admin de Quote nunca recupera raw link. Se resposta se perder, consultar estado e rotacionar; não reconstruir de hash. Um link não revogado por quote. Terminal APPROVED continua legível até token vencer/revogar, mas não admite nova emissão.

Frontend /q lê fragmento antes de montar componentes, valida formato, copia para variável fechada em memória e imediatamente history.replaceState para /q. Não usar query router, persistência, error breadcrumbs ou devtools de query. Refresh sem link pede reabrir link recebido. Token não aparece em API path/query/referrer; cada GET/POST usa Authorization: Bearer. Assets/erros/console não recebem token. Public GET não registra evento viewed; logs de acesso não são prova comercial de leitura.

Compartilhar pelo WhatsApp: primeiro copiar link completo para clipboard em gesto explícito; abrir WhatsApp/WhatsApp Web com mensagem pré-preenchida **sem o link/segredo**, por exemplo “Olá! Segue o orçamento da Climatech Serviços.”; Admin cola o link no chat antes de enviar. É proibido colocar URL com token em wa.me?text ou outra query string. Isso cumpre simultaneamente mensagem pré-preenchida e proibição de segredo em query. Abrir nova aba com noopener,noreferrer. Browser/clipboard/aplicativo externo passam a ser fronteiras de confiança por escolha de compartilhamento; posse do link autoriza aprovação, não comprova identidade civil.

Web Share API pode complementar o fluxo Admin como **OPTIONAL/NON-BLOCKING**, em contexto seguro e após gesto explícito, somente quando detectada como disponível. Entregar ao share sheet nativo o link completo com fragmento já mantido em memória, sem converter o bearer em query, persistir payload ou usar intermediário/telemetria. A escolha do destino é do Admin; não comprova entrega nem identidade. Cancelamento/falha/indisponibilidade mantém Copiar link disponível, sem envio automático ou cópia sem gesto. A base permanece funcional sem Web Share; não altera permissões do cliente público. Contrato de UX em UI_UX.

Público bearer desconhecido/malformado/expirado/revogado/cancelado → mesmo 401 PUBLIC_ACCESS_INVALID, sem motivo detalhado ou revelar existência. Bearer válido + SENT comercialmente vencido → GET 200 com is_expired=true e POST 409 QUOTE_EXPIRED. Repetição APPROVED conforme DOMAIN. Não persistir IP/User-Agent de cliente para inventar assinatura jurídica.

Headers produção para HTML /q e respostas públicas: Referrer-Policy:no-referrer; Cache-Control:no-store; X-Content-Type-Options:nosniff; X-Frame-Options:DENY. CSP pública: default-src 'self'; script-src 'self'; style-src 'self'; style-src-elem 'self'; style-src-attr 'none'; img-src 'self' blob:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'. Sem scripts inline, CDN/font/analytics/telemetry terceirizados. Public logo é GET autenticado por bearer, convertido em blob URL na memória; nunca img src contendo bearer. /q mantém essa política estrita sem relaxamento para componentes Admin.

CSP privada parte da mesma restrição. **script-src 'unsafe-inline' permanece proibido**, inclusive na política privada e no fallback de SPA. Se um componente privado precisar de style inline, primeiro adaptar o wrapper/CSS; exceção só com necessidade demonstrada, mínima e documentada em SECURITY/DECISIONS na fase de implementação: componente/propriedade, motivo, alternativas, diretiva exata, rotas afetadas e testes. Quando estritamente necessária para atributos de estilo, limitar a style-src-attr no documento privado; não ampliar style-src-elem, script-src, default-src ou CSP global para corrigir Radix. Nenhuma exceção está concedida nesta correção.

Gates CL-01/CL-02 devem inspecionar headers efetivos do HTML de /q, /admin, /tech e login, inclusive deep-link/fallback, e testar componentes com a política aplicada. Como /q e app privado podem usar o mesmo build SPA, proxy seleciona a política pelo documento/rota sem herdar relaxamento privado no público. CSP de desenvolvimento/HMR não é evidência de política de produção; SEC-05 valida as duas fronteiras. Diretivas de script e estilo são controles distintos na [especificação CSP3](https://www.w3.org/TR/CSP3/).

Todas respostas privadas e auth no-store; PDFs/evidências no-store e nosniff. Static assets com hash podem ter cache immutable, desde que sem dados do usuário; HTML privado no-store. HSTS max-age=31536000 em produção após TLS verificado, sem includeSubDomains automático. Sem service worker v1.

## Upload, filesystem e PDF

Uma imagem por request. Evidência: arquivo até **8 MiB = 8388608 bytes**, request multipart até 9 MiB; proxy e app contam bytes reais em streaming inclusive sem Content-Length. JSON até 256 KiB; headers até 16 KiB. Autorizar OS antes de processar corpo, sem confiar só na UI. Rota de upload deve validar cookie/origem/CSRF/path/escopo antes do parser multipart; não depender de parâmetro UploadFile/Form que faça parsing antecipado. Orquestração de streaming pode ser async localmente, chamando serviço ORM síncrono no threadpool; decoder fica em subprocesso. Parser aceita um arquivo e campos allowlist limitados, rejeita partes extras, conta bytes e limpa staging em disconnect. .jpg/.jpeg/.png/.webp e MIME declarado correspondente image/jpeg|png|webp, assinatura e decoder precisam concordar. Nomes externos descartados, extensão nunca define path.

Pipeline: limite → allowlist de extensão → MIME → magic bytes → abrir header/limites → decode integral → orientação EXIF → conversão RGB → reencode → persistência privada. Pillow com formatos explicitamente selecionados, warning/error de decompression bomb como rejeição; max 8192 px por dimensão, **20 milhões de pixels**, mínimo 1×1; um frame apenas, rejeitar APNG/WebP animado. Truncadas/inconsistentes são rejeitadas, sem LOAD_TRUNCATED_IMAGES. Decode isolado em subprocesso com 10 s/512 MiB, máximo dois em paralelo por instalação; excedente 429.

Sanitização evidencia: respeitar orientação antes de remover EXIF; reduzir proporcionalmente maior lado a 2560, sem ampliar; alpha composto sobre fundo branco; JPEG qualidade 85, RGB, sem EXIF/ICC/XMP/comentários. Validar output <=8 MiB, sem metadados, guardar hash/dimensões/mime calculados. Não guardar original. Formatos não suportados (SVG/GIF/PDF/HEIC) retornam 415; UI informa formatos antes do envio. HEIC permanece fora do escopo atual; não presumir o MIME/formato que Safari fornecerá.

H02 exige gate real UP-11 em CL-05 e CL-06: iPhone físico/Safari suportado, foto capturada na câmera e foto selecionada da biblioteca passam pelo input web, upload ServiceEvidence e conclusão do Hero Flow. Registrar MIME/formato efetivamente entregues, conforme TESTING. Se dispositivo/browser suportado entregar HEIC e o fluxo falhar, a release fica bloqueada até suporte seguro a HEIC autorizado ou revisão explícita da support matrix. Não ampliar allowlist/decode silenciosamente nem considerar fixture JPEG ou emulação substituto dessa prova.

Logo BusinessProfile: mesmo pipeline seguro, input até 2 MiB, dimensão até 2048×2048 e 4 milhões de pixels, estática JPEG/PNG/WebP; output PNG até 512×512, mantém alpha, até 2 MiB, sem metadata. Admin somente. Chave antiga retida se snapshot referenciar. Frontend pode pré-visualizar, mas servidor valida tudo.

Storage root fora do web root; diretórios 0700/arquivos 0600 para UID da aplicação. Proxy nunca serve /uploads; volume não está no frontend. IDs externos resolvem metadados via DB, aplicam autorização e só depois open_read. Adapter aceita exclusivamente chaves geradas internamente, root confinement e no symlink; jamais servir paths da URL. Download PDF usa filename fixo derivado de number, Content-Disposition:attachment. Evidência usa inline image/jpeg privado; não reutiliza nome original.

Renderer fpdf2 usa somente texto, fontes empacotadas e streams sanitizados, sem URL/file path fornecidos pelo usuário, HTML ou anexos executáveis. Dependências lockadas e scanner futuro; não é necessário antivírus para cumprir o contrato de reencode de imagens desta v1. PDF/storage failure não reabre OS; recovery em ARCHITECTURE.

## Rate limits e logs

PostgreSQL fixed-window atômico com contadores técnicos independentes de rollback comercial. Hora do Clock UTC, chave HMAC por IP normalizado/login/usuário/hash bearer. Aplicar todos os limites relevantes; request negada conta tentativa. Janelas fixas admitem até 2× limite em fronteira; valores são ponto inicial explícito para pequena operação, não resultado de benchmark. Não usar memória local como única proteção. DB do limiter indisponível → 503 em endpoints protegidos, sem fail-open.

| Ação | Limites iniciais | Motivo |
|---|---|---|
| Login | 30/15 min por IP; 10/15 min por login normalizado; 100/min por instalação | Limitar guessing e custo Argon2; falha genérica sem lock permanente |
| Público GET quote/logo | 120/min por IP e 60/min por hash bearer; instalação 600/min | Acomoda leitura/logo, limita varredura |
| Aprovar quote | 20/10 min por IP e 5/10 min por bearer; instalação 100/min | Cliques/retries moderados, sem spam de comandos |
| Upload/logo | 20/10 min por usuário e 100/10 min por instalação; 2 decodes simultâneos | 20 imagens/OS e teto de CPU/memória |
| Reset senha | 10/h por Admin | Evitar revogação abusiva |
| Demais privadas | 600/5 min por usuário | Operação humana e listagens |

IP somente de proxy confiável; não confiar em X-Forwarded-For do público. Chaves de limiter nunca logadas; buckets expiram e são limpos. Resposta 429 RATE_LIMITED e Retry-After segundos até janela liberar, sem expor bucket/email. Limite não deve revelar se login existe, pois aplica a ambos. Login global protege crescimento ilimitado de buckets. GETs públicos também passam limite por IP antes de criar bucket de bearer.

Logs JSON com timestamp UTC, level, request_id gerado/validado UUID, route template, method, status, duration_ms, user_id interno quando autenticado, código de erro e job/run_id. Nunca body/header completo, query, fragment, password, cookie, Authorization, CSRF, hash de credencial, endereço, foto, notas ou URL compartilhada. Proxy remove query do formato de log; app mascara também exceptions de validação que poderiam ecoar input. Erros inesperados guardam classe/stack técnico sanitizado sem locals/SQL params; resposta pública só request_id e erro genérico.

INFO eventos operacionais/autenticação; WARNING falha/rate/validação agregada; ERROR exceção sanitizada. Retenção 30 dias, acesso operador, rotação/capacidade; timeline é histórico de domínio com retenção do atendimento, não dump de logs. Segredos fornecidos fora do repositório; frontend nunca recebe DB URL/HMAC keys. Não há scanner terceirizado/analytics no fluxo público.

## Threat model e verificação

| Asset | Ameaça | Impacto | Mitigação | Verificação/teste |
|---|---|---|---|---|
| Conta | Credential stuffing/guessing | Acesso indevido/DoS | Argon2, política, dummy, limites pré-hash | AUTH-01..08; carga limitada CL-02 |
| Session | Roubo/fixation | Impersonação | CSPRNG/hash, cookie host-only/HttpOnly/Secure, novo login, expiração/revogação | AUTH-04..08; cookie e fixation |
| Estado autenticado | CSRF/login CSRF | Mudança sem intenção | Origem+token, JSON/header login, CORS restrito | SEC-01 todas unsafe methods |
| OS/evidência/report | Broken object authorization | Exposição de outro técnico | Scoped queries e filtro de payload | AZ-01..06; IDs cruzados em GET/HEAD/stream |
| Quote link | Vazamento | Aprovação por terceiro | Fragment→memória, sem logs/query, no-referrer, TTL/rotate | PUB-08 network/log scan e WhatsApp |
| Dados do cliente | Link encaminhado expõe cadastro | Exposição excessiva de dados pessoais | DTO público allowlist client {name}, snapshot interno privado | PUB-09 campos proibidos ausentes |
| Quote access | Brute force | Acesso público indevido | 256 bits, rate, erro uniforme | PUB-02..04, rate antes lookup |
| Volume/CPU | Upload abuse | Esgotamento | Limites streaming, quotas, subprocesso, throttle | UP-03/09; chunked/concorrência |
| Filesystem | Path traversal/symlink | Leitura fora do root | Keys opacas, root confinement, no symlink | UP-07/10 |
| Decoder | Image bomb/arquivo animado | OOM/hang | Pixels/dimensões/frames, deadline/processo | UP-04/09 |
| Browser/PDF | Conteúdo malicioso persistido | XSS/injeção/SSRF | Texto escapado, CSP, reencode, fontes/bytes locais | SEC-02; payload HTML/URL em notes |
| Papel | Privilege escalation | Admin indevido | role fixo, DTO allowlist, restrição temporária | AZ-03 e AUTH-08 |
| Timeline/log | Vazamento secundário | PII/segredos acessíveis | Payload allowlist, DTO por papel, redaction | SEC-03 scans com canários |
| Domínio | Mass assignment | Status/totais/owner falsos | Schemas extra=forbid, service validation | API-03 overposting |
| Recursos | Rate abuse | Indisponibilidade | DB buckets atômicos, proxy confiável, tetos instalação | SEC-04 workers simultâneos |
| Estados | Stale/concurrent transitions | Duplicação/perda/histórico incorreto | If-Match, locks raiz, uniques, snapshot transacional | CON-01..07 duas conexões reais |
| Snapshot/backup | Perda de arquivos | Histórico indisponível | Arquivos imutáveis, referências e restore testado | REP-04 e OPS-02 |

Riscos residuais concretos: quem recebe/obtém link pode aprovar; clipboard/WhatsApp estão fora do controle da aplicação. Um host/volume requer backup e monitoramento; não há HA. Layout PDF e custo de decode/hash dependem do container alvo e têm gates posteriores. Nenhuma dessas limitações abre decisão estrutural de CL-00.

## Controles implementados na Foundation CL-01

O Nginx serve todos os documentos com a política `default-src 'self'; script-src 'self'; style-src 'self'; style-src-elem 'self'; style-src-attr 'none'; img-src 'self' blob:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'`. O build não usa script ou atributo style inline. HTML recebe `no-store`, `no-referrer`, `nosniff` e `DENY`; assets com hash recebem cache imutável. HTTPS acrescenta HSTS `max-age=31536000` sem `includeSubDomains`.

A rede `edge` é `172.28.0.0/28`; somente o endereço fixo do Nginx `172.28.0.2/32` consta em `TRUSTED_PROXY_CIDRS`. O middleware remove `X-Forwarded-*` de origem não confiável. Testes cobrem request via proxy e request direto com headers forjados. A API e o proxy executam sem root, somente o web publica porta, o readiness não é exposto e segredos não aparecem no frontend, histórico de imagens ou logs examinados.

O volume privado fica fora do web root, montado somente pela API e operado como UID 10001. CL-01 testa apenas confinamento/permissões e o probe efêmero do readiness; upload, FileStorage operacional e arquivos de domínio permanecem CL-05.

## Controles implementados na CL-02

CL-02 implementa Argon2id pelos parâmetros normativos, semaphore não bloqueante de duas operações, dummy PHC, blocklist local, normalização central de e-mail ASCII/IDNA e comandos TTY `create_admin`/`reset_password`. O benchmark real na imagem `clientops-api:latest` (Python 3.13.15, Linux x86_64, glibc 2.36) executou um warm-up e três amostras em 01/10/2026. Hash: mínimo 84,854 ms, mediana 85,331 ms, máximo 117,381 ms. Verify: mínimo 85,134 ms, mediana 85,349 ms, máximo 109,610 ms. `ru_maxrss` observado: 108644 KiB. Comando: `docker run --rm --network none --entrypoint python clientops-api:latest -m app.cli.benchmark_argon2 --samples 3`. Os parâmetros não foram alterados pela medição.

Sessões usam bearer CSPRNG de 32 bytes, cookie HttpOnly/Lax e somente SHA-256 no banco; idle 1800 s, absolute 43200 s, touch 60 s e cap de cinco sob lock do User. Comandos privados mantêm autorização, revalidação do User/Session e operação na mesma transação, serializados por advisory lock para que troca de senha, reset e disable não deixem um comando antigo continuar. Produção/demo usam `__Host-clientops_session; Secure`; desenvolvimento HTTP aceita somente localhost; o ambiente de teste Compose possui origem interna explícita. Origin/Referer e CSRF HMAC protegem toda mutation por cookie. O proxy confiável aceita exatamente um IP validado/normalizado e peers não confiáveis perdem `X-Forwarded-*`; logs recebem apenas o IP validado.

Os buckets fixed-window guardam HMAC das chaves e não possuem limpeza automática na CL-02. A manutenção de buckets expirados por mais de 24 h permanece CL-05; decisões da janela corrente ignoram buckets de outras janelas pela chave primária temporal.

## Controles implementados na CL-03

Todas as rotas Client/Equipment/timeline exigem Admin antes do lookup; Técnico recebe 403 e IDs cruzados de Equipment recebem 404 uniforme. Queries de Equipment incluem simultaneamente `client_id` e `id`, e o schema rejeita `client_id` no corpo. A role runtime não pode atualizar ownership, IDs, `created_at` nem deletar; Client/Equipment usam grants UPDATE por coluna e timeline continua append-only.

Mutations preservam Origin/CSRF da CL-02 e usam ETag, lock PostgreSQL e ordem Client→Equipment. Payload de timeline contém somente `equipment_id` e nomes de campos; valores de phone/email/address/notes não entram. Logs da aplicação usam route template sem query/body, e o formato nginx registra `$request_method $uri $server_protocol`, removendo argumentos. O E2E CL-03 desativa trace e screenshot para que os canários privados não sejam publicados.
