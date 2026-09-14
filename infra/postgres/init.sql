-- Idempotent bootstrap for the pgvector PostgreSQL image.
-- Schema creation and seed data belong to Alembic/application migrations;
-- this file only enables extensions required by those migrations.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;
SET TIME ZONE 'Asia/Shanghai';
