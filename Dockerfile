FROM python:3.11.2-slim

COPY requirements.txt /tmp/requirements.txt
RUN \
       pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt \
    && mkdir /app

COPY src app/src

WORKDIR /app
ENTRYPOINT ["python3", "src/main.py"]
