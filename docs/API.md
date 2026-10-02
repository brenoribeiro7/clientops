# ClientOps — contrato REST v1

Especificação HTTP do produto. Prefixo **/api/v1**; exemplos omitem host. [DOMAIN](DOMAIN.md) fixa campos, tipos, limites e regras; [SECURITY](SECURITY.md) fixa credenciais. CL-02 implementa health, auth/session, gestão de User e BusinessProfile listados abaixo. Os demais endpoints permanecem contratos de fases posteriores.

## Convenções

JSON UTF-8 em snake_case, enums uppercase, UUID strings, civil date YYYY-MM-DD, instantes RFC3339 UTC Z. Entrada temporal com offset obrigatório. Decimal sempre string, dinheiro com 2 casas e quantidade até 3, nunca number. Unknown fields retornam 422; omissão em PATCH mantém valor, null limpa apenas campo nullable. Sem PUT genérico de entidade, status livre, totals enviados pelo cliente ou JSON Patch.

Sucesso de recurso único: {data: resource, meta?:{warnings:[]}}. Listas: {data:[],page:{number,size,total,total_pages}}. Create 201 + Location, alteração/action 200, exclusão de filho/logout 204, retry PDF aceito 202. Todos JSON privados/públicos de dados têm Cache-Control:no-store. Streams usam headers específicos; erros sempre JSON. GET/HEAD não alteram estado comercial, exceto touch técnico de sessão permitido em SECURITY.

Versionamento de URL só muda por breaking change; campos novos opcionais/aditivos podem entrar em v1 com documentação. OpenAPI gerada do backend será revisada contra este contrato e tipos TS gerados em CL-01+, sem declarar OpenAPI já existente.

Paginação page>=1 default 1, page_size 1..100 default 20; páginas fora do total retornam [] com metadados. Offset é suficiente à instalação pequena; não promete snapshot entre páginas sob inserções. sort default -created_at,id, nomes allowlist por recurso, tie-break id sempre presente; '-' desc. Search q de 2..100 chars em name/number/description permitidos, case-insensitive literal, sem interpretar %/_ como wildcard do usuário. Queries parametrizadas, sem SQL livre. Filtros desconhecidos ou valores fora do enum retornam 422.

Estado derivado não substitui status: quote tem is_expired, charge tem is_overdue; filtros is_expired/is_overdue boolean combinam condição em DOMAIN. Metadados de leitura incluem server_now e business_today quando usados em decisões temporais. Agenda usa from/to RFC3339 e interseção de intervalos, janela máxima 31 dias; app monta hoje/semana em timezone da empresa.

Timezone ainda não escolhida no onboarding é null, nunca default. Se a operação precisa de business_today ou agenda local, retorna 409 BUSINESS_PROFILE_INCOMPLETE; isso inclui dashboard e validações de limites civis de Quote/Charge. Operações sem essa dependência, como auth, profile e Client/Equipment, continuam disponíveis; metadados opcionais usam business_timezone:null/business_today:null e server_now UTC. Send de Quote e start de ServiceOrder exigem adicionalmente is_complete=true para os cinco campos do profile definidos em DOMAIN. Nenhum fallback do host/browser preenche o campo.

### Concorrência, idempotência e limites

GET de agregado mutável retorna ETag forte "v7" e version:7 no DTO. PATCH e ações de estado privadas exigem If-Match com exatamente uma tag atual; ausência 428 PRECONDITION_REQUIRED; mismatch 412 VERSION_CONFLICT com current_version, sem aplicar parcialmente. Após autorização, lock da raiz, comparação e regra de estado; 409 se estado incompatível com versão atual. Mutar filho usa ETag da OS/Quote, incrementa raiz e devolve ETag atualizado, inclusive 204. Session/limiter/timeline não expõem ETag.

