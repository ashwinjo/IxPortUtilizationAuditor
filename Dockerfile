FROM python:3.13-slim

WORKDIR /app

# Install deps in a separate layer for cache efficiency
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY api/       api/
COPY collector/ collector/
COPY web/       web/
COPY mcp/       mcp/

EXPOSE 8890

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8890"]
