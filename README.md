# ClientOps

ClientOps com a Foundation CL-01, identidade e segurança CL-02, clientes e equipamentos CL-03 e orçamentos com aprovação pública segura CL-04. O repositório contém API FastAPI, aplicação React, PostgreSQL, migrations Alembic, proxy Nginx, composição Docker e testes locais/CI.

## Toolchain fixada

- Python 3.13.15 e uv 0.12.19
- Node 24.21.0 e npm 11.19.0
- PostgreSQL 17.6
- Docker 29.1.3 e Compose 2.40.3 usados na validação local

As dependências Python e JavaScript estão congeladas em `backend/uv.lock` e `frontend/package-lock.json`. As imagens estão fixadas por digest em `infra/images.env`.

## Inicialização local

Prepare segredos descartáveis e suba a pilha a partir da raiz:

```bash
python3.13 infra/dev-env.py
docker compose --env-file infra/images.env --env-file .local/compose.env up --build -d --wait --wait-timeout 180
```

A aplicação fica em `http://127.0.0.1:8080`. O host publica somente o proxy; API e PostgreSQL permanecem nas redes internas. Os endpoints são:

- `GET /api/v1/health/live`: processo HTTP vivo, inclusive durante falha do banco;
- `GET /api/v1/health/ready`: uso interno, verifica PostgreSQL, revisão Alembic exata e probe do volume privado;
- `/login` e `/change-password`: login e troca obrigatória de senha;
- `/admin`, `/admin/account`, `/admin/settings`, `/admin/settings/users`, `/admin/clients` e `/admin/clients/:clientId`: árvore privada do Admin;
- `/tech/today` e `/tech/account`: árvore privada do Técnico;
- `/q`: árvore pública isolada, ainda sem Quote até CL-04.

Não existe conta padrão. Crie o primeiro Admin em um TTY, dentro do container da API:

```bash
docker compose --env-file infra/images.env --env-file .local/compose.env exec api \
  python -m app.cli.create_admin --name "Admin" --email admin@example.com
```

Admins adicionais exigem `--additional`. O reset operacional usa `python -m app.cli.reset_password --email ...`; os dois comandos leem e confirmam a senha sem echo por TTY. `python -m app.cli.benchmark_argon2 --samples 3` mede hash, verify e memória observada sem alterar os parâmetros; a execução real está em [SECURITY](docs/SECURITY.md).

Para a prova TLS local:

```bash
python3.13 infra/dev-env.py --tls
docker compose --env-file infra/images.env --env-file .local/compose.env -f compose.yaml -f compose.tls.yaml up --build -d --wait --wait-timeout 180
```

Ela usa certificado local descartável em `https://127.0.0.1:8443`. Encerre containers preservando dados com `docker compose ... down`. Acrescentar `--volumes` apaga `pg_data` e `private_files` e só é aceitável em ambiente deliberadamente descartável.

### Segredos e volumes existentes

`infra/dev-env.py --force` substitui as credenciais no arquivo local. O PostgreSQL aplica usuários e senhas de inicialização somente quando cria um volume vazio; portanto, regenerar o arquivo e reutilizar `pg_data` deixa as novas credenciais incompatíveis com o volume. Não use `--force` como rotação rotineira. Uma rotação futura exige mudança coordenada das roles no banco e do arquivo de configuração. Apagar `pg_data` é permitido apenas quando o ambiente é descartável e não contém dados relevantes; `private_files` deve ser tratado separadamente.

## Verificação local

```bash
cd backend
uv lock --check
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked pytest -m "not postgres and not compose and not artifacts"

cd ../frontend
npm ci
npm run format:check
npm run lint
npm run typecheck
npm run test:unit
npm run build
```

Os testes PostgreSQL e Compose usam `.local/compose.env` e as imagens fixadas. O workflow `.github/workflows/ci.yml` preserva os gates CL-01/02/03 e acrescenta `quotes-integration`, `quotes-e2e` e `cl04-gate`, totalizando 17 jobs. A execução local valida o arquivo do workflow, mas somente um run do GitHub Actions no SHA publicado constitui evidência de CI real.

## Limites atuais

CL-04 acrescenta somente `quote_number_seq`, `quotes`, `quote_items`, `quote_public_access` e os contextos Quote/PublicAccess na timeline. O FileStorage operacional, uploads, logo persistido, ordens de serviço, relatórios e scheduler entram em CL-05. Não há Redis, JWT, autenticação externa nem infraestrutura paga obrigatória.
