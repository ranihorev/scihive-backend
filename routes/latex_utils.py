import requests
import tarfile
import os
import re
import logging

from TexSoup import TexSoup

logger = logging.getLogger(__name__)
TMP_DIR = 'tmp'


def get_extension_from_headers(h):
    c_type = h.get('content-type')
    c_encoding = h.get('content-encoding')

    if c_type == 'application/pdf':
        return '.pdf'
    if c_encoding == 'x-gzip':
        if c_type == 'application/postscript':
            return '.ps.gz'
        if c_type == 'application/x-eprint-tar':
            return '.tar.gz'
        if c_type == 'application/x-eprint':
            return '.tex.gz'
        if c_type == 'application/x-dvi':
            return '.dvi.gz'
    return None


# Extract content of tex files from a compressed tar.gz file
def extract_tex_files(file):
    files = []
    tar = tarfile.open(f'{TMP_DIR}/{file}', "r:gz")

    # Find the tex file
    for member in tar.getmembers():
        if member.name.lower().endswith('tex'):
            files.append(tar.extractfile(member).read().decode('utf-8'))

    return files


def arxiv_id_to_source_url(arxiv_id):
    # https://arxiv.org/help/mimetypes has more info
    return 'https://arxiv.org/e-print/' + arxiv_id


# Downloads arxiv latex source code
def download_source_file(arxiv_id):
    source_url = arxiv_id_to_source_url(arxiv_id)
    headers = {
        'User-Agent': 'arXivVanity (https://www.arxiv-vanity.com)',
    }
    res = requests.get(source_url, headers=headers)
    res.raise_for_status()
    extension = get_extension_from_headers(res.headers)
    if not extension:
        raise Exception(f"Could not determine file extension of {arxiv_id}")
    file = res.content
    name = arxiv_id + extension
    if not os.path.exists(TMP_DIR):
        os.makedirs(TMP_DIR)

    with open(f'{TMP_DIR}/{name}', 'wb') as f:
        f.write(file)
    return name


def extract_text(section, tex):
    base_groups = section.groups()
    if '{' not in base_groups[1]:
        return base_groups

    start_pos = section.start()
    # find the beginning of the section element
    while tex[start_pos] != '{':
        start_pos += 1

    # find the right closing brackets
    level = 0
    end_pos = start_pos + 1
    while True:
        if tex[end_pos] == '}':
            if level == 0:
                break
            level -= 1
        elif tex[end_pos] == '{':
            level += 1
        end_pos += 1

    # TODO improve this part
    soup = TexSoup(tex[section.start():end_pos+1])
    section_contents = list(list(soup.tokens)[0].contents)
    name = ''
    for c in section_contents:
        if isinstance(c, str):
            name += c
    return base_groups[0], name


# Gets the sections of a tex file
def get_sections(tex_files):
    for tex in tex_files:
        sections = list(re.finditer(r'\\(section|subsection|subsubsection){(.*?)}', tex))
        if sections:
            res = [extract_text(section, tex) for section in sections]
            return res
    return []


# Gets the sections of a tex file
def get_equations(tex):
    equations = re.findall(r'\\begin\{equation\}(.*?)\\end\{equation\}', tex, re.S)

    return equations


# Gets the references of a tex file
def get_references(tex):
    references = re.findall(r'\\(\bibitem{(.*?)}(.*?))', tex, re.S)
    return references


def extract_data_from_latex(arxiv_id):
    file_name = download_source_file(arxiv_id)
    tex_files = extract_tex_files(file_name)
    return get_sections(tex_files)

