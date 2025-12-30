FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (better caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .
COPY app_core/ ./app_core/
COPY app_ui/ ./app_ui/
COPY logo/ ./logo/

# Create data directory (will be overwritten by volume mount)
RUN mkdir -p /app/data/media /app/data/uploads

EXPOSE 8517

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8517", "--server.headless=true"]
