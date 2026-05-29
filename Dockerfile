# Stage 1 — Dépendances Python
FROM python:3.12-slim AS builder

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir --prefix=/install .

# Stage 2 — Runtime avec Chrome + Lighthouse
FROM python:3.12-slim

# Chrome + Lighthouse pour l'axe Performance
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-sandbox \
    nodejs \
    npm \
    && npm install -g lighthouse \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Playwright dependencies pour l'axe Intrusion (mode deep)
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV CHROME_PATH=/usr/bin/chromium

WORKDIR /app

# Copier les dépendances Python depuis le builder
COPY --from=builder /install /usr/local

# Copier le code source
COPY . .

# Installer Playwright Chromium
RUN pip install --no-cache-dir playwright \
    && python -m playwright install chromium --with-deps

# Créer un user non-root
RUN useradd --create-home osiris
USER osiris

ENTRYPOINT ["python", "scanner.py"]
CMD ["--help"]