Exceções explícitas: create não exige If-Match; auth não exige (tem senha/CSRF/lock); aprovação pública não exige (idempotência por quote/token); retry de report não exige (lock/idempotência por report); acessos públicos administrativos usam expected_access_id, conforme tabela, sem alterar versão comercial. Generic create POST não é automaticamente idempotente. UI desabilita duplo clique, não faz retry silencioso após falha de rede; relê lista para reconciliação. Constraints únicas protegem quote→OS e OS→charge; duplicata retorna 409 ALREADY_EXISTS com ID acessível existente.

Send de Quote é uma transição única; repetir após sucesso resulta 412 se versão antiga ou 409 QUOTE_NOT_DRAFT se atual. Não reexibe bearer. Start/complete com versão antiga retornam 412; reler revela resultado. Mark-paid já PAID com versão atual retorna 200 sem novo evento; cancel/archive/restore repetidos na mesma situação com versão atual retornam 200 sem evento. Estado diferente desejado e terminal resulta 409. Repetição de aprovação pública é 200 estável enquanto bearer válido.

JSON máximo 256 KiB, headers 16 KiB; multipart limites SECURITY; request malformada 400, tipo de mídia 415, payload 413, validação 422. Rate 429 com Retry-After. Requests devem enviar X-Request-ID UUID opcional; servidor gera quando ausente/inválido, ecoa X-Request-ID. Nunca enviar bearer em URL/query.

### Envelope de erro

~~~json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Revise os campos indicados.",
    "fields": [{"path":"items.0.quantity","code":"OUT_OF_RANGE","message":"Informe uma quantidade válida."}],
    "details": {},
    "request_id": "df98e42e-6f64-4b69-9cba-02cc8d7aa42a"
  }
}
~~~

message humana pt-BR; code estável; fields=[] quando não aplicável; details só allowlist (current_version, pending_item_ids, current_status, existing_id, missing_fields). missing_fields contém apenas nomes de campos BusinessProfile faltantes, sem seus valores. Nunca incluir input rejeitado, SQL, traceback, tokens, paths, nome de arquivo ou dados de objeto inacessível.

| HTTP | Códigos estáveis principais |
|---|---|
| 400 | MALFORMED_REQUEST |
| 401 | INVALID_CREDENTIALS, AUTHENTICATION_REQUIRED, PUBLIC_ACCESS_INVALID |
| 403 | FORBIDDEN, PASSWORD_CHANGE_REQUIRED, CSRF_FAILED, ORIGIN_REJECTED |
| 404 | NOT_FOUND |
| 409 | INVALID_STATE, QUOTE_NOT_DRAFT, QUOTE_EXPIRED, ACCESS_CHANGED, ALREADY_EXISTS, CLIENT_ARCHIVED, EQUIPMENT_ARCHIVED, CHECKLIST_INCOMPLETE, COMPLETION_REQUIRED, BUSINESS_PROFILE_INCOMPLETE, LAST_ADMIN_REQUIRED, REPORT_NOT_READY |
| 412 / 428 | VERSION_CONFLICT / PRECONDITION_REQUIRED |
| 413 / 415 | PAYLOAD_TOO_LARGE / UNSUPPORTED_MEDIA_TYPE |
| 422 | VALIDATION_ERROR, INVALID_IMAGE, IMAGE_DIMENSIONS_INVALID, MONEY_LIMIT_EXCEEDED |
| 429 | RATE_LIMITED |
| 500 / 503 | INTERNAL_ERROR / TEMPORARILY_UNAVAILABLE, RETRYABLE_TRANSACTION, STORAGE_UNAVAILABLE |

## DTOs e autenticação

A=ADMIN; T=TECHNICIAN com escopo da própria OS; P=bearer público de Quote; S=sessão autenticada inclusive restrita onde explicitado; -=público técnico. Todo comando cookie exige origem/CSRF conforme SECURITY. Não existe Authorization:Bearer de sessão privada. Rotas não listadas são negadas por padrão.

