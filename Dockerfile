FROM python:3.11.2-buster

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt
RUN rm /tmp/requirements.txt

RUN mkdir /app
COPY src app/src

WORKDIR /app
ENTRYPOINT ["python3", "src/main.py"]
