# ClientOps — produto v1.0

Baseline CL-00, 25/09/2026. Documento normativo de produto; regras detalhadas em [DOMAIN](DOMAIN.md), contratos em [API](API.md), execução em [PHASES](PHASES.md). A restrição original de não iniciar CL-01 é registro histórico; o estado atual da Foundation e sua evidência ficam em PHASES.

Correção documental CL-00-FIX incorpora as instruções da auditoria fornecida pelo usuário. Root oficial: /home/breno/Projects/clientops; /home/breno/Projects é somente o diretório pai. O gate anterior foi rejeitado; o resultado desta correção habilita apenas nova auditoria, conforme PHASES.

## Problema e proposta

Pequenas empresas de serviços técnicos usam papel, planilhas e mensagens para controlar propostas, agenda, execução e cobrança. ClientOps conecta esse atendimento, tornando visíveis o estado atual, a próxima ação e o histórico. O resultado comercial esperado é organização → controle → agilidade → rastreabilidade → profissionalismo.

A demonstração usa **Climatech Serviços**, pequena empresa de climatização/manutenção com técnicos externos. Equipamento, checklist e descrição são genéricos: elétrica, informática, segurança eletrônica, assistência técnica, manutenção predial, energia solar e instalações não exigem outro modelo de domínio. Não há campos nem regras exclusivos de climatização.

É uma peça principal de portfólio freelancer: deve mostrar um processo operacional completo, usável e seguro. Não pretende reproduzir ERP, Jobber, Housecall Pro, ServiceM8, Auvo, FieldPulse ou ServiceTitan.

## Personas e implantação

| Experiência | Responsabilidade | Prioridade |
|---|---|---|
| ADMIN | Clientes/equipamentos, orçamentos, agenda, OS, cobranças, usuários e acompanhamento | Desktop |
| TECHNICIAN | Própria agenda/OS, execução, checklist, observações, evidências, conclusão | Smartphone |
| CUSTOMER | Ler e aprovar orçamento específico; solicitar alteração por contato externo | Página pública, sem conta |

Uma instalação corresponde a uma empresa: **single-tenant**. Não há organization_id, seletor de empresa, planos ou assinatura SaaS. Papéis fixos; usuário desabilitado perde acesso e sessões. Primeiro Admin é criado por comando seguro; Admin cria técnicos.

### Baseline de custo e entrega da v1

A arquitetura permanece correta e implantável em produção, enquanto execução, testes e demonstração oficiais da v1 devem ser possíveis localmente sem custo recorrente obrigatório de infraestrutura. A baseline oficial usa Docker Compose, FastAPI e PostgreSQL locais ou em containers, volumes locais persistentes `pg_data` e `private_files`, Nginx/proxy local, jobs e scheduler locais quando entrarem nas fases previstas, e PDFs/processamento locais. O repositório e a CI no GitHub integram o workflow de desenvolvimento; a demonstração oficial pode usar execução local, screenshots, vídeo e documentação.

Deployment público é **OPTIONAL/NON-BLOCKING**. Gate e release v1 não exigem VPS, banco gerenciado, S3/object storage, CDN, domínio, SaaS de observabilidade, scheduler cloud ou serviço de e-mail pagos, nem produção pública 24/7. Essa restrição não autoriza SQLite em produção, retirada de persistência, substituição de PostgreSQL, remoção de segurança, adaptação artificial a free tiers ou impedimento de deploy real futuro. Serviço cloud futuro deve ser opção de deployment/adaptação, não dependência obrigatória do core da v1, salvo Change Request explicitamente aprovado.

## Hero Flow bloqueador

~~~mermaid
flowchart TD
 A[Admin autentica] --> B[Cadastra cliente]
 B --> C[Cria orçamento DRAFT]
 C --> D[Envia: SENT e snapshot imutável]
 D --> E[Compartilha link seguro manualmente]
 E --> F[Cliente visualiza e aprova]
 F --> G[Orçamento APPROVED]
 G --> H[Admin cria e agenda OS: SCHEDULED]
 H --> I[Técnico abre no celular e inicia: IN_PROGRESS]
 I --> J[Checklist, evidências e observações]
 J --> K[Confirmação: CONFIRMED ou NOT_AVAILABLE]
 K --> L[Conclui: COMPLETED]
 L --> M[Relatório histórico PDF privado]
 M --> N[Admin acompanha e baixa]
 N --> O[Cobrança simples opcional por OS]
 O --> P[Dashboard e alertas refletem operação]
