# ClientOps — domínio e modelo lógico

Fonte principal de verdade de regras v1.0. [API](API.md) define transporte; [SECURITY](SECURITY.md) define identidade/permissões. A seção final identifica o subconjunto materializado pela migration CL-02; os demais tipos e exemplos continuam especificação de fases futuras.

## Convenções globais

Todos os IDs de entidades são UUID v4 gerados no servidor, exceto BusinessProfile singleton id=1. FKs têm ON DELETE RESTRICT, salvo limpeza técnica explicitamente descrita. Sem delete físico pela operação comum, com exceção de filhos editáveis e sessões técnicas. Texto simples UTF-8, sem HTML; strip em bordas de campos textuais, mas nunca em senha. Empty string opcional normaliza para NULL. Campos obrigatórios não aceitam string vazia. JSONB de snapshot é validado com schema versionado estrito; extra fields rejeitados na entrada.

Padrão M: created_at/updated_at TIMESTAMPTZ NOT NULL; version INTEGER NOT NULL DEFAULT 1 CHECK >0. Padrão C: created_at TIMESTAMPTZ NOT NULL. Todas as colunas listadas são NOT NULL salvo sufixo ?. FK indexada em B-tree salvo PK/unique que já a cobre. Status é VARCHAR com CHECK de valores, sem PostgreSQL ENUM. Índices adicionais estão abaixo. Domínio fixa updated_at pelo Clock; não há update automático de histórico terminal.

Texto: name 160, label 300, item description 500, phone 32, email 254, address 500, notes 5000, reason 1000, serial 100, brand/model/location 120/120/300. Rejeitar NUL e controles C0, exceto tab/newline em campos multilinha; preservar Unicode válido. Máximo 100 itens por quote, 100 itens checklist e 20 evidências por OS. Validação de contagem é sob lock da raiz; tamanhos e CHECKs escalares também no banco. UUIDs nunca substituem autorização.

## Relações

