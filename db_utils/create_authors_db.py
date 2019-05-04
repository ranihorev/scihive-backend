import pymongo

client = pymongo.MongoClient()
mdb = client.arxiv
papers = mdb.papers
authors = mdb.authors

for p in list(papers.find()):
    for a in p['authors']:
        authors.update({'_id': a['name']}, {'$addToSet': {'papers': p['_id']}}, True)