DTO Admin usa campos comerciais da entidade em DOMAIN mais id, number quando houver, created_at/updated_at/version/status. Nunca retorna password_hash, bearer_hash, storage_key, chaves HMAC, paths, credencial antiga ou snapshot bruto com referências de storage. Resposta de User contém id,name,email,role,status,must_change_password,version; Session contém user,expires_at,idle_expires_at,csrf_token,server_now. Equipment/Client seguem campos públicos administrativos definidos em DOMAIN. DTO Technician é projeção restrita de SECURITY, não subset escolhido pelo browser.

Quote detail inclui items ordenados, subtotal/total/currency, commercial_snapshot sanitizado quando enviado, is_expired, public_access {id,expires_at,revoked_at}|null; nunca raw bearer após emissão. ServiceOrder detail Admin inclui campos de domínio, checklist/evidence metadata/confirmation e report_status; Técnico exclui client email/notes, quote/charge e snapshot bruto. Snapshot exibido resolve logo em endpoint próprio. Report metadata: id,status,generated_at,content_hash,size_bytes,last_error_code,next_attempt_at; sem snapshot/keys crus. Imutabilidade de DTO de histórico vem do snapshot, não de joins a cadastros.

Listagens retornam summaries sem imagens/snapshots/items extensos. Detail é endpoint para conteúdo completo. Campos explicitamente create/update nas tabelas abaixo são allowlist total, e campos obrigatórios marcados por !. O resto é read-only. IDs com ! são obrigatórios na criação; GET não recebe body.

## Identity e BusinessProfile

| Método/path | Auth | Entrada | Saída/regra |
|---|---|---|---|
| POST /auth/login | - | email!, password!; header X-ClientOps-Request | 200 Session + Set-Cookie; inválido/disabled/temporária expirada: 401 genérico |
| GET /auth/session | S | Sem body | 200 Session/CSRF; não touch; inválida 401 |
| POST /auth/change-password | S | current_password!, new_password! | 200 nova Session + cookie; revoga anteriores |
| POST /auth/logout | S ou cookie inválido | {} | 204; regra especial CSRF SECURITY |
| GET /users | A | status, role, q; sort name/created_at | Lista paginada |
| POST /users | A | name!, email! | 201 User TECHNICIAN + temporary_password entregue uma vez |
| GET /users/{id} | A | — | 200 User/ETag |
| PATCH /users/{id} | A | name | 200; If-Match |
| POST /users/{id}/disable | A | {} | 200; If-Match; revoga; não self/último Admin |
| POST /users/{id}/enable | A | {} | 200; If-Match; não revive sessões |
| POST /users/{id}/reset-password | A | {} | 200 User + temporary_password; If-Match; não self |
| GET /business-profile | A | — | Profile/ETag, cinco campos nullable, is_complete e missing_fields derivados |
| PATCH /business-profile | A | trade_name, phone, email, address, timezone, acknowledge_timezone_change | Profile; If-Match; onboarding parcial e timezone IANA explícita |

As rotas de logo do contrato do produto continuam adiadas para CL-05 e não existem na OpenAPI CL-02. A OpenAPI gerada documenta cookie privado, headers CSRF e If-Match, ETag e Retry-After; `frontend/src/contracts/api.d.ts` é gerado diretamente desse artefato.

Admin pode filtrar technicians ACTIVE via GET users, sem endpoint de lookup desprotegido. BusinessProfile initial GET retorna trade_name:null,phone:null,email:null,address:null,timezone:null,is_complete:false e missing_fields com os cinco nomes. PATCH parcial preserva campos omitidos e permite NULL nos ainda não configurados; empty/whitespace normaliza para NULL, nunca é persistido. Valor não nulo inválido, timezone não IANA, is_complete ou missing_fields enviados pelo cliente retornam 422. is_complete só é true quando trade_name, phone, email, address e timezone são todos válidos/não nulos; logo não participa.

A primeira escolha de timezone é explícita no PATCH e não exige confirmação de troca de um valor anterior. Alterar timezone já configurada exige acknowledge_timezone_change=true; omissão →422 com explicação do impacto em datas civis. Não se pode limpar timezone já escolhida; se profile já completo, limpar qualquer campo essencial também é 422. Demais edições válidas são permitidas. Send/start com profile incompleto retornam409 BUSINESS_PROFILE_INCOMPLETE com missing_fields, sem efeito comercial. Login e troca obrigatória de senha continuam seguindo seus contratos, sem dependência de completude.