~~~mermaid
erDiagram
 User ||--o{ Session : possui
 Client ||--o{ Equipment : possui
 Client ||--o{ Quote : recebe
 Quote ||--o{ QuoteItem : contem
 Quote ||--o{ QuotePublicAccess : acessos
 Quote o|--o| ServiceOrder : origina
 Client ||--o{ ServiceOrder : solicita
 Equipment o|--o{ ServiceOrder : opcional
 User o|--o{ ServiceOrder : tecnico
 ServiceOrder ||--o{ ServiceChecklistItem : contem
 ServiceOrder ||--o{ ServiceEvidence : contem
 ServiceOrder ||--o| CustomerCompletionConfirmation : resolve
 ServiceOrder ||--o| ServiceReport : gera
 ServiceOrder ||--o| Charge : cobra
 Quote o|--o{ OperationalAlert : followup
 ServiceOrder o|--o{ OperationalAlert : upcoming
 Charge o|--o{ OperationalAlert : overdue
~~~

Quote pode originar no máximo uma OS, inclusive se esta for CANCELLED. Nova execução usa nova OS sem reaproveitar quote_id, ou novo orçamento, com explicação na descrição; não há reabertura implícita. Isso evita cobrança/execução duplicadas da mesma aceitação. Cliente possui muitos equipamentos/orçamentos/OS. Um técnico por OS; assignment não é entidade. Report/confirmation/charge são no máximo um por OS. Timeline tem FKs contextuais; BusinessProfile não se espalha como tenant FK.

## Catálogo lógico de tabelas

### BusinessProfile → business_profiles

PK id SMALLINT CHECK id=1. trade_name? VARCHAR(160), phone? VARCHAR(32), email? VARCHAR(254), address? VARCHAR(500), timezone? VARCHAR(64), logo_storage_key? VARCHAR(160), logo_content_hash? CHAR(64), logo_content_type? VARCHAR(30), logo_size_bytes? INTEGER; M. Os cinco campos de configuração são nullable para onboarding; o singleton inicial os contém em NULL, sem default de timezone nem sentinel empty string. Valor fornecido deve ser válido; vazio/whitespace normaliza para NULL conforme convenção de campo nullable. Banco CHECK id e, para texto não nulo, tamanho e conteúdo não vazio após trim; timezone não nulo é validado pelo domínio contra o catálogo IANA. Os quatro campos logo são todos NULL ou todos preenchidos; mime image/png; size positivo. Sem archive/delete. Logo privada, imutável por key; substituir não remove referências históricas.

**is_complete é derivado pelo domínio, não coluna persistida nem campo gravável da API.** É true exatamente quando trade_name, phone, email, address e timezone estão todos não nulos e válidos nas regras de tamanho/formato acima; email usa validação sintática e timezone deve ser IANA válido escolhido explicitamente pelo Admin. Logo não participa. missing_fields lista os nomes dos cinco campos que ainda faltam, em ordem trade_name, phone, email, address, timezone. Valores inválidos são rejeitados antes de persistir, sem convertê-los em dados completos.

PATCH parcial permite salvar onboarding incompleto. Uma vez timezone escolhida, só é possível substituí-la por outra IANA válida, nunca voltar a NULL. Quando is_complete já é true, serviço sob lock impede limpar qualquer um dos cinco campos e regredir a incompleto (422); edições válidas continuam permitidas. Essas invariantes preservam regras civis e a conclusão de atendimentos já iniciados, sem criar status ou flag de onboarding persistida. Antes de send de Quote e start de ServiceOrder, domínio verifica is_complete sob lock do profile: false → 409 BUSINESS_PROFILE_INCOMPLETE, sem transição, snapshot, bearer ou evento comercial.

Não há timezone de produção inferida do host, navegador, locale, env ou seed. America/Bahia é valor explícito apenas do seed Climatech e de fixtures de demonstração/teste. Antes de configurar timezone, operações de conta/perfil/cadastros e instantes UTC continuam disponíveis; regras que precisam de business_today ou agenda local aguardam essa escolha conforme a seção temporal abaixo.

### User → users

PK id; name VARCHAR(160), email_normalized VARCHAR(254) UNIQUE, password_hash TEXT, role CHECK ADMIN/TECHNICIAN, status CHECK ACTIVE/DISABLED, must_change_password BOOLEAN, temporary_password_expires_at? TIMESTAMPTZ, password_changed_at TIMESTAMPTZ; M. CHECK temporary expiry presente quando must_change_password=true e nulo quando false. Índice (role,status,name,id). E-mail normalizado ASCII conforme SECURITY; CHECK lower/trim e tamanho no banco. Não expor hash/expiry interno em listagens.

Sem editar papel pela API. Nome é editável; email só no provisionamento nesta v1 para evitar alteração silenciosa de login. Criar Admin adicional somente CLI administrativa explícita; interface Admin cria TECHNICIAN. Proibido desabilitar/resetar a si próprio pela gestão; troca própria usa fluxo específico. Último Admin ACTIVE não pode ser desabilitado, verificado sob advisory lock de gestão de Admin. Desabilitar técnico atribuído a OS aberta não altera assignment: Admin recebe pendência e pode reatribuir antes de início ou executar/concluir como Admin após início. Histórico conserva técnico original.

### Session → sessions

PK id; user_id FK User, bearer_hash BYTEA UNIQUE CHECK length=32, created_at, last_seen_at, absolute_expires_at TIMESTAMPTZ; revoked_at? TIMESTAMPTZ, revocation_reason? VARCHAR(40). CHECK created_at<=last_seen_at<=absolute_expires_at; revocation fields ambos nulos ou preenchidos. Índices user_id e absolute_expires_at. Idle deriva de last_seen_at. Sem bearer raw ou IP/UA obrigatório; lifecycle em SECURITY. Limpeza técnica permite delete 30 dias após expiração/revogação; eventos de segurança permanecem pelo período de log.

### Client → clients

PK id; name VARCHAR(160), phone? VARCHAR(32), email? VARCHAR(254), address? VARCHAR(500), notes? VARCHAR(5000), status CHECK ACTIVE/ARCHIVED, archived_at? TIMESTAMPTZ; M. CHECK status/archived_at coerentes. Índices (status,name,id), created_at. Contatos não únicos. Sem CPF/RG/nascimento. Listagens de técnico inexistem; projeção operacional definida em SECURITY.

### Equipment → equipment

PK id; client_id FK Client, name VARCHAR(160), brand? VARCHAR(120), model? VARCHAR(120), serial_number? VARCHAR(100), location_description? VARCHAR(300), notes? VARCHAR(5000), status ACTIVE/ARCHIVED, archived_at? TIMESTAMPTZ; M. UNIQUE(id,client_id) para ownership composta; índice (client_id,status,name,id). Serial não único. client_id imutável. Não transformar em inventário de ativos genérico.

### Quote → quotes

PK id; number BIGINT UNIQUE positivo de sequence (lacunas aceitas), client_id FK Client, source_quote_id? FK Quote, status DRAFT/SENT/APPROVED/CANCELLED, currency CHAR(3) CHECK BRL, valid_until DATE, notes? VARCHAR(5000), subtotal NUMERIC(14,2), total NUMERIC(14,2), commercial_snapshot? JSONB, sent_at?, approved_at?, cancelled_at? TIMESTAMPTZ, cancellation_reason? VARCHAR(1000), created_by FK User; M. UNIQUE(id,client_id) para vínculo composto. CHECK 0<=subtotal=total<=999999999.99. Índices (status,valid_until), (status,sent_at), (client_id,created_at,id).

CHECKs: DRAFT não tem sent/approved/cancelled/snapshot; SENT tem sent/snapshot e não approved/cancelled; APPROVED tem sent/snapshot/approved e não cancelled; CANCELLED tem cancelled/reason e não approved, podendo ter sent/snapshot se anteriormente SENT. sent e snapshot ambos presentes ou ambos ausentes; approved>=sent, cancelled>=created. source_quote_id diferente de id. Snapshot schema_version=1 quando presente. number nunca reutilizado, display ORC-000123 (mínimo seis dígitos).

### QuoteItem → quote_items

PK id; quote_id FK Quote, description VARCHAR(500), quantity NUMERIC(10,3), unit_price NUMERIC(14,2), line_total NUMERIC(14,2), position SMALLINT; M. UNIQUE(quote_id,position) DEFERRABLE INITIALLY DEFERRED, position 1..100. CHECK quantity 0.001..9999.999, unit_price 0..9999999.99, line_total 0..999999999.99. Remover/reordenar permitido só DRAFT; substituição atômica da lista pelo serviço, sem versões independentes no HTTP. Posições contíguas 1..N validadas no serviço ao terminar comando; unique diferido permite troca de posições sem violação intermediária.

### QuotePublicAccess → quote_public_access

PK id; quote_id FK Quote, bearer_hash BYTEA UNIQUE CHECK length=32, created_by FK User, created_at, expires_at TIMESTAMPTZ, revoked_at? TIMESTAMPTZ, revocation_reason? VARCHAR(40). CHECK expires_at>created_at; revocation fields pareados. UNIQUE parcial quote_id WHERE revoked_at IS NULL (um não revogado, mesmo que expirado); índice expires_at. Rotacionar revoga anterior inclusive expirado. Registros preservados, sem raw bearer; não armazenar sessão de cliente.

### ServiceOrder → service_orders

PK id; number BIGINT UNIQUE positivo, client_id FK Client, equipment_id? FK Equipment, quote_id? FK Quote UNIQUE, technician_id? FK User, status DRAFT/SCHEDULED/IN_PROGRESS/COMPLETED/CANCELLED, service_address VARCHAR(500), reported_problem VARCHAR(5000), service_description? VARCHAR(5000), technician_notes? VARCHAR(5000), scheduled_start?, scheduled_end?, started_at?, completed_at?, cancelled_at? TIMESTAMPTZ, cancellation_reason? VARCHAR(1000), execution_snapshot? JSONB, created_by FK User; M.

FK (equipment_id,client_id) → Equipment(id,client_id); FK (quote_id,client_id) → Quote(id,client_id). Índices (technician_id,status,scheduled_start,id), (status,scheduled_start), (client_id,created_at,id). CHECK schedule ambos nulos ou ambos presentes, end>start e duração<=24h. SCHEDULED exige técnico/início/fim, sem started/completed. IN_PROGRESS exige técnico/agenda/started/snapshot, sem completed. COMPLETED exige técnico/agenda/started/completed/snapshot e completed>=started. CANCELLED exige cancelled/reason e não completed. DRAFT não contém started/completed/execution snapshot. Validações de papel/técnico e estado de quote são do serviço sob locks. display OS-000123.

### ServiceChecklistItem → service_checklist_items

PK id; service_order_id FK OS, label VARCHAR(300), required BOOLEAN, position SMALLINT, completed BOOLEAN DEFAULT false, completed_at? TIMESTAMPTZ, completed_by? FK User; M. UNIQUE(service_order_id,position) DEFERRABLE INITIALLY DEFERRED, position 1..100. Serviço mantém sequência contígua ao incluir/mover/remover; unique diferido permite reordenação atômica. CHECK completed exige timestamp/autor; false exige ambos NULL. Índice service_order_id coberto pelo unique. Resposta só em IN_PROGRESS, sempre autor autenticado e Clock; desfazer resposta nesse estado zera ambos. Estrutura congelada desde start; sem ChecklistResponse nem template global.

### ServiceEvidence → service_evidence

PK id; service_order_id FK OS, category BEFORE/AFTER/GENERAL, caption? VARCHAR(1000), storage_key VARCHAR(160) UNIQUE, content_hash CHAR(64), content_type CHECK image/jpeg, size_bytes INTEGER CHECK 1..8388608, width/height INTEGER CHECK 1..2560, uploaded_by FK User; C. Índice (service_order_id,created_at,id). Máximo 20 sob lock. Input JPEG/PNG/WebP; persistido JPEG sanitizado conforme SECURITY. Conteúdo não é substituível: remover e reenviar enquanto IN_PROGRESS. Caption/categoria editáveis nesse estado. Sem original filename persistido/exposto.

### CustomerCompletionConfirmation → customer_completion_confirmations

PK id; service_order_id FK OS UNIQUE, resolution CONFIRMED/NOT_AVAILABLE, customer_name? VARCHAR(160), confirmed_at? TIMESTAMPTZ, explicit_confirmation BOOLEAN, reason? VARCHAR(1000), recorded_at TIMESTAMPTZ, recorded_by FK User; M. CONFIRMED exige nome, confirmed_at, explicit_confirmation=true, reason NULL; NOT_AVAILABLE exige reason, explicit_confirmation=false, nome/confirmed_at NULL. recorded_at e confirmed_at são do servidor. Somente IN_PROGRESS permite criar/substituir; cada substituição gera evento sanitizado. Não é assinatura eletrônica jurídica nem conta de cliente.

### ServiceReport → service_reports

PK id; service_order_id FK OS UNIQUE, status PENDING/FAILED/READY, snapshot JSONB, snapshot_hash CHAR(64), storage_key? VARCHAR(160) UNIQUE, generated_at? TIMESTAMPTZ, content_hash? CHAR(64), size_bytes? INTEGER, attempts INTEGER DEFAULT 0, total_attempts INTEGER DEFAULT 0, next_attempt_at? TIMESTAMPTZ, last_error_code? VARCHAR(80); M. CHECK counts>=0, total>=attempts. READY exige todos os campos de arquivo, size 1..31457280 e next_attempt_at NULL; demais estados não têm campos de arquivo. Snapshot schema_version=1. Índice (status,next_attempt_at,id). Gerado somente para OS COMPLETED, validado pelo serviço; first READY congela linha inteira. O snapshot existe antes do primeiro render e nunca muda, inclusive em FAILED.

### Charge → charges

PK id; service_order_id FK OS UNIQUE, status PENDING/PAID/CANCELLED, currency BRL, amount NUMERIC(14,2) CHECK 0.01..999999999.99, due_date DATE, notes? VARCHAR(1000), paid_at?, cancelled_at? TIMESTAMPTZ, cancellation_reason? VARCHAR(1000), created_by FK User; M. PAID exige paid_at e não cancelled; CANCELLED exige cancelled/reason e não paid; PENDING nenhum deles. Índice (status,due_date,id). Somente Admin, OS COMPLETED. Se há quote, default amount=quote snapshot total; Admin confirma e pode escolher outro valor positivo, explicitamente, sem mudar quote. Total zero permite OS mas requer valor positivo se houver cobrança. Nunca cria cobrança automaticamente.

### OperationalAlert → operational_alerts

PK id; type QUOTE_FOLLOW_UP/UPCOMING_SERVICE/OVERDUE_CHARGE, quote_id? FK Quote, service_order_id? FK OS, charge_id? FK Charge, status ACTIVE/RESOLVED, activated_at TIMESTAMPTZ, resolved_at? TIMESTAMPTZ, last_evaluated_at TIMESTAMPTZ; M. CHECK exatamente uma FK não nula, correspondente ao type; resolved_at só se RESOLVED. Unique por (type,quote_id), (type,service_order_id), (type,charge_id), com índices parciais FK não nula; isso garante uma linha por regra/alvo por toda a vida, mais forte que apenas ACTIVE. Índice (status,activated_at,id). Não há READ/UNREAD/SNOOZE/DISMISSED, botão de resolver ou free-form message.

### TimelineEvent → timeline_events

PK id; event_type VARCHAR(80), actor_type USER/CUSTOMER_QUOTE_LINK/SYSTEM_AUTOMATION, actor_user_id? FK User, actor_public_access_id? FK QuotePublicAccess, client_id? FK Client, quote_id? FK Quote, service_order_id? FK OS, charge_id? FK Charge, subject_user_id? FK User, business_profile_id? FK BusinessProfile, payload JSONB, occurred_at TIMESTAMPTZ. Ator USER exige actor_user_id apenas; CUSTOMER_QUOTE_LINK exige actor_public_access_id apenas; SYSTEM_AUTOMATION não tem ambas. Pelo menos um contexto obrigatório, com FKs coerentes pelo serviço; eventos da execução podem referir cliente, OS e charge simultaneamente. Índices (client_id,occurred_at,id), equivalentes para quote/OS/charge, e subject_user_id. Sem updated_at/version. Runtime DB role tem INSERT/SELECT, sem UPDATE/DELETE nesta tabela. Schema payload allowlist por tipo; limite 4 KiB.

### Infraestrutura, fora do modelo comercial

rate_limit_buckets: PK composta (rule VARCHAR(40), key_hash BYTEA CHECK octet_length=32, window_start TIMESTAMPTZ), count INTEGER CHECK >=0, expires_at TIMESTAMPTZ; índice expires_at. Upsert atômico para rate limits, commit independente de transação de negócio, sem armazenar IP/login/bearer raw. alembic_version é metadado de migration. Não acrescentar ServiceAssignment/ChecklistResponse ou entidade genérica de arquivos por conveniência.

Modelo acima descreve schema final. Timeline entra progressivamente: CL-02 cria contextos User/BusinessProfile e atores USER/SYSTEM_AUTOMATION; CL-03 acrescenta FK Client; CL-04 acrescenta Quote/QuotePublicAccess e ator CUSTOMER_QUOTE_LINK; CL-05 acrescenta ServiceOrder; CL-06 acrescenta Charge. Cada migration ajusta CHECK de contexto/ator e índices ao conjunto existente, sem FK para tabela ainda ausente. Eventos antigos continuam válidos. As demais tabelas entram na sua fase; schema inicial CL-01 contém só metadados Alembic.

## Dinheiro, datas e clock

Money é Decimal e JSON string com exatamente 2 casas; quantidade JSON string com até 3, normalizada a 3. Rejeitar floats JSON, notação exponencial, NaN, valores negativos ou escala excedente. line_total = quantize(quantity × unit_price, 0.01, ROUND_HALF_UP); subtotal = soma das linhas já arredondadas; total = subtotal. Sem desconto/taxa/imposto/frete nesta v1. Exemplo: 3 × 0.335 é inválido como unit_price; 0.005 de quantity × 1.00 resulta 0.01. Limites individuais e total acima valem antes de persistir; overflow retorna 422. DRAFT pode ter zero itens; enviar exige 1..100, inclusive serviços sem custo.

Instantes são UTC TIMESTAMPTZ, serializados RFC3339 com Z. Entrada de agenda aceita RFC3339 com offset obrigatório e normaliza UTC; frontend mostra timezone IANA da empresa. Datas civis due_date/valid_until são DATE YYYY-MM-DD, sem conversão UTC. business_today = Clock.now_utc convertido ao timezone ATUAL do BusinessProfile, depois date. Clock.now_utc é capturado uma vez por comando/job; nenhuma chamada espalhada a datetime.now/Date.now decide regra de domínio. Frontend usa server_now/business_today para orientação; servidor revalida.

Se timezone ainda for NULL, business_today é indisponível: não calcular por UTC nem por outro fallback. Comando/consulta que exige data civil calculada ou agenda local (incluindo limites de validade/vencimento e dashboard) retorna 409 BUSINESS_PROFILE_INCOMPLETE. Endpoints que não precisam desse cálculo continuam operando e, se incluírem metadados temporais, usam business_timezone:null e business_today:null; server_now permanece UTC. evaluate_automations encerra como no-op de onboarding com log sanitizado CONFIGURATION_REQUIRED, sem criar/resolver alertas por uma data inventada, e reavalia no próximo intervalo após configuração. Jobs técnicos de sessão/storage usam UTC e não dependem de timezone. Profile incompleto não torna health/readiness indisponível nem impede login/onboarding.

Mudança de timezone afeta regras civis futuras e apresentação da agenda, nunca os instantes ou snapshots. Admin recebe preview/aviso explícito desse efeito ao salvar. Snapshot guarda timezone usado para emissão/conclusão. Horários ambíguos em DST exigem offset escolhido; horários locais inexistentes são rejeitados pela UI/serviço. Programação no passado exige confirmação UX, mas não hard block; end sempre maior que start. Duração padrão sugerida 60 min; API exige end explícito, limite 24h.

## Quote: máquina, snapshot e repetição

~~~mermaid
stateDiagram-v2
 [*] --> DRAFT
 DRAFT --> SENT: Admin send
 DRAFT --> CANCELLED: Admin cancel
 SENT --> APPROVED: bearer público válido
 SENT --> CANCELLED: Admin cancel
 APPROVED --> [*]
 CANCELLED --> [*]
~~~

DRAFT edita cliente ativo, itens, notas, validade; valid_until até business_today+365 dias. Pode salvar draft vencido, mas send exige valid_until>=business_today. SENT congela campos comerciais/itens; só ações approve, cancel, revoke/rotate de acesso permitidas. APPROVED/CANCELLED são terminais e imutáveis; vincular OS não modifica quote. EXPIRED é apenas SENT AND valid_until<business_today; dia de validade é inclusivo. Não existe REJECTED.

Revisar SENT: cancelar com motivo, duplicar como novo DRAFT com source_quote_id, editar e enviar. Duplicate permitido de qualquer estado como novo recurso; copia campos/itens, sem snapshot/access/approval/número, recalcula totais e sugere validade D+14. Draft fica ligado ao cliente original; se archived, selecionar cliente ativo antes de send. Aprovação Admin direta não existe na v1.

QuoteSnapshotV1 é JSONB:

~~~text
schema_version: 1
quote: {id, number, sent_at, currency:"BRL", valid_until, business_timezone}
business: {trade_name, phone, email, address,
           logo:{storage_key,content_hash,content_type}|null}
client: {id, name, phone|null, email|null, address|null}
items: [{id, position, description, quantity:"1.000",
         unit_price:"100.00", line_total:"100.00"}]
subtotal:"100.00"; total:"100.00"; notes:null|string
~~~

Snapshot nasce com SENT na mesma transação e é a fonte histórica comercial para leitura enviada/aprovada. O snapshot interno preserva client.id/name/phone/email/address necessários ao Admin; não inclui client.notes ou credenciais. A API pública constrói DTO por allowlist e projeta o cliente exclusivamente como client {name}: não envia client.phone, client.email, client.address, client.id, client.notes, snapshot bruto ou keys de storage, nem em campos auxiliares/HTML. Os contatos comerciais da empresa permanecem públicos; logo tem endpoint protegido por bearer. raw token nunca é snapshot. Logo antiga referenciada é retida. Atualizações em Client/Business não alteram esse objeto.

Bearer vence em 30 dias de sua emissão; validade comercial e validade do acesso são controles independentes. Admin pode rotacionar apenas SENT ainda comercialmente válido; revogar SENT ou APPROVED. Cancelar revoga todos. Aprovar não revoga automaticamente: permite confirmação/repetição/leitura até expires_at. Segunda aprovação com bearer ainda válido em APPROVED devolve 200, mesmo approved_at, sem evento extra; validade comercial não é reavaliada para desfazer aprovação passada. Se token expirou/revogou depois, 401. Corrida approve/cancel sob lock: um vence e outro recebe estado/erro coerente. Rotação pode invalidar imediatamente um link aberto.

## OS: estados, mutabilidade e ownership

~~~mermaid
stateDiagram-v2
 [*] --> DRAFT
 DRAFT --> SCHEDULED: Admin schedule
 SCHEDULED --> IN_PROGRESS: Admin ou técnico atribuído
 IN_PROGRESS --> COMPLETED: checklist e resolução completos
 DRAFT --> CANCELLED: Admin
 SCHEDULED --> CANCELLED: Admin
 IN_PROGRESS --> CANCELLED: Admin com motivo
 COMPLETED --> [*]
 CANCELLED --> [*]
~~~

Criar OS sempre produz DRAFT, com service_address explícito (sugerido do cliente), reported_problem obrigatório. quote opcional deve ser APPROVED e pertencer ao mesmo cliente; se vinculado, client/quote ficam fixos desde criação. equipamento opcional deve pertencer ao cliente e estar ACTIVE na seleção. Sem quote, DRAFT permite trocar cliente, limpando equipamento e copiando endereço apenas por escolha explícita.

| Estado | Campos/operações permitidos | Restrições |
|---|---|---|
| DRAFT | Admin edita preparação, cliente sem quote, equipamento, local, descrição, técnico, agenda e checklist | Sem respostas/evidências/resolução; agendar exige técnico ACTIVE TECHNICIAN e início/fim |
| SCHEDULED | Admin reagenda, reatribui técnico, ajusta equipamento/local/descrições/checklist | Cliente e quote fixos; nenhuma resposta ainda; sem retorno a DRAFT |
| IN_PROGRESS | Admin ou técnico atribuído respondem checklist, editam technician_notes, evidências, confirmação | Cliente/equipamento/local/técnico/agenda/descrições de preparação/estrutura do checklist congelados |
| COMPLETED | Leituras e criação de charge; processamento técnico de report | Nenhuma mudança de OS ou filhos; sem reabrir |
| CANCELLED | Leitura histórica; evidências já existentes privadas | Imutável, sem conclusão/charge/report; sem reabrir |

Start não exige estar perto do horário agendado; servidor registra timestamp real e UI informa diferença. Admin pode iniciar/concluir OS atribuída a qualquer técnico, registrando seu próprio actor; nunca troca responsável ocultamente. Technician não cancela/agenda/atribui nem acessa outras OS.

ExecutionSnapshotV1 em start: schema_version, captured_at, business_timezone, client {id,name,phone,email,address}, equipment {id,name,brand,model,serial_number,location_description}|null, technician {id,name}, service_address, reported_problem, service_description, scheduled_start/end, quote {id,number,total,currency}|null. Informações são lidas sob locks; depois são imutáveis. Dados de contato anteriores a start refletem cadastro atual; depois refletem snapshot. Report copia esse snapshot e não consulta novamente cliente/equipamento/técnico.

Concluir exige IN_PROGRESS, started_at, técnico, todos os required=true concluídos, CustomerCompletionConfirmation válida. Checklist vazio é permitido; evidência e observação não são obrigatórias universalmente, mas Hero Flow demonstra ambas. Conclusão dupla sem versão atual retorna 412; UI relê e exibe concluída; nunca gera segundo report. Cancelar IN_PROGRESS preserva respostas/evidências/snapshot e registra motivo, sem PDF obrigatório.

Checks/FKs/uniques no banco são segunda defesa; validações entre tabelas/estados ficam no serviço com lock. Runtime não oferece endpoint de update status arbitrário; scripts/seed chamam serviços. Testes de integração provam que todo comando de filho bloqueia raiz. Sem triggers para máquina de estados.

## Agenda e overlaps

Intervalos semiabertos [start,end); A conflita B quando A.start<B.end AND B.start<A.end, mesmo technician_id, estados SCHEDULED ou IN_PROGRESS, excluindo própria OS. End igual ao start vizinho não conflita. IN_PROGRESS usa intervalo planejado; não inventar previsão de término nem expandir indefinidamente. Agenda inclui históricos COMPLETED/CANCELLED quando filtrados, mas estes não geram conflito.

Endpoint de preview é read-only. Schedule/reschedule revalida e **salva mesmo havendo overlap**, retorna warnings com IDs, horário e número das outras OS. UI pede escolha Agendar mesmo assim após preview e repete aviso pós-save se corrida introduzir outro overlap. Omitir preview nunca transforma conflito em hard block. Warning não é OperationalAlert nem quarta automação. API/TESTING fixam os exemplos.

## Confirmação e relatório histórico

CONFIRMED: operador registra nome de quem confirmou e checkbox explícito, servidor fixa confirmed_at/recorded_at. NOT_AVAILABLE: operador fornece reason; ninguém precisa estar presente para concluir. Alteração antes da conclusão substitui resolução e registra evento, sem apagar trilha.

ReportSnapshotV1 capturado atomicamente com COMPLETED:

~~~text
schema_version:1; report_id; service_order_id; number
completed_at; business_timezone
business:{trade_name,phone,email,address,logo:{storage_key,content_hash,content_type}|null}
execution: ExecutionSnapshotV1
started_at; technician_notes
checklist:[{id,label,required,position,completed,completed_at,completed_by_name|null}]
evidence:[{id,category,caption,storage_key,content_hash,content_type,width,height,size_bytes}]
confirmation:{resolution,customer_name,explicit_confirmation,confirmed_at,
              reason,recorded_at,recorded_by_name}
~~~

Sem valores financeiros além da referência opcional de quote na execution; cobrança não entra nem altera PDF. Usar JSON UTF-8 canônico (keys ordenadas, sem whitespace extra, ensure_ascii=false; números comerciais como strings) para snapshot_hash SHA-256. content_hash é SHA-256 dos bytes do primeiro PDF válido, não do snapshot. Não prometer PDF byte a byte igual entre versões de biblioteca: documento já gerado é preservado e baixado, nunca re-renderizado. Metadados generated_at representam render; completed_at representa atendimento.

Report status só PENDING→READY/FAILED e FAILED→PENDING por retry ou FAILED→READY por job elegível; READY terminal. Mesmo snapshot em todos os retries. Arquivo ausente/corrompido após READY é incidente de storage/restore, sem regenerar automaticamente. Somente Admin acessa snapshot/PDF; técnico vê report_status na própria OS.

## Charge, archive e delete

Charge PENDING→PAID ou PENDING→CANCELLED; terminais imutáveis. PENDING edita amount/due_date/notes. mark-paid usa Clock.now_utc, sem pagamentos parciais/backdating nesta v1. OVERDUE = PENDING AND due_date<business_today, inclusive após mudança de timezone. due_date aceita passado (gera alerta) e até D+365. Cancelar não libera UNIQUE service_order_id; cobrança errada pode ser corrigida enquanto PENDING, e substituições após cancelamento são POST-V1.

Charge é opcional por OS: ausência de Charge em COMPLETED não constitui pendência de attention, alerta ou dívida. A ação de registrar cobrança permanece no contexto da OS; lista e indicadores financeiros contam somente cobranças que existem. Não criar billing_required, dismissed ou novo estado para administrar ausência legítima de cobrança.

Client/Equipment ACTIVE↔ARCHIVED, Admin archive/restore idempotentes com versão. Sem delete comum, mesmo sem histórico. Arquivar cliente não arquiva equipamentos em cascata, não cancela quote/OS e não impede executar histórico já aberto. Novas seleções/criação/send de draft exigem Client ACTIVE e Equipment ACTIVE; iniciar/concluir vínculos existentes continua possível. Técnicos não recebem notas internas do cliente. User não é deletado; email permanece reservado. Quote/OS/charge são cancelados; nunca removidos. DRAFT QuoteItem/checklist podem ser removidos; evidência só em IN_PROGRESS. Histórico, snapshots, reports READY e timeline não são editados.

## Três automações, resolução e unicidade

| Tipo | Condição atual exata | Frequência |
|---|---|---|
| QUOTE_FOLLOW_UP | Quote.status=SENT AND now>=sent_at+72h; inclui SENT comercialmente expirado enquanto não resolvido | 5 minutos |
| UPCOMING_SERVICE | OS.status=SCHEDULED AND scheduled_start<=now+24h; inclui OS atrasada ainda não iniciada para catch-up | 5 minutos |
| OVERDUE_CHARGE | Charge.status=PENDING AND due_date<business_today | 5 minutos |

Uma regra/alvo corresponde a uma linha pela vida toda. True cria ACTIVE ou reativa RESOLVED (novo activated_at, resolved_at NULL); true já ACTIVE só atualiza last_evaluated_at, sem evento duplicado. False resolve ACTIVE com resolved_at; false já RESOLVED é no-op. Transição relevante (aprovar/cancelar, iniciar/reagendar/cancelar, pagar/alterar vencimento) reconcilia alert existente na mesma transação; job cria os alertas temporais e corrige atrasos. Antes de CL-06 esses hooks não exigem criar tabela de alert antecipada; CL-06 integra e testa a reconciliação.

Reagendar para além da janela resolve; aproximar de novo reativa mesma linha. Execução perdida não perde alvo ainda pendente: reavaliar estado atual, não emitir alerta histórico para condição já resolvida durante indisponibilidade. Atualização concorrente e job bloqueiam mesma raiz; unique + upsert impedem duplicação. Alerta é administrativo; técnico usa agenda/tarefas, sem módulo de alertas.

## Timeline: taxonomia e acesso

USER aponta usuário real; CUSTOMER_QUOTE_LINK aponta registro de acesso, sem afirmar identidade civil de quem clicou; SYSTEM_AUTOMATION inclui jobs técnicos report e automações com payload source distinguindo o comando. Não é event sourcing. Eventos abaixo são emitidos somente após validação, junto com commit da mudança, e jamais em GET público/preview:

| Eventos | Contexto e payload permitido |
|---|---|
| user.created, user.disabled, user.enabled, user.password_reset, user.password_changed | subject_user_id, role/status; sem credencial |
| business.updated, business.logo_changed | profile; nomes de campos alterados, sem contatos anteriores |
| client.created/updated/archived/restored; equipment.created/updated/archived/restored | client e equipment_id no payload; nomes dos campos, sem notes |
| quote.created/updated/sent/approved/cancelled/duplicated | quote/client, status_from/to, number; source_quote_id em duplicated; motivo cancelamento <=1000 |
| quote.access_rotated/access_revoked | quote/client, access_id; sem hash/raw/link |
| service.created/prepared/scheduled/rescheduled/assigned/started/completed/cancelled | OS/client, status e horários/técnico quando aplicável; motivo |
| checklist.structure_changed, checklist.answered | OS, item_id; contagem ou completed boolean, sem copiar observações |
| evidence.added/updated/removed | OS, evidence_id/category; sem key/path/imagem |
| service.notes_updated | OS; apenas indicação de mudança |
| completion.recorded | OS; resolution, sem nome/reason duplicados |
| report.ready/failed/retry_requested | OS, report_id e código sanitizado |
| charge.created/updated/paid/cancelled | charge/OS/client; status, amount/due_date quando alterados |
| alert.activated/resolved | alvo; type e alert_id |

Login/logout/falhas de autenticação ficam em log de segurança, sem timeline operacional. Não registrar view público: GET permanece sem mutação comercial nem falsa comprovação de leitura. Listagem técnica filtra contexto da própria OS E tipos permitidos de execução (service, checklist, evidence, completion); exclui quote/charge/usuários/profile/alert/report e payload de cliente interno. Admin vê timeline de contexto, não feed irrestrito exposto ao cliente.

## Subconjunto persistido na CL-03

O schema atual materializa BusinessProfile singleton, User, Session, RateLimitBucket, Client, Equipment e TimelineEvent nos contextos User/BusinessProfile/Client. Client e Equipment alternam entre ACTIVE e ARCHIVED por comandos idempotentes versionados; o arquivamento do cliente preserva o estado dos equipamentos e bloqueia somente a criação de novos equipamentos. Equipment sempre pertence ao Client da rota e `client_id` não pode ser alterado.

Client.email é texto genérico de contato: trim, blank para NULL, limite 254 e rejeição de controles, sem normalização de identidade, unicidade ou validação DNS. Busca de Client e Equipment consulta somente `name`, trata `%`, `_` e `\` como literais e usa `id` como desempate estável. A timeline CL-03 acrescenta os oito eventos client/equipment, nomes de campos alterados e `equipment_id`, sem valores de contato ou notas.

Quote, ServiceOrder, uploads, logo, Report, Charge, OperationalAlert e scheduler não foram antecipados.
