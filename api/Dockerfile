FROM python:3.12-slim

# System deps:
#   libxml2/xslt     — Apple Health streaming XML parser (lxml)
#   poppler-utils    — PDF text extraction for medical docs
#   weasyprint deps  — pango, cairo, fontconfig for PDF rendering
#   curl + ca-certs  — needed to fetch Node.js installer
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2-dev libxslt1-dev build-essential poppler-utils \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libfontconfig1 \
    libcairo2 libjpeg62-turbo libgdk-pixbuf-2.0-0 \
    fonts-dejavu fonts-noto-core \
    curl ca-certificates gnupg \
    && rm -rf /var/lib/apt/lists/*

# Node.js 20 + Claude Code CLI.
# Needed so agents can run through the user's Claude Pro/Max subscription via
# CLAUDE_CODE_OAUTH_TOKEN — the claude-agent-sdk Python package spawns this
# CLI as a subprocess. Users on ANTHROPIC_API_KEY don't strictly need it, but
# the ~100MB overhead is cheap vs making two separate images.
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && rm -rf /var/lib/apt/lists/* /root/.npm

WORKDIR /app

# Copy sources first so editable install can find `src` package
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -e . && pip cache purge

RUN mkdir -p /app/data /app/uploads

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
