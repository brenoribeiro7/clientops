# ClientOps — UI/UX v1.0

Consolidação do baseline fornecido. **Action-first; state → next action; progressive disclosure; uma ação principal por contexto; status sempre visível; Admin ≠ Técnico ≠ Cliente.** A seção final registra o subconjunto de identidade/configuração implementado na CL-02.

## Arquitetura de informação

~~~text
ADMIN — sidebar desktop
Principal
  Dashboard                 /admin
  Agenda                    /admin/agenda
Operação
  Serviços                  /admin/services
  Orçamentos                /admin/quotes
  Clientes                  /admin/clients
Financeiro
  Cobranças                 /admin/charges
Configurações               /admin/settings (Empresa e Usuários)

TECHNICIAN — navegação inferior própria
Hoje                        /tech/today
Serviços                    /tech/services
Conta                       /tech/account

CUSTOMER
Orçamento público           /q#token=... → /q após leitura

IDENTIDADE
Entrar                      /login
Troca obrigatória           /change-password
~~~

Equipamentos dentro de cliente; timeline dentro de cliente/quote/OS. Sem menu de automações ou relatórios públicos. Papel determina experiência; largura determina layout. Técnico desktop mantém navegação simples; Admin mobile usa drawer com grupos Admin. Não reutilizar sidebar Admin como experiência técnica.

Deep links checam sessão antes de exibir dados. Redirect de login só aceita destino interno permitido; must_change_password tem precedência. Guards não substituem autorização da API.

## Wireframes conceituais

~~~text
ADMIN / DASHBOARD
┌ Sidebar ┬ Hoje, sexta-feira 25       [Abrir agenda] ┐
│Principal│ Precisam de atenção                       │
│Operação │ OS atrasada → Ver serviço                 │
│Financeiro│ Proposta aprovada → Agendar              │
│Config.  │ Agenda de hoje            Alertas         │
│         │ 09:00 Marcos • OS-001      cobrança vencida│
│         │ 14:00 Lucas  • OS-002      follow-up       │
│         │ Resumo: agendadas / em curso / concluídas │
└─────────┴───────────────────────────────────────────┘

ADMIN / OS
OS-000123 • Agendada                           [Iniciar]
Cliente • Local • Técnico • Horário
Resumo | Execução | Evidências | Histórico
Conteúdo da aba; ações secundárias em contexto

TÉCNICO / HOJE — 390px
Hoje, 25 set.
┌ 09:00 • Agendada                 ┐
│ OS-000123 • Loja Aurora          │
│ Endereço • contato               │
│ [Ver serviço]                    │
└──────────────────────────────────┘
Hoje                Serviços                Conta

TÉCNICO / EXECUÇÃO
OS-000123 • Em andamento
Checklist obrigatório 2 de 3
[ ] Conferir funcionamento
[✓] Inspecionar instalação
Evidências [Adicionar foto]
Observações [Salvar]
Confirmação: Confirmou / Não disponível
                       [Concluir atendimento]

CLIENTE — sem navegação de aplicativo
Logo/empresa • contato
Orçamento ORC-000123 • Enviado
Cliente • validade
Itens / quantidades / valores / total BRL
Observações
[APROVAR ORÇAMENTO]
Solicitar alteração: contatar empresa
~~~

Dashboard usa API, até10 itens/seção, Ver todos e resumo pequeno; sem gráficos decorativos/BI. Attention inclui OS atrasada SCHEDULED, report FAILED e quote APPROVED sem OS. Uma OS COMPLETED sem Charge não gera pendência/alerta: Registrar cobrança permanece ação contextual opcional na OS; lista e indicadores financeiros consideram somente cobranças existentes. Não adicionar billing_required, dismissed ou novo estado. Abas OS preservam o baseline, não substituem workflow por formulário gigante.

## Estado → próxima ação

| Contexto | Principal | Secundárias/limites |
|---|---|---|
| Quote DRAFT | Enviar orçamento | Salvar, revisar, cancelar; validar antes de enviar |
| Quote SENT | Compartilhar | Copiar na emissão, rotacionar se perdido, cancelar/duplicar para revisar |
| SENT expirado | Cancelar e preparar nova proposta | EXPIRED derivado, sem aprovação |
| APPROVED sem OS / com OS | Criar/agendar serviço / Ver serviço | Sem edição/reaprovação/segunda conversão |
| Quote CANCELLED | Duplicar | Histórico somente |
| OS DRAFT | Agendar | Preparação e checklist editáveis |
| OS SCHEDULED | Iniciar atendimento | Admin reagenda/cancela; técnico lê preparação |
| OS IN_PROGRESS | Concluir atendimento | Pendências visíveis; ações de checklist/fotos/notas |
| OS COMPLETED | Admin: baixar relatório READY | PENDING aguardar; FAILED retry; cobrança contextual |
| OS CANCELLED | Ver histórico | Sem execução/reabertura |
| Charge PENDING / overdue | Registrar pagamento | Editar/cancelar com motivo |
| Charge PAID/CANCELLED | Ver registro | Terminal |
| Senha temporária | Alterar senha | Logout; navegação operacional bloqueada |

