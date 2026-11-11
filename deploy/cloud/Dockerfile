# Design artifact. Phase 8 does not build or publish this image.
# A later authorized build must install from uv.lock.
# .env is excluded by .dockerignore and must not be copied into a layer.

FROM python:3.13-slim-bookworm

RUN useradd --create-home --uid 10001 cyvora
WORKDIR /app

COPY --chown=cyvora:cyvora pyproject.toml uv.lock README.md ./
COPY --chown=cyvora:cyvora apps config database domain integrations intelligence monitoring operations shield trading backtesting terminal ./

USER cyvora

ENV CYVORA_ENVIRONMENT=local \
    CYVORA_EXECUTION_MODE=READ_ONLY \
    CYVORA_API_HOST=127.0.0.1 \
    CYVORA_API_PORT=8787

EXPOSE 8787

# The process still refuses a non-local environment and a non-loopback bind.
CMD ["python", "-m", "operations.startup", "--ticks", "1"]