~~~

Enviar significa congelar a proposta e disponibilizar link, sem presumir entrega por e-mail/WhatsApp. Compartilhar é uma ação humana. Aprovação pública não cria OS automaticamente. Falha de PDF preserva a conclusão e permite retry. Cobrança é opcional no atendimento, mas sua funcionalidade é obrigatória na v1.

OS COMPLETED sem Charge não é pendência do Dashboard nem alerta. Registrar cobrança permanece ação contextual da OS e a lista/indicadores financeiros consideram somente registros existentes; nenhuma flag billing_required, dismissed ou novo estado será criado. Onboarding mantém dados ainda não configurados em NULL; Admin escolhe timezone IANA explicitamente e completa os cinco campos definidos em DOMAIN antes de enviar orçamento/iniciar OS. O cliente público vê somente seu nome, os dados comerciais necessários da proposta e os contatos da empresa.

## Escopo fechado

| Classificação | Conteúdo |
|---|---|
| REQUIRED V1 — identidade | BusinessProfile; User ADMIN/TECHNICIAN; Session; login/logout; senha temporária/troca obrigatória; revogação; autorização |
| REQUIRED V1 — comercial | Client; Equipment opcional; Quote/QuoteItem; dinheiro BRL; snapshot SENT; QuotePublicAccess; copiar link/abrir WhatsApp; aprovação pública |
| REQUIRED V1 — execução | ServiceOrder; agenda hoje/semana/filtros; um técnico; checklist local; observações; evidências privadas; confirmação de conclusão; ServiceReport PDF histórico |
| REQUIRED V1 — acompanhamento | Charge única opcional por OS; OperationalAlert; exatamente três automações principais; TimelineEvent; dashboard orientado a ações |
| REQUIRED V1 — entrega | REST, PostgreSQL, stack congelada, Docker/CI em fases futuras, testes por risco, demo fictícia, documentação, acessibilidade e responsividade |
| OPTIONAL/NON-BLOCKING | Drag-and-drop da agenda; acabamento de identidade de marketing além dos tokens definidos; Web Share API como progressive enhancement para compartilhar link pelo share sheet nativo quando suportado, com fallback Copiar link |
| POST-V1 | Toda ampliação abaixo; não é dependência de entrega |

Ficam POST-V1: multi-tenancy, IA, app nativo, offline, GPS/mapas/roteirização; WhatsApp API, SMS e envio automático de e-mail; portal de cliente, relatório público e PDF de orçamento; NF-e/NFS-e, PIX/cartão/gateway/bancos; estoque/compras/fornecedores/contabilidade/folha; CRM, leads/funil, filiais/marketplace; custom fields, workflow builder, RBAC configurável; múltiplos técnicos, templates globais de checklist; parcelas, pagamentos parciais e múltiplas cobranças; recuperação de senha por e-mail. Event sourcing, CQRS, brokers e microservices são excluídos da arquitetura v1, sem compromisso de adoção posterior.

Decisões auxiliares de segurança, validação, backup, retry e concorrência são REQUIRED V1 porque preservam correção/operação básica. Não acrescentam módulos comerciais. Qualquer ideia nova deve receber uma dessas três classificações antes de entrar no plano.

CL-00-FIX não acrescenta funcionalidade REQUIRED V1. Web Share continua opcional; HEIC continua fora do escopo atual. O gate de foto real em iPhone/Safari CL-05/CL-06 verifica a promessa mobile já existente: câmera e biblioteca devem atravessar input web/upload/ServiceEvidence e conclusão. MIME/formato efetivo será registrado; se HEIC em ambiente suportado inviabilizar o fluxo, bloquear release até suporte seguro autorizado ou revisão explícita da support matrix.

## Critérios comerciais verificáveis

