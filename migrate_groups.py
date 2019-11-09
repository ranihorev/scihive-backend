import uuid
from datetime import datetime

import pymongo

client = pymongo.MongoClient()
mdb = client.arxiv

db_users = mdb.users
db_groups = mdb.groups
db_group_papers = mdb.group_papers

all_users = db_users.find({'library': {"$exists": True}})
for u in all_users:
    if not u.get('library_id'):
        library_id = str(uuid.uuid4())
        db_users.update_one({'_id': u['_id']}, {'$set': {'library_id': library_id}})
        u['library_id'] = library_id
    library_id = u['library_id']

    for p_id in u.get('library', []):
        db_group_papers.insert_one(
            {'paper_id': p_id, 'group_id': library_id, 'date': datetime.now(), 'user': str(u['_id']),
             'is_library': True})

all_groups = db_groups.find()
for g in all_groups:
    papers = g.get('papers', [])
    for p_id in papers:
        db_group_papers.update_one({'paper_id': p_id, 'group_id': str(g['_id'])},
                                   {'$set': {'date': datetime.now(), 'user': str(g.get('created_by'))}},
                                   upsert=False)

