FROM python:3.12-slim

# System deps:
#   libxml2/xslt — Apple Health streaming XML parser
#   poppler-utils — PDF text extraction for medical docs
#   weasyprint deps — pango, cairo, fontconfig for PDF rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2-dev libxslt1-dev build-essential poppler-utils \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libfontconfig1 \
    libcairo2 libjpeg62-turbo libgdk-pixbuf-2.0-0 \
    fonts-dejavu fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy sources first so editable install can find `src` package
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -e . && pip cache purge

RUN mkdir -p /app/data /app/uploads

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
