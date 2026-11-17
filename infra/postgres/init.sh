#!/bin/sh
# Docker entrypoint init script: creates the owner (migrations) and app (runtime, RLS-bound) roles.
set -eu
: "${AISV_OWNER_PASSWORD:?AISV_OWNER_PASSWORD is required}"
: "${AISV_APP_PASSWORD:?AISV_APP_PASSWORD is required}"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v owner_pw="$AISV_OWNER_PASSWORD" -v app_pw="$AISV_APP_PASSWORD" <<'SQL'
CREATE ROLE aisv_owner LOGIN PASSWORD :'owner_pw';
CREATE ROLE aisv_app LOGIN PASSWORD :'app_pw' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
CREATE DATABASE aisv OWNER aisv_owner;
\connect aisv
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO aisv_owner;
GRANT USAGE ON SCHEMA public TO aisv_app;
SQL
