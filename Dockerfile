FROM python:3.8
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
  poppler-utils \
  pandoc
RUN mkdir /usr/app
WORKDIR /usr/app
COPY ./requirements.txt .
RUN pip install -r requirements.txt
# don't buffer log messages
ENV PYTHONUNBUFFERED=1
COPY ./src ./src
COPY ./migrations ./migrations

ADD ./start.sh .
RUN chmod +x ./start.sh

CMD ["sh", "./start.sh"]