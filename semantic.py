import json
import os
import semanticscholar as sch
import requests
from urllib import parse
import time


# Downloads a file from url into a local folder named local_dir_name.
# If local_file_name is None, then the original file name is maintained
def download_file(url, local_dir_name='', local_file_name=None, timeout=10):
    # Splitting the URL and maintaining the original file name when storing it locally
    url_split = parse.urlsplit(url)

    if local_file_name is None:
        local_file_name = os.path.join(local_dir_name, url_split.path.split("/")[-1])
    else:
        local_file_name = os.path.join(local_dir_name, local_file_name)

    # Download file unless it existed before
    if not os.path.isfile(local_file_name):
        print('...Downloading: {}'.format(url))

        # Check the file type
        request = requests.head(url, timeout=timeout)

        if request.headers.get('Content-Type', '') != 'application/pdf':
            print(f'{url} is not a PDF')
            return False

        # Make the actual request, set the timeout for no data and enable streaming responses so we don't
        # have to keep the large files in memory
        request = requests.get(url, timeout=timeout, stream=True)

        # Open the output file and make sure we write in binary mode
        with open(local_file_name, 'wb') as fh:
            # Walk through the request response in chunks of 1024 * 1024 bytes, so 1MiB
            for chunk in request.iter_content(1024 * 1024):
                # Write the chunk to the file
                fh.write(chunk)

        return True
    else:
        print('...File exists: {}'.format(url))

        return False


def download_papers(dir_name):
    for file_name in os.listdir(f'data/{dir_name}')[:20]:
        with open(f'data/{dir_name}/{file_name}') as f:
            data = json.load(f)
            paper_id = data['paper_id']
            result = download_file(f'https://pdfs.semanticscholar.org/{paper_id[:4]}/{paper_id[4:]}.pdf', local_dir_name='pdfs/')

            if not result:
                print(paper_id)
                
            time.sleep(1)
            
            # print(data['paper_id'])
            # paper = sch.paper(data['paper_id'])
            # print(paper)


def main():
    dir_names = ['biorxiv_medrxiv', 'comm_use_subset', 'noncomm_use_subset', 'pmc_custom_license']

    for dir_name in dir_names:
        download_papers(dir_name)


if __name__ == '__main__':
    main()
