FROM python:3.9-alpine AS temp
RUN apk --no-cache add npm
RUN npm install -g sass
COPY . .

RUN npm ci
ENV NODE_ENV="production"
RUN npm run build
RUN sass scss/main.scss:cubicweb_francearchives/data/css/francearchives.bundle.css
RUN python setup.py sdist

FROM logilab/cubicweb-base:bullseye-1.0@sha256:39e0c229d6fff2a96f17451587dd93022bfead40763267448ad17d53383ad671
USER root
RUN apt update && apt -y --no-install-recommends install \
    screen \
    curl \
    poppler-utils \
    procps \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*
# XXX restart worker after a number of requests (prevent memory leak)
# TODO remove when https://forge.extranet.logilab.fr/cubicweb/docker-cubicweb/-/issues/8 is fixed
RUN echo "max-requests = 128000" >> /etc/uwsgi/uwsgi.ini
# enable stats socket used by uwsgi prometheus exporter
RUN echo "memory-report = true" >> /etc/uwsgi/uwsgi.ini
RUN echo "stats = 127.0.0.1:8001" >> /etc/uwsgi/uwsgi.ini
USER cubicweb
COPY --from=temp dist/cubicweb-francearchives-*.tar.gz .
COPY ./requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt
RUN pip install cubicweb-francearchives-*.tar.gz
RUN pip install pyramid-session-redis
ENV CUBE=francearchives
ENV CW_DB_NAME=${CUBE}
RUN docker-cubicweb-helper create-instance
USER root
RUN rm /requirements.txt
RUN echo "deb http://apt.postgresql.org/pub/repos/apt bullseye-pgdg main" > /etc/apt/sources.list.d/pgdg.list
RUN wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add -
RUN apt-get update
RUN apt-get remove -y postgresql-client
RUN apt-get install -y postgresql-client-12
USER cubicweb
