import requests
import tarfile
import os
import re

arxiv_prefix = "https://arxiv.org/e-print/"


# Extract content of tex files from a compressed tar.gz file
def extract_tex(input_file):
	print("Extracting TAR: {}".format(input_file))
	tex = None
	tar = tarfile.open(input_file, "r:gz")

	# Find the tex file
	for member in tar.getmembers():
		if member.name.lower().endswith('tex'):
			with tar.extractfile(member) as m:
				tex = m.read()

	return tex.decode('utf-8')


# Downloads arxiv latex source code
def download_arxiv_source(arxiv_id):
	print("Downloading paper id: {}".format(arxiv_id))

	url = arxiv_prefix + arxiv_id
	r = requests.get(url)

	# Saving received content as a tar.gz file in the papers folder
	file_name = "papers/{}.tar.gz".format(arxiv_id)

	with open(file_name,'wb') as f: 
	    f.write(r.content)

	return (file_name)


# Gets the sections of a tex file
def get_sections(tex):
	sections = re.findall(r'\\(section|subsection|subsubsection){(.*?)}', tex, re.S)
	
	return(sections)


# Gets the sections of a tex file
def get_equations(tex):
	equations = re.findall(r'\\begin\{equation\}(.*?)\\end\{equation\}', tex, re.S)
	
	return(equations)


# Gets the references of a tex file
def get_references(tex):
	references = re.findall(r'\\(\bibitem{(.*?)}(.*?)', tex, re.S)

	return(references)


def main():
	arxiv_ids = ["1905.02383"] #, "1905.03670", "1905.03776"]

	for arxiv_id in arxiv_ids:
		file_name = download_arxiv_source(arxiv_id)
		tex = extract_tex(file_name)

		print(get_sections(tex))
		print(get_equations(tex))
		# print(get_references(tex))


if __name__ == "__main__":
	main()