## Clientes e equipamentos

| Método/path | Auth | Entrada | Resposta |
|---|---|---|---|
| GET /clients | A | status default ACTIVE, q; sort name/created_at | Página |
| POST /clients | A | name!, phone?, email?, address?, notes? | 201 Client |
| GET /clients/{id} | A | — | Client/ETag; links de contexto |
| PATCH /clients/{id} | A | name,phone,email,address,notes | Client; If-Match |
| POST /clients/{id}/archive ou /restore | A | {} | 200; If-Match |
| GET /clients/{id}/equipment | A | status,q; sort name/created_at | Página |
| POST /clients/{id}/equipment | A | name!,brand?,model?,serial_number?,location_description?,notes? | 201 Equipment; Client ACTIVE |
| GET /clients/{id}/equipment/{equipment_id} | A | — | Equipment/ETag; ownership obrigatório |
| PATCH /clients/{id}/equipment/{equipment_id} | A | name,brand,model,serial_number,location_description,notes | Equipment; If-Match do Equipment |
| POST .../{equipment_id}/archive ou /restore | A | {} | 200; If-Match do Equipment |

Não há DELETE de Client/Equipment. Alterar cadastro não atualiza OS nem snapshots. Clientes archived continuam consultáveis por ID; seleção default mostra ativos.

## Orçamentos e link público

| Método/path | Auth | Entrada | Resposta/regra |
|---|---|---|---|
| GET /quotes | A | status,client_id,is_expired,q; sort number/created_at/valid_until | Página de summaries |
| POST /quotes | A | client_id!,valid_until!,notes?,items[] opcional | 201 DRAFT |
| GET /quotes/{id} | A | — | Detail/ETag |
| PATCH /quotes/{id} | A | client_id,valid_until,notes,items | DRAFT apenas; If-Match |
| POST /quotes/{id}/send | A | {} | 200 Quote + public_access entrega única; If-Match |
| POST /quotes/{id}/cancel | A | reason! | 200; If-Match; revoga links |
| POST /quotes/{id}/duplicate | A | {} | 201 novo DRAFT; não altera origem; sem If-Match |
| POST /quotes/{id}/public-access | A | expected_access_id: UUID ou null obrigatório | 201 metadata + share_url; lock Quote, SENT válido; 409 se access mudou |
| POST /quotes/{id}/public-access/{access_id}/revoke | A | {} | 200 metadata, já revogado no-op; ID deve pertencer ao quote |
| GET /quotes/{id}/logo | A | — | Logo congelada do snapshot, privada, ou 404 |
| GET /public/quote | P | Authorization: Bearer secret | 200 projeção pública por allowlist, client {name}, status/is_expired/can_approve |
| GET /public/quote/logo | P | Authorization: Bearer secret | PNG do snapshot ou 404 |
| POST /public/quote/approve | P | {"accept":true} | 200 status APPROVED/approved_at; repeat estável |

items é substituição atômica completa em DRAFT; cada item recebe description!,quantity!,unit_price!,position!,id? de item já do quote. Omitir id cria; omitir item existente remove. ID de outro quote é 422/404 sem dados alheios. Limite 100 e posições contíguas 1..N; servidor calcula totais. Sem endpoints de totals/EXPIRED/REJECTED. access expected id é do acesso mais recente, inclusive revogado; null somente se nenhum. Revoke usa o ID específico para não revogar acidentalmente um acesso novo.

### Exemplo comercial

POST /quotes, cookie e CSRF:

~~~json
{"client_id":"92eccf62-cf9b-4aec-b82a-adcf2c4dbf57","valid_until":"2026-10-09","notes":"Atendimento em horário comercial.","items":[{"position":1,"description":"Inspeção e manutenção preventiva","quantity":"2.000","unit_price":"180.00"}]}
~~~

