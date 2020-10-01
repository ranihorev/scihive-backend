# SciHive 

Read, collaborate and talk about scientific papers.

## Development
To get started, create a local copy of `.env_example` and modify according to your environment if needed.
Without making any changes, you should be able to run the web worker out-of-the-box via docker. 

### Develop using Docker
Run `docker-compose up` to get a postgres DB and web worker up and running on docker images.

The web worker will auto reload code changes and apply them immediately. For non-code 
changes (e.g. environment variables, configurations), interrupt the running process and re-run `docker-compose up`.

#### Updating python dependencies
When changing the `requirements.txt` file, we need to rebuild the docker image. We can do that by
simply adding the `build` flag on our next run: `docker-compose up --build` 

#### Resetting your local env (including your Postgres data)
Run `docker-compose down --rmi all --volumes` to remove all the container volumes and get 
a fresh start on your next `up` command. This is mostly useful if you want a fresh database volume.

#### Seeding papers locally
To grab some papers locally, we'd like to run the `fetch-arxiv` command within our web instance.
With your docker instances running, run `docker ps` to find the running web instance names.
Assuming that it's `scihive-backend_web_1`, you can then run 
`docker exec -it scihive-backend_web_1 bash -c "flask fetch-arxiv"` to grab some papers. You can 
just kill the process after a couple hundered papers were scraped.

The papers will be downloaded into a local folder on your web container, configured by `LOCAL_FILES_DIRECTORY`
(defaulting to `/tmp/scihive-papers/`). We can access them by opening a shell in the container:
`docker exec -it scihive-backend_web_1 bash`.

### Develop directly on your machine
1. Install Postgres
1. Install `pandoc` to support references extraction from here: https://pandoc.org/installing.html
1. Install `pdftotext` to support acronyms extraction: `sudo apt-get install poppler-utils`
1. Create your Python 3.7 virtual env
1. Update your local .env file to match your environment
1. Run `flask fetch-arxiv` to grab some papers (you can stop the function after fetching ~200 papers)  
1. Run `flask run`
1. See `SciHive.postman_collection.json` for some examples of queries


## Production
- Repeat steps 2-5 from the [Develop directly on your machine](#develop-directly-on-your-machine) section
- Run `sh restart_server.sh`

###Changelog

- May 31, 2019 - Acronym extraction and enrichment (from other papers)