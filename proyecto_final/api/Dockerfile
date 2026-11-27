# Imagen de la API de inferencia de Centinela.
# El modelo NO va dentro de la imagen: se carga al arrancar desde MLflow (MODELO_URI, por defecto
# models:/centinela-modelo@champion) y se recarga si el alias cambia. Cambiar de modelo no reconstruye la imagen.
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY esquemas.py registro.py main.py catalogos.json ./
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=10 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/salud')"
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
