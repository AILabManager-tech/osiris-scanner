FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de

LABEL org.opencontainers.image.title="OSIRIS Scanner" \
      org.opencontainers.image.description="Diagnostic multidimensionnel de sites web" \
      org.opencontainers.image.vendor="Auxo Systems" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app
COPY . /app

RUN python -m pip install --no-cache-dir ".[deep]" \
    && python -m playwright install --with-deps chromium \
    && useradd --create-home --uid 10001 osiris \
    && mkdir -p /tmp/osiris-scanner-web \
    && chown -R osiris:osiris /tmp/osiris-scanner-web /ms-playwright

USER osiris
EXPOSE 25000

ENTRYPOINT ["osiris-web"]
CMD ["--host", "0.0.0.0", "--port", "25000"]
