FROM python:latest

WORKDIR /service
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && chmod -R 777 /service
COPY demo_service ./demo_service
CMD ["uvicorn", "demo_service.app:app", "--host", "0.0.0.0", "--port", "8080", "--reload"]
