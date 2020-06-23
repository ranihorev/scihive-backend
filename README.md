# SciHive 

Read, collaborate and talk about scientific papers.

## Getting started

### 1) Install Postgres

```
podman run --name postgresql -p 5432:5432 -d postgres:latest
```

### Install pgadmin (optional)

Change the default settings.

```
podman run --name pgadmin -p 5050:80 -e "PGADMIN_DEFAULT_EMAIL=pgadmin4@pgadmin.org" -e "PGADMIN_DEFAULT_PASSWORD=admin" -d dpage/pgadmin4
```

### 2) Install Pandoc

Pandoc is needed to support references extraction. Installation can be found here: https://pandoc.org/installing.html.

#### Archlinux
```
sudo pacman -S pandoc
```

### 3) Install pdftotext

`pdftotext` is needed to support acronyms extraction.

#### Archlinux
```
sudo pacman -S poppler
```

#### Ubuntu
```
sudo apt-get install poppler-utils
```

### 4) Configure a virtualenv

```
mkvirtualenv scihive
workon scihive

pip install -r requirements.txt
```

### 5) Set the configuration variables in the .env

Create `.env` file based on the `.env_example` and fill out the values


### 6) Prepare the backend

Run `flask fetch-arxiv` to grab some papers (you can stop the function after fetching ~200 papers) 

### 7) Run the backend

To start the backend
```
flask run
```

To visualize the routes
```
flask routes
```

### 8) See `SciHive.postman_collection.json` for some examples of queries

## Production
- Repeat steps 2-5
- Run `sh restart_server.sh`

### Changelog

- May 31, 2019 - Acronym extraction and enrichment (from other papers)
