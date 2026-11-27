# Tablero de monitoreo de Centinela (Streamlit, puerto 8501). Lee CENTINELA.PRODUCCION en Snowflake y, si no hay
# conexión (o FUENTE_DATOS=csv), los CSV de docs/ montados en /app/docs.
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt
WORKDIR /app
COPY app.py /app/app.py
EXPOSE 8501
HEALTHCHECK --interval=15s --timeout=5s --retries=10 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health')"
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true", "--browser.gatherUsageStats=false"]