201 (summary ilustrativo, detail acrescenta timestamps e itens):

~~~json
{"data":{"id":"f91b2271-d31a-4307-a9de-1f4dd02285e5","number":"ORC-000123","status":"DRAFT","version":1,"currency":"BRL","subtotal":"360.00","total":"360.00"}}
~~~

Send com If-Match: "v1" congela snapshot e retorna ETag "v2". Resposta inclui public_access {id,expires_at,share_url:"https://host/q#token=<segredo-entregue-uma-vez>"} fora do snapshot. Placeholder não é token válido. Se timeout após commit, GET detail mostra SENT e access metadata; Admin usa public-access/rotate, não repete envio comercial.

Public GET tem business {trade_name,phone,email,address,has_logo}, client {name}, number, notes, valid_until, items {description,position,quantity,unit_price,line_total}, subtotal,total,currency,status,sent_at,approved_at,is_expired,can_approve e server_now/business_today. O objeto client contém exatamente name; client.phone, client.email, client.address, client.id e client.notes são ausentes, não chaves com null. Contatos da empresa permanecem públicos. Projeção é feita por allowlist no servidor, preservando o snapshot interno para Admin; nenhum snapshot bruto/dado extra é enviado para depois ocultar na UI, no HTML ou em estado serializado. Não entrega nome de técnico ou qualquer outra proposta. Approve: accept deve ser true; false não significa rejeição e retorna 422.

Público válido e aprovado:

~~~json
{"data":{"status":"APPROVED","approved_at":"2026-09-25T14:20:00Z","can_approve":false}}
~~~

Mesmos campos/valor na segunda chamada. Não há nome/CPF/assinatura/IP obrigatório. Consentimento é posse do link e ação explícita, sem certificação jurídica.

## OS, agenda e execução

| Método/path | Auth | Entrada | Resposta/regra |
|---|---|---|---|
| GET /service-orders | A/T | status,technician_id,client_id (A),from,to,q; sort number/created_at/scheduled_start | Página; T imposto own e q limitado a número/problema |
| POST /service-orders | A | client_id!,service_address!,reported_problem!,equipment_id?,quote_id?,technician_id?,scheduled_start?,scheduled_end?,service_description?,checklist[]? | 201 DRAFT |
| GET /service-orders/{id} | A/T | — | Detail por papel/ETag |
| PATCH /service-orders/{id} | A | Campos de preparação permitidos por estado DOMAIN | 200; If-Match; não aceita status/started/completed/quote_id |
| POST /service-orders/{id}/schedule | A | technician_id!,scheduled_start!,scheduled_end! | 200 SCHEDULED; If-Match; para DRAFT |
| POST /service-orders/{id}/reschedule | A | technician_id!,scheduled_start!,scheduled_end! | 200; If-Match; para SCHEDULED |
| POST /service-orders/{id}/start | A/T | {} | 200 IN_PROGRESS; If-Match |
| PATCH /service-orders/{id}/notes | A/T | technician_notes! (string ou null) | 200 OS; If-Match; IN_PROGRESS |
| POST /service-orders/{id}/complete | A/T | {} | 200 COMPLETED, report_status=PENDING; If-Match |
| POST /service-orders/{id}/cancel | A | reason! | 200 CANCELLED; If-Match |
| GET /agenda | A/T | from!,to!,technician_id,status; page/page_size | Página summaries; own enforced para T |
| GET /agenda/overlaps | A | technician_id!,start!,end!,exclude_service_order_id? | {data:{overlaps:[]}}; read-only |

PATCH preparação: DRAFT aceita client_id (sem quote),equipment_id,service_address,reported_problem,service_description,technician_id,scheduled_start/end; SCHEDULED aceita equipment_id,service_address,reported_problem,service_description, e agenda/assignment exclusivamente via reschedule. quote_id fica fixo desde criação (inclusive null); vincular depois é POST-V1. Nenhum campo de execução nesse PATCH. T não passa client_id/technician_id de outro para ampliar escopo; filtro outro técnico é 403.

