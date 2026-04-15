FROM python:3.12-slim

# System deps for lxml (Apple Health XML parser) and pdf processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2-dev libxslt1-dev build-essential poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy sources first so editable install can find `src` package
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -e . && pip cache purge

RUN mkdir -p /app/data /app/uploads

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