1. Demonstrar o Hero Flow completo com dados fictícios e sem manipulação manual do banco.
2. Cada contexto mostra estado textual e uma ação principal coerente; dashboard destaca pendências e agenda do dia, sem virar BI.
3. Técnico executa em 390 px sem sidebar Admin, rolagem horizontal ou ações dependentes de hover.
4. Cliente aprova sem cadastro; valores e identificação vistos permanecem iguais após mudanças cadastrais.
5. Admin consegue explicar quem mudou o quê e quando pela timeline; PDF conserva resultado concluído.
6. Falhas de conexão/upload/PDF têm tratamento útil e não simulam sucesso. Não há promessa de operação offline.
7. Não há dados reais, credenciais fixas de produção, links públicos de evidência ou cobrança automática.

## Seed oficial

Empresa Climatech Serviços; Ana Costa (ADMIN), Marcos Silva e Lucas Rocha (TECHNICIAN). Clientes inteiramente fictícios: Loja Aurora, Escritório Horizonte, Residencial Ipê. Contatos usam domínio .example e telefones fictícios não discáveis; não abrir WhatsApp automaticamente no seed.

Comando futuro exclusivo de ambiente development/test/demo, com proteção contra produção. Senhas vêm de entrada segura do operador; nunca do repositório. Identificadores determinísticos de fixtures evitam duplicação; reexecução comum é no-op sobre base já semeada. Rebase/reset somente em banco demo dedicado, mediante comando explícito futuro. Não atualizar silenciosamente registros já concluídos.

O seed Climatech configura explicitamente os cinco campos completos do BusinessProfile, incluindo timezone America/Bahia; esse fuso vale apenas para a demonstração e fixtures específicas, sem default de produção. Captura um único instant T e business_today D nesse timezone. Gera cronologia, snapshots, totais e eventos por serviços de domínio; clocks controlados fazem as transições históricas. Não grava estados impossíveis diretamente.

| Cenário | Datas relativas e consistência |
|---|---|
| Quote DRAFT | Criado D, válido até D+14 |
| Quote SENT aguardando | Enviado T−4 dias, validade D+10; follow-up ACTIVE |
| Quote SENT expirado | Enviado T−10 dias, validade D−1; EXPIRED apenas derivado |
| Quote APPROVED | Enviado T−3 dias, aprovado T−2 dias |
| OS SCHEDULED | Mesmo orçamento aprovado; início T+60 min, fim T+120 min; upcoming ACTIVE |
| OS IN_PROGRESS | Outra OS, outro técnico; início agendado T−60 min e started_at T−45 min |
| OS COMPLETED | OS de D−2, checklist respondido, imagem sintética e confirmação; PDF gerado pelo pipeline |
| Cobranças | Duas OS concluídas distintas: PENDING vencimento D+5 e PENDING vencimento D−1; esta última overdue |
| Resolução histórica | Quote antes SENT/follow-up, depois APPROVED; alerta RESOLVED |

Imagens serão fixtures sintéticas locais em CL-05/06, sem metadados pessoais. Bearers públicos são gerados pelo fluxo normal e entregues uma vez ao operador, nunca gravados em seed/fixtures de produção. Demo implantada deve ser recriada antes de apresentação usando banco demo isolado; datas de snapshots existentes não são reescritas.

## Governança

O anexo CL-00 consolida, nesta ordem, Final Pre-CL-00 Adversarial Audit + Amendment A1, Pre-CL-00 Product & Engineering Baseline e UI/UX Baseline Oficial. Os originais separados não estavam no workspace; esta especificação utiliza a consolidação fornecida, sem alegar inspeção desses originais. Conflito material exige registro, nunca adaptação silenciosa a código antigo.

Change Request obrigatório para mudar baseline: regra afetada, problema, evidência, impacto, alternativas A/B, recomendação e impactos em escopo, segurança, testes e fases. Se necessário para consistência, CL-00 fica BLOCKED até revisão humana. B01/B02/B03/H01/H02/M01/M02 são correções explicitamente determinadas pelo usuário e registradas em DECISIONS/PHASES; não dependem de novo pedido de aprovação. Eventual inclusão de HEIC ou alteração da support matrix por falha futura continua exigindo decisão explícita, sem mudança silenciosa.