checklist em create é lista {label!,required!,position!}, default vazia; respostas default false. Agenda returns number,status,scheduled_start/end,technician {id,name},client {name},service_address e href relativo; não expõe informações financeiras a T. from/to listas de OS filtram scheduled_start no intervalo; /agenda seleciona interseção [start,end), documentadamente distinta para eventos atravessando meia-noite.

### Contrato de warning de agenda

Agendamento que conflita é salvo com 200, nunca 409 por overlap. UI usa preview para apresentar escolha; corrida após preview ainda é informada:

~~~json
{
  "data":{"id":"536620c3-b0a8-46bb-a2e6-c28f3034545d","status":"SCHEDULED","version":3},
  "meta":{"warnings":[{
    "code":"SCHEDULE_OVERLAP",
    "message":"Há outro serviço nesse horário.",
    "conflicts":[{"id":"48fb0a2d-ab1e-47f4-bb98-cd9df542d830","number":"OS-000041","scheduled_start":"2026-09-25T13:00:00Z","scheduled_end":"2026-09-25T14:00:00Z"}]
  }]}
}
~~~

Não existe parâmetro secreto que contorne bloqueio; warning acompanha resposta mesmo após confirmação UX. Zero overlap → warnings:[].

### Checklist, evidências, confirmação

| Método/path (prefixo /service-orders/{id}) | Auth | Entrada | Resposta |
|---|---|---|---|
| POST /checklist | A | label!,required!,position! | 201 item + ETag OS; DRAFT/SCHEDULED |
| PATCH /checklist/{item_id} | A | label,required,position | 200 item; reorganização contígua atômica |
| DELETE /checklist/{item_id} | A | — | 204; reordena restantes |
| PUT /checklist/{item_id}/response | A/T | completed! boolean | 200 item + ETag OS; IN_PROGRESS |
| GET /evidence | A/T | paginação | Metadata sem keys |
| POST /evidence | A/T | multipart file!,category!,caption? | 201 metadata; IN_PROGRESS |
| PATCH /evidence/{evidence_id} | A/T | category,caption | 200 metadata; IN_PROGRESS |
| DELETE /evidence/{evidence_id} | A/T | — | 204; IN_PROGRESS |
| GET /evidence/{evidence_id}/file | A/T | — | image/jpeg; lookup/authorization/stream |
| PUT /completion-confirmation | A/T | resolution! e campos abaixo | 200 resolução + ETag OS; IN_PROGRESS |

Todos os comandos de filho exigem If-Match da OS e retornam ETag OS atual. IDs filhos sempre scoped ao parent. Metadata evidence: id,category,caption,width,height,size_bytes,content_hash,created_at,uploaded_by {id,name}, download_path relativo protegido. Sem raw image em JSON.

CONFIRMED: {resolution:"CONFIRMED",customer_name:"Pessoa Exemplo",explicit_confirmation:true}. NOT_AVAILABLE: {resolution:"NOT_AVAILABLE",reason:"Cliente ausente ao término."}. Campos da outra variante são 422; recorded/confirmed timestamps e by vêm do servidor. Complete com checklist pendente → 409 CHECKLIST_INCOMPLETE, details.pending_item_ids; sem resolução →409 COMPLETION_REQUIRED. Serviço permanece IN_PROGRESS e nada é parcialmente concluído.

## Relatório, financeiro, alertas e timeline

