FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY ai/calendar/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY ai/calendar /app/ai/calendar

CMD ["python", "-m", "ai.calendar.runpod_handler"]
