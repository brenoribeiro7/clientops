#!/bin/sh
set -eu

psql --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=migration_password="$MIGRATION_DATABASE_PASSWORD" \
  --set=runtime_password="$RUNTIME_DATABASE_PASSWORD" <<'SQL'
CREATE ROLE clientops_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD :'migration_password';
CREATE ROLE clientops_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD :'runtime_password';
ALTER DATABASE clientops OWNER TO clientops_migrator;
REVOKE CREATE, TEMPORARY ON DATABASE clientops FROM PUBLIC;
GRANT CONNECT ON DATABASE clientops TO clientops_runtime;
ALTER SCHEMA public OWNER TO clientops_migrator;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO clientops_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE clientops_migrator IN SCHEMA public GRANT SELECT ON TABLES TO clientops_runtime;
SQL
