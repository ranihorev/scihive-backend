FROM python:3.7-slim
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
  poppler-utils \
  pandoc
RUN mkdir /usr/app/
WORKDIR /usr/app/
COPY ./requirements.txt .
RUN pip install -r requirements.txt
# don't buffer log messages
ENV PYTHONUNBUFFERED=1
COPY ./src ./src

CMD python -m src.app