# Database migrations

Alembic revisions for the local PostgreSQL database live in `versions/`.

Do not put passwords, API keys, or wallet material in a revision. The
connection URL is read from `CYVORA_DATABASE_URL` at runtime.
