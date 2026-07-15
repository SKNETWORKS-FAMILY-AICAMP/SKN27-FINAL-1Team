FROM python:3.11-slim

WORKDIR /project

RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ && rm -rf /var/lib/apt/lists/*

COPY app/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt lightfm>=1.17

COPY app ./app
COPY ai ./ai

ENV PYTHONPATH=/project
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]