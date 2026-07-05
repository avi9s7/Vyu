-- Local-only role separation for migration vs application access.
CREATE ROLE vyu_migrator WITH LOGIN PASSWORD 'local-migrator-password';

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT ALL PRIVILEGES ON DATABASE vyu TO vyu_migrator;
GRANT CREATE ON SCHEMA public TO vyu_migrator;
GRANT USAGE ON SCHEMA public TO vyu_app;

ALTER ROLE vyu_app NOBYPASSRLS NOSUPERUSER;
ALTER ROLE vyu_migrator NOBYPASSRLS;
