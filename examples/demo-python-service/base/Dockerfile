FROM python:3.11.10-slim-bookworm

WORKDIR /service
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY demo_service ./demo_service
USER 10001:10001
CMD ["uvicorn", "demo_service.app:app", "--host", "0.0.0.0", "--port", "8080"]
