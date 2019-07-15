import shutil
import subprocess

import requests
import tarfile
import os
import re
import logging

from TexSoup import TexSoup

logger = logging.getLogger(__name__)
TMP_DIR = 'tmp'
REFERNCES_VERSION = 1.1

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
def extract_files(file, types):
    files = []
    tar = tarfile.open(f'{TMP_DIR}/{file}', "r:gz")

    # Find the tex file
    for member in tar.getmembers():
        if any([member.name.lower().endswith(t) for t in types]):
            try:
                files.append(tar.extractfile(member).read().decode('utf-8'))
            except Exception as e:
                logger.warning(f'Failed to extract reference file - {file} - {member.name}')

    return files


def arxiv_id_to_source_url(arxiv_id):
    # https://arxiv.org/help/mimetypes has more info
    return 'https://arxiv.org/e-print/' + arxiv_id


# Downloads arxiv latex source code
def download_source_file(arxiv_id):
    source_url = arxiv_id_to_source_url(arxiv_id)
    headers = {
        'User-Agent': 'SciHive',
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


def find_right_closing_bracket(tex, start_pos, left_char, right_char):
    # find the right closing brackets
    level = 0
    end_pos = start_pos + 1
    while True:
        if tex[end_pos] == right_char:
            if level == 0:
                break
            level -= 1
        elif tex[end_pos] == left_char:
            level += 1
        end_pos += 1
    return end_pos


def extract_text(section, tex):
    base_groups = section.groups()
    if '{' not in base_groups[1]:
        return base_groups

    start_pos = section.start()
    # find the beginning of the section element
    while tex[start_pos] != '{':
        start_pos += 1

    # find the right closing brackets
    end_pos = find_right_closing_bracket(tex=tex, start_pos=start_pos, left_char='{', right_char='}')

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


def get_cite_name(item):
    # find cite name. Remove the first [] if exists
    if re.match(r'\n\\bibitem\s*\[', item):
        start_pos = item.find('[')
        end_pos = find_right_closing_bracket(item, start_pos, '[', ']')
        item = item[:start_pos] + item[end_pos+1:]
    cite_name = re.search('{(.*?)}', item).group(1)
    return cite_name


def get_bibliography(tex):
    # Focus on the relevant section though it can work without it
    bib_start = tex.find('\\begin{thebibliography}')
    bib_end = tex.find('\\end{thebibliography}')
    bib_content = tex[bib_start: bib_end]
    all_items_matches = list(re.finditer(r'\n\\bibitem\s*[\[\{]', bib_content))
    all_items_content = []

    # split to bibitems:
    for i in range(len(all_items_matches)):
        if i == len(all_items_matches) - 1:
            end_pos = len(bib_content) + 1
        else:
            end_pos = all_items_matches[i + 1].start()
        all_items_content.append(bib_content[all_items_matches[i].start():end_pos])

    return all_items_content


def find_arxiv_id_in_bib_item(item):
    arxiv_links = re.search('\d{4}.\d{4,5}', item)
    if arxiv_links:
        return arxiv_links.group(0)
    return None


def convert_bib_items_to_html(paper_id, items):
    curr_dir = f'{TMP_DIR}/{paper_id}'
    if not os.path.exists(curr_dir):
        os.makedirs(curr_dir)

    htmls = {}
    for item in items:
        item = item.replace('\\newblock', ' ')  # the command \newblock messes up pandoc, so we get rid of it
        filename = f'{curr_dir}/item.txt'
        with open(filename, 'w') as output:
            output.write(item)
        try:
            html = subprocess.check_output(['pandoc', filename, '-f', 'latex', '-t', 'html5']).decode('utf-8')
            htmls[get_cite_name(item)] = {'html': html, 'arxivId': find_arxiv_id_in_bib_item(item)}
        except subprocess.CalledProcessError as e:
            logger.error(f'Failed to render bib item of paper - {paper_id} - {e}')

    shutil.rmtree(curr_dir)
    return htmls


# Gets the references of a tex file
def extract_references_from_latex(arxiv_id):
    file_name = download_source_file(arxiv_id)
    files = extract_files(file_name, ['tex', 'bbl'])
    all_items = []
    for f in files:
        all_items += get_bibliography(f)

    return {'data': convert_bib_items_to_html(arxiv_id, all_items), 'version': REFERNCES_VERSION}


def extract_sections_from_latex(arxiv_id):
    file_name = download_source_file(arxiv_id)
    tex_files = extract_files(file_name, ['tex'])
    return get_sections(tex_files)

