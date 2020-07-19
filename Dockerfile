FROM python:3.7-slim
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    poppler-utils \
    pandoc
RUN mkdir /usr/src/app
WORKDIR /usr/src/app
COPY ./requirements.txt .
RUN pip install -r requirements.txt
# don't buffer log messages
ENV PYTHONUNBUFFERED=1
COPY . .