FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY stremio_addon.py .

ENV PYTHONUNBUFFERED=1
EXPOSE 7000
CMD ["python", "stremio_addon.py"]
