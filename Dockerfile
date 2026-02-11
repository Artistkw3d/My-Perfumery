FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir flask

COPY app.py .
COPY templates/ templates/
COPY static/ static/

RUN mkdir -p /app/database

EXPOSE 8000

CMD ["python", "app.py"]
