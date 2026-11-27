# Imagen de las tareas de ML de Kestra (produccion_lotes, monitoreo, reentrenamiento).
# Construir:  docker compose build ml      (o: docker build -t centinela-ml:1.0 simulacion)
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
COPY requirements-ml.txt /tmp/requirements-ml.txt
RUN pip install --no-cache-dir -r /tmp/requirements-ml.txt && rm /tmp/requirements-ml.txt
WORKDIR /proyecto
