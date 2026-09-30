# ClientOps

Foundation CL-01 do ClientOps. Este repositório contém a API FastAPI, o shell React, PostgreSQL, migrations Alembic, o proxy Nginx, a composição Docker e os testes da fundação. Funcionalidades de identidade e negócio começam em CL-02 e não fazem parte desta entrega.

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
- `/admin`, `/tech/today`, `/q` e `/login`: shells estruturais sem autenticação ou dados comerciais simulados.

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

Os testes PostgreSQL e Compose usam `.local/compose.env` e as imagens fixadas. O workflow `.github/workflows/ci.yml` separa qualidade backend/frontend, migration, drift de contrato, smoke Compose e segurança, com um gate agregado. A execução local valida o arquivo do workflow, mas somente um run do GitHub Actions no SHA publicado constitui evidência de CI real.

## Limites da Foundation

CL-01 possui somente um probe técnico de escrita/leitura/remoção no volume privado. O FileStorage operacional, uploads, relatórios e scheduler entram em CL-05. Usuário, sessão, autenticação, CSRF funcional, BusinessProfile persistido e demais entidades comerciais também não existem nesta fase.
