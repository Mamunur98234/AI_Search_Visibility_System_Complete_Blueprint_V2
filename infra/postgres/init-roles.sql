-- Development/CI bootstrap. Run once as a PostgreSQL superuser.
-- aisv_owner: owns the schema, runs migrations.
-- aisv_app:   used by the API at runtime; NOT owner, NOT superuser, NO BYPASSRLS, so RLS applies.
-- Passwords here are for local development only; production passwords come from your secret store.
CREATE ROLE aisv_owner LOGIN PASSWORD 'change-me-owner';
CREATE ROLE aisv_app LOGIN PASSWORD 'change-me-app' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
CREATE DATABASE aisv OWNER aisv_owner;
CREATE DATABASE aisv_test OWNER aisv_owner;
\connect aisv
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO aisv_owner;
GRANT USAGE ON SCHEMA public TO aisv_app;
\connect aisv_test
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO aisv_owner;
GRANT USAGE ON SCHEMA public TO aisv_app;
CREATE DATABASE aisv_e2e OWNER aisv_owner;
\connect aisv_e2e
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO aisv_owner;
GRANT USAGE ON SCHEMA public TO aisv_app;