| Método/path | Auth | Entrada | Resposta |
|---|---|---|---|
| GET /service-orders/{id}/report | A | — | Metadata 200 PENDING/FAILED/READY; 404 antes de concluir |
| GET /service-orders/{id}/report/file | A | — | 200 application/pdf attachment se READY; 409 REPORT_NOT_READY caso pendente |
| POST /service-orders/{id}/report/retry | A | {} | 202 PENDING/agendado; 200 se READY sem regenerar |
| GET /charges | A | status,is_overdue,service_order_id,q por número OS; sort due_date/created_at/amount | Página |
| POST /charges | A | service_order_id!,amount!,due_date!,notes? | 201 PENDING; só OS COMPLETED |
| GET /charges/{id} | A | — | Charge/ETag, is_overdue |
| PATCH /charges/{id} | A | amount,due_date,notes | 200; PENDING/If-Match |
| POST /charges/{id}/mark-paid | A | {} | 200 PAID/If-Match |
| POST /charges/{id}/cancel | A | reason! | 200 CANCELLED/If-Match |
| GET /alerts | A | status default ACTIVE,type; sort activated_at | Página; contexto, texto derivado e next_action.href |
| GET /dashboard | A | — | Contrato abaixo |
| GET /clients/{id}/timeline | A | page,page_size | Eventos do cliente |
| GET /quotes/{id}/timeline | A | page,page_size | Eventos do orçamento |
| GET /service-orders/{id}/timeline | A/T | page,page_size | Eventos filtrados por papel |
| GET /health/live | - | — | 200 {"status":"ok"}, sem configs; independente de DB/storage |
| GET /health/ready | - interno | — | 200/503 DB+migration exata+probe storage acessíveis, envelope sanitizado; proxy externo retorna 404 |

PDF download inclui Content-Disposition: attachment; filename="OS-000123.pdf", Content-Length, no-store,nosniff. Antes de enviar headers de sucesso, verificar existência, tamanho e SHA-256 dos bytes contra metadata (máximo30MiB); ausência/corrupção retorna503 STORAGE_UNAVAILABLE e log de incidente, sem re-render. Report falhou: metadata tem código sanitizado e retry habilitado; sem stack/path. Não há link público, arquivo base64 nem regenerate READY. Retry não duplica fila: representa eligibility na própria linha report.

Dashboard retorna {server_now,business_today,business_timezone,attention:[{kind,resource_id,number,status,title,next_action:{label,href}}],today_schedule:[],alerts:[],summary:{scheduled_today,in_progress,completed_today,pending_charges,overdue_charges}}. Até 10 itens por seção e total_count para Ver todos. Prioridade attention: OS atrasada SCHEDULED, report FAILED, quotes APPROVED sem OS; empates oldest first. Ausência de Charge em OS COMPLETED não gera attention nem alerta. Registrar cobrança continua ação contextual da OS COMPLETED, e cobranças existentes continuam na própria lista; pending_charges/overdue_charges contam exclusivamente linhas Charge existentes. completed_today continua contando atendimentos, independentemente de cobrança. Não adicionar billing_required, dismissed ou novo estado. Alertas são as três regras exatas; summary é contagem, sem gráficos financeiros.

Timeline entry: id,event_type,occurred_at,actor {type,display_name},payload allowlist; não expõe public access id/hash a técnico/cliente. Paginação default -occurred_at,id. Head em arquivos aplica mesma autorização de GET; Range não é suportado na v1 (servidor entrega 200 completo), evitando bypass por implementação alternativa.

## Fluxos HTTP verificáveis

1. Login → cookie+csrf → criar Client → criar Quote → GET ETag → send.
2. Browser público /q lê/limpa fragment → GET /public/quote com bearer/credentials omit → render snapshot → POST approve {accept:true} → 200; repetir não muda timestamp.
3. Admin GET quote APPROVED → POST OS → schedule com ETag e warning → técnico login (troca obrigatória se aplicável) → own OS.
4. Técnico start → respostas/upload/observações/resolução com nova ETag a cada passo → complete → COMPLETED/PENDING. Erro 412 preserva formulário e exige reler, sem overwrite forçado.
5. Job gera PDF → Admin metadata READY → download privado. Falha permite retry sem nova conclusão. Admin cria charge e mark-paid; alert reconcilia.

Bearer/temporária só nos corpos de emissão, que são no-store e excluídos de logs/traces. Exemplos usam apenas IDs e dados fictícios. Nenhum endpoint envia mensagens externas.