Não usar switches de status genéricos. Modal destrutivo explica efeito e pede motivo quando domínio exige. Conclusão não exige cliente presente nem imagem universalmente; Hero demonstra evidência. Falha PDF é distinta de falha de conclusão.

## Comportamentos de fluxo

Cliente cria com nome; equipamento é opcional e contextual. Archive preserva histórico e restore é explícito. Contato/local do técnico são projeção mínima; não há mapa/GPS.

Onboarding da empresa: formulário Admin permite salvar parcialmente trade_name, phone, email, address e timezone; ausência vem como null e aparece como campo não preenchido, sem valor sentinel. Timezone é escolha IANA explícita, sem pré-selecionar fuso de produção, navegador ou host. is_complete/missing_fields retornados pelo domínio orientam pendências; logo não é obrigatório. Sem timezone não apresentar “hoje”/agenda local inventados: orientar Admin a configurar; login/conta/cadastros continuam acessíveis. Send Quote e start OS mostram impedimento enquanto qualquer um dos cinco campos faltar. Depois de completa, não oferecer limpar campos essenciais; troca de timezone configurada pede confirmação do impacto civil. America/Bahia só aparece previamente preenchida em demo/fixtures Climatech específicas, nunca no onboarding de produção.

Quote editor recebe quantidade/preço como texto decimal pt-BR (vírgula convertida à string canônica). Sem float/Number como fonte de cálculo; estimativa cliente é opcional, total retornado pelo servidor prevalece. Antes de send mostrar resumo/validade; depois campos comerciais somente leitura. “Enviado” não implica mensagem entregue.

Compartilhamento: modal transitório, Copiar link principal, Abrir WhatsApp secundário. Clipboard por gesto; se falhar, seleção manual em memória. WhatsApp abre mensagem genérica pré-preenchida sem token na query, com instrução “Cole o link copiado na conversa e envie”. Ao fechar, limpar segredo. Gerar novo link informa invalidação do anterior; não simular recuperação de hash.

