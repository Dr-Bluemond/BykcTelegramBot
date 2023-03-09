FROM python:3.11.2-alpine

COPY requirements.txt /tmp/requirements.txt
RUN \
       pip install -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt \
    && mkdir /app

COPY src app/src

WORKDIR /app
ENTRYPOINT ["python3", "src/main.py"]
