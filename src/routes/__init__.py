import pymongo

client = pymongo.MongoClient()

mdb = client.arxiv
db_comments = mdb.comments
db_papers = mdb.papers
db_authors = mdb.authors
db_users = mdb.users
db_groups = mdb.groups
db_acronyms = mdb.acronyms
db_group_papers = mdb.group_papers
revoked_tokens = mdb.revoked_tokens