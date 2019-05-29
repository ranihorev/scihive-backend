import logging
import os
import shutil
import string
import subprocess
from typing import List
import re

import requests
import spacy
from .paper_query_utils import get_paper_with_pdf

logger = logging.getLogger(__name__)

nlp = spacy.load("en_core_web_sm", disable=['parser', 'tagger', 'ner'])

STOPWORDS = ['i', 'me', 'my', 'myself', 'we', 'our', 'ours', 'ourselves', 'you', 'your', 'yours', 'yourself', 'yourselves', 'he', 'him', 'his', 'himself', 'she', 'her', 'hers', 'herself', 'it', 'its', 'itself', 'they', 'them', 'their', 'theirs', 'themselves', 'what', 'which', 'who', 'whom', 'this', 'that', 'these', 'those', 'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'having', 'do', 'does', 'did', 'doing', 'a', 'an', 'the', 'and', 'but', 'if', 'or', 'because', 'as', 'until', 'while', 'of', 'at', 'by', 'for', 'with', 'about', 'against', 'between', 'into', 'through', 'during', 'before', 'after', 'above', 'below', 'to', 'from', 'up', 'down', 'in', 'out', 'on', 'off', 'over', 'under', 'again', 'further', 'then', 'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all', 'any', 'both', 'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 's', 't', 'can', 'will', 'just', 'don', 'should', 'now']
MAX_WORDS_DISTANCE = 10
TMP_DIR = 'acronym_tmp'


def update_curr_result(result, cur_long_word, is_same_long_word):
    if is_same_long_word:
        return result
    return result + [cur_long_word]


def find_long_form(short_form: str, long_form: List[str], result=[], is_same_long_word=False, middle_of_short_word=False):
    if short_form == '':
        return result

    if not long_form:
        return None

    cur_long_word = long_form[0]
    cur_long_word_l = cur_long_word.lower()
    cur_short_word = short_form.lower()

    if middle_of_short_word and cur_long_word_l in STOPWORDS and not is_same_long_word:
        # skip a word only if not in the middle of a long form word
        res = find_long_form(short_form, long_form[1:],
                             update_curr_result(result, cur_long_word, is_same_long_word),
                             False, middle_of_short_word)
        if res:
            return res

    if cur_short_word == cur_long_word_l:
        return None

    if cur_short_word[0] == cur_long_word_l[0]:
        # remove the first word of long form or only the first letter of the first word
        res_next_word = find_long_form(short_form[1:], long_form[1:],
                                       update_curr_result(result, cur_long_word, is_same_long_word),
                                       False, True)
        if res_next_word:
            return res_next_word

        new_long_form = long_form.copy()
        new_long_form[0] = new_long_form[0][1:]
        if len(new_long_form[0]) > 0:
            res_same_word_next_letter = find_long_form(short_form[1:], new_long_form,
                                                       update_curr_result(result, cur_long_word, is_same_long_word),
                                                       True, True)
            if res_same_word_next_letter:
                return res_same_word_next_letter

    if middle_of_short_word:
        return None

    # next word
    return find_long_form(short_form, long_form[1:], [], False, False)


def text_to_tokens(txt):
    doc = nlp(txt.replace('\n', ' '))
    punct = set(list(string.punctuation))
    tokens = [t.string.replace(' ', '') for t in doc]
    tokens = [t for t in tokens if t not in punct and t != '']
    return tokens


def get_dir(paper_id):
    return f'{TMP_DIR}/{paper_id}'


def get_pdf_file(paper_id):
    paper = get_paper_with_pdf(paper_id)
    response = requests.get(paper['pdf_link'])

    curr_dir = get_dir(paper_id)
    if not os.path.exists(curr_dir):
        os.makedirs(curr_dir)

    file_path = f'{curr_dir}/{paper_id}.pdf';
    with open(file_path, 'wb') as f:
        f.write(response.content)
    return file_path


def find_acronyms(paper_id):
    pdf_file_path = get_pdf_file(paper_id)
    txt_file_name = pdf_file_path.replace('pdf', 'txt')
    subprocess.check_output(['pdftotext', pdf_file_path, txt_file_name])
    txt = open(txt_file_name, 'r').read()

    acronyms = re.findall(r'\b(?:[A-Z][a-z]*){2,}', txt)
    tokens = text_to_tokens(txt)

    results = {}

    for acr in acronyms:
        if acr in results:
            continue

        try:
            acr_pos = tokens.index(acr)
            long_form_candidate = tokens[(acr_pos - MAX_WORDS_DISTANCE):acr_pos]
            try:
                long_form = find_long_form(acr, long_form_candidate)
                if long_form:
                    results[acr] = ' '.join(long_form)
            except Exception as e:
                logger.error(f'Failed to find long form - {paper_id} - {acr} - {long_form}')
        except ValueError:
            logging.warning(f'Acronym was not found in text - {acr} - {pdf_file_path}')

    shutil.rmtree(get_dir(paper_id))
    return results
