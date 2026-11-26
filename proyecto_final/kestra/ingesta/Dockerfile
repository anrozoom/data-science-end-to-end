# Imagen de la ingesta diaria que ejecutan las tareas de Kestra.
# Construir desde pset_2/:  docker build -t centinela-ingesta:1.0 kestra/ingesta
# Kestra la usa con pullPolicy NEVER: debe existir localmente con este tag.
FROM python:3.11-slim

RUN pip install --no-cache-dir \
        snowflake-connector-python==4.8.0 \
        kaggle==2.2.5 \
        kagglesdk==0.1.38

WORKDIR /app
COPY cargar_dia.py /app/cargar_dia.py