**OPTIONAL/NON-BLOCKING — Web Share API:** progressive enhancement no modal Admin, disponível somente quando navigator.share e contexto seguro permitirem; usar canShare para validar o payload quando disponível. Após gesto explícito, passar o link com fragmento mantido em memória ao share sheet nativo e deixar o Admin escolher o destino. Não usar a URL atual da página Admin, remover o fragmento ou colocar bearer em wa.me query. Copiar link continua fallback sempre acessível; cancelar é neutro, e falhar/indisponível oferece copiar sem afirmar entrega. Sem SDK/polyfill/intermediário obrigatório, envio automático ou dependência para o Hero Flow. O mecanismo de share sheet/gesto é documentado na [Web Share API](https://www.w3.org/TR/web-share/); disponibilidade depende do ambiente, não é prometida pela support matrix.

Público /q limpa fragmento antes de montar UI, mostra projeção do snapshot, logo protegida, total e validade. Identificação do cliente é somente seu nome (client {name}); telefone/e-mail/endereço/ID/notas do cliente não são recebidos, renderizados ou escondidos em HTML/estado. Contatos comerciais da empresa permanecem visíveis. Aprovar abre confirmação textual, e só clique final faz POST. Falha de rede oferece verificar aprovação por GET antes de repetir. APPROVED mostra data estável; quote vencido orienta contato. Acesso inválido/revogado/expirado/cancelado usa tela única “Link indisponível. Peça um novo link à empresa.” Sem conta, menus administrativos ou alegação de assinatura jurídica.

Agenda: Hoje/Semana, data, técnico/status, acesso OS; lista cronológica mobile, grade desktop quando útil. Timezone visível. Início/fim, sugestão60min, end obrigatório. Preview de conflito apresenta Ajustar horário/Agendar mesmo assim. Após save, warning persistente junto ao horário se conflito permaneceu/surgiu; não apenas toast. Drag-and-drop OPTIONAL/NON-BLOCKING.

Execução: checklist indica resposta salvando e erro; bloquear complete enquanto requests locais pendentes. Notas/caption têm save explícito e aviso ao sair com mudanças. Sem promessa de autosave/offline. Upload individual, preview transitório e sucesso apenas após201. Erro orienta JPEG/PNG/WebP/8MiB. Texto não salvo fica somente na aba aberta.

Input de evidência deve permitir os dois caminhos de aquisição: captura pela câmera e seleção da biblioteca. Não assumir formato final a partir do aparelho, extensão ou atributo accept/capture. Em CL-05/CL-06, gate UP-11 executa ambos em iPhone real/Safari suportado, registra MIME/formato entregue e conclui o Hero Flow com ServiceEvidence. Se HEIC entregue pelo ambiente suportado falhar, há blocker antes da release: suporte seguro autorizado ou revisão explícita da support matrix. Converter manualmente uma fixture antes do input não satisfaz o gate; HEIC não foi adicionado à v1 nesta correção.

Confirmação oferece CONFIRMED (nome + declaração explícita) e NOT_AVAILABLE (motivo), sem desenho de assinatura. Admin vê preparar/erro/retry/download PDF; técnico vê OS concluída independentemente do report.

412 preserva formulário, relê e pede revisão antes de novo save; sem merge automático ou overwrite forçado. 401 limpa caches e pede login, sem persistir dados sensíveis para restaurar. Sem feedback otimista para transição, pagamento, conclusão ou upload.

## Componentes e tokens

Escolha: componentes shadcn/ui selecionados baseados em Radix, adaptados em components/ui com tokens ClientOps. Radix para dialog/alert-dialog/dropdown/tabs/tooltip; HTML nativo para button/input/table. Sonner atrás de Toast. Features dependem dos wrappers, sem espalhar primitive imports. Não copiar dashboard/template inteiro. Código copiado precisa de manutenção; a composição ainda exige testes de acessibilidade.

Componentes privados devem respeitar a CSP de SECURITY. /q permanece estrita e script-src 'unsafe-inline' é proibido em todas as experiências. Qualquer necessidade mínima de style inline privado requer documentação da diretiva/componente/rotas e verificação CL-01/CL-02; não relaxar CSP global para acomodar Radix. Preferir ajuste do wrapper/CSS e conferir headers do build servido, incluindo deep links.

| Token | Valor/política |
|---|---|
| canvas / surface | #F8FAFC / #FFFFFF |
| text / text-muted | #0F172A / #475569 |
| border / border-interactive | #E2E8F0 / #64748B; inputs usam o segundo |
| primary / hover / on-primary | #1D4ED8 / #1E40AF / #FFFFFF |
| success-fg / bg | #166534 / #DCFCE7 |
| warning-fg / bg | #92400E / #FEF3C7 |
| danger-fg / bg | #B91C1C / #FEE2E2 |
| info-fg / bg | #1E40AF / #DBEAFE |
| focus | #1D4ED8, anel2px + offset2px |
| Fontes | system-ui/sans-serif; PDF Noto Sans local |
| Tipografia | corpo16/24, apoio14/20, títulos20/28,24/32,32/40; pesos400/500/600 |
| Espaçamento | 4,8,12,16,24,32,48px |
| Radius | controles8px, card/dialog12px; pill só status |
| Sombras | Sem sombra em cards; leve em overlays |
| Densidade | Ações/inputs mobile >=44px; linhas desktop >=44px |

Status tem texto + cor: DRAFT/CANCELLED neutros; SENT/SCHEDULED info; IN_PROGRESS warning; APPROVED/COMPLETED/PAID success; vencidos warning/danger com texto. Nenhuma cor substitui estado persistido.

| Componente | Contrato |
|---|---|
| Button | primary/secondary/tertiary/destructive; busy preserva largura/rótulo; type explícito; disabled explicado |
| FormField | label/id/help/error/aria-describedby; required textual; field path da API |
| StatusBadge | Texto e token sem depender só de cor |
| Card/Table | Título, caption/headers semânticos, ações nomeadas |
| Modal/AlertDialog | Título/descrição, foco contido/restaurado, Escape quando seguro |
| Drawer | Semântica modal, foco e formulário mobile acessível |
| Skeleton | Dimensão estável, aria-hidden e loading anunciado pelo container |
| EmptyState | Motivo e próxima ação permitida |
| ErrorState | Mensagem, retry/relogin por código, request_id opcional |
| Toast | Complementa feedback inline; status/alert; nunca único meio de saber erro |
| Money/DateDisplay | pt-BR, BRL, timezone empresa, distinção civil/instant |
| EvidenceViewer | Stream autorizado, legenda/categoria, alt contextual, sem paths |

## Estados obrigatórios

Normal é conteúdo real com próxima ação. L=loading, E=empty, F=error, D=disabled, S=success.

| Feature | L | E | F | D | S |
|---|---|---|---|---|---|
| Login/troca | botão busy | formulário inicial | credencial genérica/campos | request ativa | destino por papel |
| Cliente/equipamento | skeleton | cadastrar/adicionar | retry com filtros | sem permissão/save | registro salvo |
| Quote editor | skeleton/save | adicionar item | campos/412 | send inválido/SENT | snapshot/link transitório |
| Público | skeleton | reabrir link | indisponível/rede | vencido/aprovando | aprovado/data |
| Agenda | skeleton | nenhum serviço | retry | sem dados/permissão | salvo + warning persistente |
| Checklist | indicador por item | vazio permitido | preserva valor anterior | terminal/salvando | resposta/progresso |
| Evidências | preview enviando | adicionar primeira | tipo/tamanho/rede | quota20/terminal | arquivo salvo |
| Confirmação/conclusão | busy | escolher resolução | pendências/412 | campos faltantes | COMPLETED/PENDING |
| Report | preparando/poll | antes de concluir | FAILED/retry | sem READY | download |
| Charge | skeleton/save | registrar opcional | campo/estado/412 | terminal | pago/cancelado |
| Dashboard/alertas | skeleton seção | sem pendências | erro por seção | role | atualizado sem toast repetitivo |
| Timeline/config | skeleton | sem eventos/profile | retry/fields | permissão | salvo/evento |
| Onboarding empresa | skeleton/save | campos null, timezone não escolhida | campos inválidos/412 | send/start com is_complete=false | configuração completa pelo domínio |

Polling report com página visível a cada5s por até2min, depois Atualizar; não touch de sessão. Público sem polling indefinido.

## Responsividade e browsers

| Gate | Comportamento |
|---|---|
| 390px | Técnico vertical/nav inferior; Admin drawer/lista; público uma coluna; sem overflow |
| 768px | Formulário duas colunas curtas se couber; agenda adaptável |
| 1024px | Sidebar Admin persistente/tabela; técnico task-first |
| 1440px | Admin max1280px, espaço entre agenda/alertas; público max760px |

Também testar reflow320 CSS px/zoom400% onde aplicável. Tabs OS podem rolar com indicação acessível; não esconder ação principal. Sticky respeita safe-area/teclado/foco.

Suporte no release: Chrome/Edge últimas2 versões estáveis; Firefox últimas2 + ESR corrente; Safari macOS/iOS principal atual/anterior; Chrome Android atual/anterior. Floors técnicos: Chromium/Edge111, Firefox128, Safari17. Fora da política corrente não há garantia mesmo acima do floor. Build target explícito compatível; registrar versões exatas em CL-06 e revisar por release. Sem IE/WebViews antigos. CI Chromium/Firefox/WebKit não substitui Safari real/iOS; smoke manual Safari+iOS/Android Chrome obrigatório no release. Tailwind4 requer browsers modernos conforme [fonte oficial](https://tailwindcss.com/docs/compatibility).

O suporte declarado a Safari/iPhone exige o gate de foto real UP-11, além de navegação/smoke. Nenhum formato entregue pela câmera/biblioteca é afirmado antecipadamente. Falha por HEIC em ambiente suportado impede release até uma das duas decisões explícitas de H02; não excluir silenciosamente iOS da matriz nem declarar PASS apenas com Playwright WebKit.

## Acessibilidade e auditoria visual

Meta WCAG2.2 AA aplicável ao app: teclado completo, skip link/landmarks/h1, foco visível não oculto, dialog com contenção/retorno/Escape, labels e erros associados, nome em ícones, status anunciado sem spam. Contraste texto normal>=4.5:1, grande>=3:1; controles/foco>=3:1 quando aplicável. Produto mira44×44px touch (mínimo AA24×24 onde sem exceção). Placeholder não substitui label.

Não depender de drag/hover/cor/gesto complexo. prefers-reduced-motion remove animação desnecessária. Tabelas/cards mantêm labels; erro de formulário leva foco ao resumo com links para campos. Upload tem botão acionável por teclado.

Gate por feature: normal/L/E/F/D/S; quatro viewports; keyboard/zoom/reflow; axe sem serious/critical não justificados; contraste calculado e render conferido; uma ação principal; status textual; sem lorem/dados reais; nenhuma informação de hash/storage/token na jornada comercial. Critérios e exceções referenciam [WCAG2.2](https://www.w3.org/TR/WCAG22/). PDF tem leitura/ordem visual verificadas, sem promessa de PDF/UA.

## Baseline histórico da Foundation CL-01

Na CL-01, o shell React implementou `/admin`, `/tech/today`, `/q` e `/login`, além de redirecionamento `/tech` e 404 contextual. Os três layouts usam lazy loading, landmarks, h1 e skip link. A navegação administrativa usa sidebar a partir de 1024 px e Drawer nativo abaixo desse limite, com Escape e restauração de foco. Naquele baseline ainda não havia login funcional ou guards; a seção CL-02 abaixo substitui esse estado para identidade/configuração.

Os tokens de cor, tipografia, espaçamento, raio, sombra e largura vêm deste contrato e são aplicados por CSS externo compatível com a CSP. Vitest/RTL cobre sete casos; a matriz Playwright em Chromium 390/768/1024/1440, Firefox 1440 e WebKit 390 executou 87 casos com três skips deliberados. Os skips são somente o caso Drawer nos projetos Chromium 1024, Chromium 1440 e Firefox 1440, onde a sidebar substitui o Drawer; a mesma interação passa em Chromium 390, Chromium 768 e WebKit 390. Axe não encontrou violações sérias ou críticas nos shells testados.

## Identidade e configuração CL-02 implementadas

As rotas `/login`, `/change-password`, `/admin/account`, `/admin/settings`, `/admin/settings/users` e `/tech/account` são funcionais. Guards direcionam por papel e forçam a troca de senha temporária. O Admin salva onboarding parcial sem timezone pré-selecionada, vê `missing_fields`/data civil quando disponível e gerencia Técnicos. A senha temporária fica somente em estado React até o card ser fechado, com cópia por gesto; auth, CSRF e credenciais não usam localStorage/sessionStorage.

`/q` permanece no `PublicLayout` isolado, sem provider/cache privado e sem request de sessão. A matriz Playwright CL-02 executa os fluxos reais em Chromium 390/768/1024/1440, Firefox 1440 e WebKit 390; a prova HTTPS adicional confirma o cookie `__Host-` Secure/HttpOnly/Lax em Chromium.

## Clientes e equipamentos CL-03

O Admin acessa `/admin/clients` pela navegação privada, filtra por status, pesquisa e ordena, e abre `/admin/clients/:clientId` para dados, equipamentos e histórico. Cadastro e edição usam labels explícitos, estados de loading/erro/vazio e ações de archive/restore em diálogo. Equipamentos existem somente dentro do detalhe do cliente; cliente arquivado mantém seus equipamentos visíveis e desabilita a inclusão com explicação associada.

Conflito 412 preserva os valores locais, apresenta mensagem e oferece “Recarregar versão atual”; não há merge, overwrite ou retry automático. O Técnico não recebe item Clientes e um deep link Admin retorna ao shell técnico sem renderizar dados. Cards, filtros, diálogos e botões refluem sem overflow nas larguras 390, 768, 1024 e 1440; axe cobre as telas principais no E2E CL-03.

## Orçamentos e aprovação pública CL-04

O Admin acessa `/admin/quotes`, cria rascunhos em `/admin/quotes/new` e usa `/admin/quotes/:quoteId` para editar campos e itens, enviar após confirmação, cancelar, duplicar, rotacionar/revogar o acesso e consultar a timeline. Quantidade e preço permanecem strings; totais exibidos vêm do servidor. Um 412 preserva a edição até a recarga explícita. Após SENT, a proposta comercial fica somente para leitura.

Send e rotate abrem um diálogo transitório com copiar, seleção manual e WhatsApp genérico sem segredo. Fechar remove o link da árvore. Não há Web Share. A navegação Quote existe apenas no shell Admin.

`/q` permanece sem menus ou conta. O fragmento é removido antes do mount; a tela mostra business, nome do cliente, itens, totais, validade, notas e status a partir do snapshot. SENT válido exige confirmação textual antes de aprovar; vencido orienta contato; APPROVED mostra o instante fixado; acesso inválido usa mensagem uniforme. A tabela rolável recebe foco de teclado e a página não causa overflow no viewport móvel.
