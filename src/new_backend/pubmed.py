import requests
from xml.etree import ElementTree


# PubMed API Documentation
# https://www.ncbi.nlm.nih.gov/pmc/tools/developers/

# Corona terms
# "COVID-19" OR Coronavirus OR "Corona virus" OR "2019-nCoV" OR "SARS-CoV" OR "MERS-CoV" OR “Severe Acute Respiratory Syndrome” OR “Middle East Respiratory Syndrome” 

# Get all the metadata of a paper from PubMed using his PubMed ID
def get_paper_metadata(paper_id):
    # Base URL for fetching metadata on a single paper
    base_url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&retmode=json&tool=SciHive&email=hello@scihive.org'

    # Calling the PubMed API and converting the results to JSON
    response = requests.get(f'{base_url}&id={paper_id}')
    response_json = response.json()
    response_details = response_json['result'][paper_id]

    # Structuring the results
    paper_title = response_details['title']
    paper_pub_date = response_details['pubdate']
    pdf_url = f'https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{paper_id}/pdf/'
    # authors
    # abstract
    # original_json
    # original_id

    return paper_title, paper_pub_date, pdf_url


# Searches a query in PubMed and returns all the IDs of papers that fit that query within the current pagination
def partial_query_pubmed(query, pagination=0, max_results=500):
    # Base URL to work with
    base_url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pmc&tool=SciHive&email=hello@scihive.org&retmode=json'

    # Calling the PubMed API and converting the results to JSON
    response = requests.get(f'{base_url}&term={query}&RetMax={max_results}&RetStart={pagination}')
    response_json = response.json()

    # Get the list of papers IDs
    total_results = response_json['esearchresult']['count']
    paper_ids = response_json['esearchresult']['idlist']

    return paper_ids, int(total_results)


# Searches a query in PubMed and returns all the IDs of papers that fit that query
def query_pubmed(query, max_results=30):
    paper_ids = []

    # Current pagination and the total number of results (initial value is temporary)
    pagination = 0
    total_results = max_results + 1

    # Loops over all pagination to get all paper IDs
    while pagination < total_results:
        partial_paper_ids, total_results = partial_query_pubmed(query, pagination=pagination, max_results=max_results)
        pagination += max_results
        paper_ids += partial_paper_ids

    return paper_ids


def main():
    # ids = query_pubmed('COVID')
    # print(ids)
    # print(len(ids))
    print(get_paper_metadata('2821897'))


if __name__ == '__main__':
    main()
