# SciHive 

Read, collaborate and talk about scientific papers.

## Getting started
1. Install Postgres
2. Install `pandoc` to support references extraction from here: https://pandoc.org/installing.html
3. Install `pdftotext` to support acronyms extraction: `sudo apt-get install poppler-utils` (or `brew install poppler` for OSX)
4. Create your Python 3.7 virtual env
5. Create `.env` file based on the `.env_example` and fill out the values
6. Run `flask fetch-papers` to grab some papers (you can stop the function after fetching ~200 papers) 
7. Run `flask run`
8. See `SciHive.postman_collection.json` for some examples of queries


## Production
- Repeat steps 2-5
- Set `RUN_BACKGROUND_TASKS=1` 
- Run `python app.py`

###Changelog

- May 31, 2019 - Acronym extraction and enrichment (from other papers)