from .new_backend.models import Collection, Comment, Reply, Paper, db, Author, Tag, User, Tweet, paper_author_table, user_collection_table, paper_collection_table, paper_tag_table
import bson
import re
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.exc import MultipleResultsFound
import datetime

# Useful stuff
# paper = db.session.query(Paper).filter(Paper.original_id == rawid).first()
old_group_id_map = {}
base_dir = 'src/new_backend/mongo_data'


def create_comment(doc, papers_map, users_by_email, existing_collections):
    """
    Creates a comment in Postgres based on the Mongo comment doc
    """
    # Ex:
    # {'_id': ObjectId('5cc657e4debc51503e266113'), 'comment': {'text': ''}, 'content': {'text': 'Deep nonlinear classifiers can fit their data so well that network designers are often faced with thechoice of including stochastic regularizer like adding noise to hidden layers or applying dropout'}, 'position': {'boundingRect': {'x1': 136.15625, 'y1': 576.828125, 'x2': 635.42041015625, 'y2': 605.640625, 'width': 771.6, 'height': 998.5411764705882}, 'rects': [{'x1': 136.15625, 'y1': 576.828125, 'x2': 635.42041015625, 'y2': 591.828125, 'width': 771.6, 'height': 998.5411764705882}, {'x1': 136.15625, 'y1': 590.640625, 'x2': 611.1009521484375, 'y2': 605.640625, 'width': 771.6, 'height': 998.5411764705882}], 'pageNumber': 1}, 'visibility': 'public', 'pid': '1606.08415', 'created_at': datetime.datetime(2019, 4, 29, 1, 48, 20, 966000), 'user': {'username': 'Guest'}}
    id = doc['_id']

    # Skip highlights that don't include text
    if 'content' not in doc:
        return None, []

    if 'type' in doc['visibility']:
        visibility = doc['visibility']['type']
    else:
        visibility = doc['visibility']

    comment = Comment(text=doc['comment'].get('text'), highlighted_text=doc['content'].get(
        'text'), position=doc['position'], shared_with=visibility, creation_date=doc['created_at'], paper_id=papers_map.get(str(doc['pid'])).id)

    # Adding the shared with property (visibility in the previous Mongo model)

    if visibility == 'group':
        collection = existing_collections.get(doc['visibility']['id'])

        if collection:
            comment.collection_id = collection.id

    # if not paper:
    #     paper_doc = get_paper_doc(str(doc['pid']))
    #     paper = create_paper(paper_doc)

    # comment.paper = paper

    # Adding the user
    email = doc['user'].get('email')
    user = None

    if email:
        user = users_by_email.get(email)
        comment.user_id = user.id

    # Adding the replies if they exist
    # [{'text': 'asdf', 'created_at': datetime.datetime(2019, 11, 8, 5, 47, 27, 107000), 'id': 'c96b6a13-faac-4376-b3da-63245e0acb1d', 'user': {'email': 'yaron.hadad@gmail.com', 'username': 'Yaron'}}]
    replies = []
    if 'replies' in doc:
        replies_doc = doc['replies']

        for reply_doc in replies_doc:
            reply = Reply(text=reply_doc['text'], creation_date=reply_doc['created_at'], parent=comment)

            if 'email' in reply_doc['user']:
                reply.user = users_by_email.get(reply_doc['user']['email'])

            replies.append(reply)

    return comment, replies


def convert_comments(papers_map, file_name='comments.bson'):
    file_name = f"{base_dir}/{file_name}"
    global old_group_id_map
    print('\n\nConverting comments')

    existing_collections = {c.old_id: c for c in db.session.query(Collection).all()}
    users_by_email = {u.email: u for u in User.query.all()}

    all_comments = []
    all_replies = []
    with open(file_name, 'rb') as f:
        for doc in bson.decode_all(f.read()):
            comment, replies = create_comment(doc, papers_map, users_by_email, existing_collections)
            if comment:
                all_comments.append(comment)
            all_replies += replies

    db.session.bulk_save_objects(all_comments)
    db.session.commit()
    db.session.bulk_save_objects(all_replies)
    db.session.commit()


def doc_to_author_name(doc):
    author_name = doc['_id']
    if type(author_name) == type({}):
        author_name = author_name['name']

    author_name = author_name[:199]
    return author_name


def convert_authors(papers_map, file_name=f'authors.bson'):
    file_name = f"{base_dir}/{file_name}"
    print('\n\nConverting authors')
    bson_file = open(file_name, 'rb')

    count = 0
    docs = bson.decode_all(bson_file.read())
    total_authors = len(docs)
    names = set()
    authors = []

    # Create authors
    for doc in docs:

        # Doc example: {'_id': 'A . M. Barrett', 'papers': ['1905.10835']}
        author_name = doc_to_author_name(doc)

        if author_name not in names:
            authors.append(dict(name=author_name))

        if count % 2000 == 0:
            print(f'{count}/{total_authors} completed')
            db.engine.execute(Author.__table__.insert(), authors)
            authors = []

        count += 1

    db.engine.execute(Author.__table__.insert(), authors)

    # Connect to papers
    all_authors = {a.name: a for a in Author.query.all()}

    author_paper_map = []
    count = 0
    for doc in docs:
        author_name = doc_to_author_name(doc)
        author_id = all_authors.get(author_name).id

        for paper_id in doc['papers']:
            paper = papers_map.get(paper_id)  # paper_id is the old id
            if paper:
                author_paper_map.append(dict(author_id=author_id, paper_id=paper.id))
            else:
                print(f'paper id not found {paper_id}')

        if count % 2000 == 0:
            print(f'{count}/{total_authors} completed')
            db.engine.execute(paper_author_table.insert(), author_paper_map)
            author_paper_map = []

        count += 1

    db.engine.execute(paper_author_table.insert(), author_paper_map)


def get_pdf_link(paper_data):
    for link in paper_data.get('links', []):
        if link.get('type', '') == 'application/pdf':
            return link.get('href', '')

    return paper_data.get('link')


def get_tags(paper_data):
    tags = []

    for tag_dict in paper_data.get('tags', []):
        tag = tag_dict.get('term', '')

        if tag != '':
            tags.append(tag)

    return tags


def convert_tags(file_name='papers.bson'):
    """
    Generates all the tags in the first run
    """
    file_name = f"{base_dir}/{file_name}"
    print("\n\nConverting tags")

    all_tags = set()
    count = 0

    # Making a list of all tags to be added
    with open(file_name, 'rb') as f:
        for doc in bson.decode_all(f.read()):
            if count % 1000 == 0:
                print(f'{count} papers scanned, total {len(all_tags)} found so far')

            tags = get_tags(doc)

            for tag_name in tags:
                # For the time being we ignore non-arxiv tags.
                # ArXiv tags are always of the form archive.subject (https://arxiv.org/help/arxiv_identifier)
                if not re.match('[A-Za-z\\-]+\\.[A-Za-z\\-]+', tag_name):
                    continue

                all_tags.add(tag_name)

            count += 1

    print(f'Total {len(all_tags)} unique tags')

    for tag_name in all_tags:
        tag = Tag(name=tag_name, source='arXiv')
        db.session.add(tag)
    db.session.commit()


def create_paper(doc):
    """
    Adds the paper from the Mongo doc into Postgres
    """
    pdf_link = get_pdf_link(doc)

    original_id = str(doc['_id'])

    # 'md5': 'a62ef6230541e7db562998b2495eaa76', 'time_published': datetime.datetime(2015, 1, 15, 5, 0),
    # 'uploaded_by': {'email': 'jmramirezo@unal.edu.co', 'username': 'jmramirezo'}, 'created_at': datetime.datetime(2020, 1, 15, 16, 24, 0, 442000), 'is_private': True, 'link': 'https://arxiv.lyrn.ai/papers/a62ef6230541e7db562998b2495eaa76.pdf', 'total_bookmarks': 3, 'history': [{'time_published': datetime.datetime(2020, 1, 15, 16, 23, 52), 'stored_at': datetime.datetime(2020, 1, 20, 18, 7, 8, 745000), 'changed_by': 'jmramirezo@unal.edu.co'}
    # paper = db.session.query(Paper.id).filter(Paper.original_id == original_id).scalar()
    publication_date = doc.get('published')
    last_update_date = doc.get('updated')

    if not publication_date:
        publication_date = datetime.datetime(1970, 1, 1, 5, 0)

    if not last_update_date:
        last_update_date = doc.get('created_at')

    paper = Paper(title=doc['title'], link=doc['link'], original_pdf=pdf_link, abstract=doc['summary'],
                  is_private=False, publication_date=publication_date, last_update_date=last_update_date, original_id=original_id)

    if 'twtr_sum' in doc:
        paper.twitter_score = doc['twtr_sum']

    return paper


def create_user_map(file_name='users.bson'):
    """
    Retrieves the doc of a user by the id
    """
    file_name = f"{base_dir}/{file_name}"
    users = {}
    with open(file_name, 'rb') as f:
        for doc in bson.decode_all(f.read()):
            users[doc['_id']] = doc

    return users

# def get_paper_doc(paper_id, file_name=f'papers.bson'):
#     """
#     Retrieves the doc of a paper by its id
#     """
#     file_name = f"{base_dir}/{file_name}"
#     with open(file_name, 'rb') as f:
#         for doc in bson.decode_all(f.read()):
#             if doc['_rawid'] == paper_id:
#                 return doc

#     return None


def fix_papers(file_name=f'papers.bson'):
    file_name = f"{base_dir}/{file_name}"
    print("\nFixing papers id")

    current_count = 0

    with open(file_name, 'rb') as f:
        docs = bson.decode_all(f.read())
        papers_count = len(docs)

        for doc in docs:
            # print(doc)
            if current_count % 1000 == 0:
                print(f'{current_count}/{papers_count} compeleted')

            paper = None
            if '_rawid' in doc:
                old_original_id = str(doc['_rawid'])
            else:
                old_original_id = str(doc['_id'])

            original_id = str(doc['_id'])

            # 'md5': 'a62ef6230541e7db562998b2495eaa76', 'time_published': datetime.datetime(2015, 1, 15, 5, 0),
            # 'uploaded_by': {'email': 'jmramirezo@unal.edu.co', 'username': 'jmramirezo'}, 'created_at': datetime.datetime(2020, 1, 15, 16, 24, 0, 442000), 'is_private': True, 'link': 'https://arxiv.lyrn.ai/papers/a62ef6230541e7db562998b2495eaa76.pdf', 'total_bookmarks': 3, 'history': [{'time_published': datetime.datetime(2020, 1, 15, 16, 23, 52), 'stored_at': datetime.datetime(2020, 1, 20, 18, 7, 8, 745000), 'changed_by': 'jmramirezo@unal.edu.co'}
            paper = db.session.query(Paper).filter(Paper.original_id == old_original_id).first()

            if paper:
                paper.original_id = original_id

                db.session.commit()

            current_count += 1


def convert_papers(file_name=f'papers.bson'):
    file_name = f"{base_dir}/{file_name}"
    print("\n\nConverting papers")
    current_count = 0

    with open(file_name, 'rb') as f:
        docs = bson.decode_all(f.read())
        papers_count = len(docs)

        papers = []
        for doc in docs:
            # print(doc)
            if current_count % 1000 == 0:
                print(f'{current_count}/{papers_count} compeleted')

            if current_count % 4000 == 0:
                print('commiting')
                db.session.bulk_save_objects(papers)
                db.session.commit()
                papers = []

            papers.append(create_paper(doc))
            current_count += 1

        db.session.bulk_save_objects(papers)
        db.session.commit()


def convert_users(file_name='users.bson'):
    file_name = f"{base_dir}/{file_name}"
    print("\n\nConverting users")

    # Ex
    # {'_id': ObjectId('5cb76867debc51623e186966'), 'email': 'ranihorev@gmail.com', 'password': 'pbkdf2:sha256:150000$YiHVt53M$743234a52a0e62056f079e8343e71056c728fce95fb8ed46246149a7e6438e1f', 'username': 'ranihorev', 'library': ['1904.08920'], 'groups': [ObjectId('5ccc55cfdebc5136066e913d'), ObjectId('5d9c007fdebc513900073ddf')], 'isAdmin': True, 'library_id': '7e6cf503-721f-4b8a-8447-130088720018'}
    collections = {c.old_id: c for c in db.session.query(Collection).all()}
    with open(file_name, 'rb') as f:
        docs = bson.decode_all(f.read())
        i = 0
        users = []
        for doc in docs:
            # doc = {'_id': ObjectId('5cb76867debc51623e186966'), 'email': 'ranihorev@gmail.com', 'password': 'pbkdf2:sha256:150000$YiHVt53M$743234a52a0e62056f079e8343e71056c728fce95fb8ed46246149a7e6438e1f', 'username': 'ranihorev', 'library': ['1904.08920'], 'groups': [ObjectId('5ccc55cfdebc5136066e913d'), ObjectId('5d9c007fdebc513900073ddf')], 'isAdmin': True, 'library_id': '7e6cf503-721f-4b8a-8447-130088720018'}
            old_id = str(doc['_id'])
            user = User(email=doc['email'], password=doc['password'], username=doc['username'], old_id=old_id)
            users.append(user)

        print('Saving users')
        db.session.bulk_save_objects(users)
        db.session.commit()

        old_id_to_user = {u.old_id: u for u in User.query.all()}

        new_collections = []
        for doc in docs:
            # Creating the library for the user
            if 'library_id' in doc:
                old_user_id = str(doc['_id'])
                collection = collections.get(doc['library_id'])
                user = old_id_to_user.get(old_user_id)

                if not collection:
                    collection = Collection(name='Saved', creation_date=datetime.datetime.utcnow(),
                                            created_by_id=user.id, old_id=doc['library_id'])
                    new_collections.append(collection)

        print('Saving user collections')
        db.session.bulk_save_objects(new_collections)
        db.session.commit()

        print('Adding user to their library')
        user_collection_list = []
        for c in db.session.query(Collection).all():
            user_collection_list.append(dict(user_id=c.created_by_id, collection_id=c.id))

        db.engine.execute(user_collection_table.insert(), user_collection_list)


def convert_groups(file_name=f'groups.bson'):
    file_name = f"{base_dir}/{file_name}"
    print("\n\nConverting groups")

    # Ex
    # {'_id': ObjectId('5cd5e175debc517430f2f957'), 'name': 'Ecology', 'created_at': datetime.datetime(2019, 5, 10, 20, 39, 17, 142000), 'created_by': ObjectId('5cbcccafdebc511d170ab359'), 'users': [ObjectId('5cbcccafdebc511d170ab359')], 'papers': ['1005.3980', '1007.4914', '1010.6251', '0911.5556', '1503.01150', '1906.09144', '1709.01861'], 'color': 'YELLOW'}
    old_users = create_user_map()
    existing_users = {u.old_id: u for u in db.session.query(User).all()}
    existing_collections = {c.old_id: c for c in db.session.query(Collection).all()}

    with open(file_name, 'rb') as f:
        i = 0
        new_collections = []
        docs = bson.decode_all(f.read())
        for doc in docs:
            collection = existing_collections.get(str(doc['_id']))
            if collection:
                continue

            color = doc.get('color', None)
            created_by = str(doc['created_by'])
            created_by_user = existing_users.get(created_by)

            if not created_by_user:
                print(f'creator is missing - {created_by}')

            old_id = str(doc['_id'])
            collection = Collection(name=doc['name'], color=color, creation_date=doc['created_at'],
                                    old_id=old_id, created_by_id=created_by_user.id)
            new_collections.append(collection)

        print('Committing collections')
        db.session.bulk_save_objects(new_collections)
        db.session.commit()

        existing_collections = {c.old_id: c for c in db.session.query(Collection).all()}
        user_collection_list = []
        for doc in docs:
            old_user_ids = [str(u) for u in doc['users']]
            collection = existing_collections.get(str(doc['_id']))

            for user_id in old_user_ids:
                user = existing_users.get(user_id)

                if not user:
                    print(f'user {user_id} is missing')
                    continue

                if user not in collection.users:
                    user_collection_list.append(dict(user_id=user.id, collection_id=collection.id))

        print('Committing users to collections')
        db.engine.execute(user_collection_table.insert(), user_collection_list)


def convert_group_papers(papers_map, file_name=f'group_papers.bson'):
    # Ex
    # {'_id': ObjectId('5dcaf30914029c532302025d'), 'group_id': '   ', 'paper_id': '1904.09970', 'date': datetime.datetime(2019, 11, 12, 17, 59, 37, 829000), 'is_library': True, 'user': '5cbcccafdebc511d170ab359'}
    file_name = f"{base_dir}/{file_name}"
    count = 0

    existing_collections = {c.old_id: c for c in db.session.query(Collection).all()}
    existing_users = {u.old_id: u for u in db.session.query(User).all()}

    with open(file_name, 'rb') as f:
        docs = bson.decode_all(f.read())
        total_group_papers = len(docs)

        new_collection_papers = []
        for doc in docs:
            collection = existing_collections.get(doc['group_id'])
            user = existing_users.get(str(doc['user']))

            if user and not collection:
                old_id = str(doc['group_id'])
                print(f'Adding new collection - this should not happen - {old_id}')
                collection = Collection(name='Saved', creation_date=datetime.datetime.utcnow(),
                                        created_by=user, old_id=old_id)
                db.session.add(collection)
                db.session.commit()

            paper = papers_map.get(str(doc['paper_id']))

            if collection and paper:
                new_collection_papers.append(dict(paper_id=paper.id, collection_id=collection.id,
                                                  date_added=doc.get('date', datetime.datetime.utcnow())))
            else:
                print("Error mapping group paper")
                print(doc)

            count += 1
            if count % 100 == 0:
                print(f'Parsed {count}/{total_group_papers} group papers')

        db.engine.execute(paper_collection_table.insert(), new_collection_papers)


def create_tweet(doc, papers_map):
    """
    Creates a Tweet object in Postgres based on a mongo db doc
    """
    # {'_id': '1000018920986808328', 'pids': ['1804.03984'], 'inserted_at_date': datetime.datetime(2020, 5, 1, 23, 46, 44, 341000), 'created_at_date': datetime.datetime(2018, 5, 25, 14, 21, 4), 'created_at_time': 1527258064.0, 'lang': 'en', 'text': 'Coolest part of @aggielaz et al\'s most recent emergent communication paper: when agents jointly learn "conceptual" reprs alongside communication protocol, these concepts are heavily biased by the natural statistics of the environment. https://t.co/K1X6ZSwH3G https://t.co/2eqav3ax6g', 'retweets': 2, 'likes': 5, 'replies': 0, 'user_screen_name': 'j_gauthier', 'user_name': 'Jon Gauthier', 'user_followers_count': 4304, 'user_following_count': 457}

    tweet_id = str(doc['_id'])

    paper = None
    original_paper_ids = doc['pids']
    for id in original_paper_ids:
        paper = papers_map.get(str(id))
        if paper:
            break

    if not paper:
        print(f'All papers are missing - {original_paper_ids}')
        return None

    tweet = Tweet(id=tweet_id, insertion_date=doc['inserted_at_date'], creation_date=doc['created_at_date'], lang=doc['lang'], text=doc['text'], retweets=doc['retweets'], likes=doc['likes'], replies=doc.get(
        'replies'), user_screen_name=doc['user_screen_name'], user_name=doc.get('user_name'), user_followers_count=doc['user_followers_count'], user_following_count=doc['user_following_count'], paper_id=paper.id)

    return tweet


def convert_tweets(papers_map, file_name=f'tweets.bson'):
    file_name = f"{base_dir}/{file_name}"
    print("\n\nConverting tweets")
    # Ex
    # {'_id': '1000018920986808328', 'pids': ['1804.03984'], 'inserted_at_date': datetime.datetime(2020, 5, 1, 23, 46, 44, 341000), 'created_at_date': datetime.datetime(2018, 5, 25, 14, 21, 4), 'created_at_time': 1527258064.0, 'lang': 'en', 'text': 'Coolest part of @aggielaz et al\'s most recent emergent communication paper: when agents jointly learn "conceptual" reprs alongside communication protocol, these concepts are heavily biased by the natural statistics of the environment. https://t.co/K1X6ZSwH3G https://t.co/2eqav3ax6g', 'retweets': 2, 'likes': 5, 'replies': 0, 'user_screen_name': 'j_gauthier', 'user_name': 'Jon Gauthier', 'user_followers_count': 4304, 'user_following_count': 457}
    with open(file_name, 'rb') as f:
        count = 0
        docs = bson.decode_all(f.read())
        total_tweets = len(docs)
        tweets = []
        for doc in docs:
            count += 1
            if count % 3000 == 0:
                print(f'{count}/{total_tweets} tweets parsed')
                db.session.bulk_save_objects(tweets)
                db.session.commit()
                tweets = []

            tweet = create_tweet(doc, papers_map)
            if tweet:
                tweets.append(tweet)

        db.session.bulk_save_objects(tweets)
        db.session.commit()


def add_tags(papers_map, file_name=f'papers.bson'):
    file_name = f"{base_dir}/{file_name}"
    print("\n\nAdding tags")
    current_count = 0
    all_tags = {tag.name: tag for tag in db.session.query(Tag).all()}

    with open(file_name, 'rb') as f:
        docs = bson.decode_all(f.read())
        papers = []
        i = 0
        paper_tags = []
        for doc in docs:
            original_id = str(doc['_id'])
            tag_names = get_tags(doc)
            paper = papers_map.get(original_id)
            if not paper:
                print(f'Paper is missing - {original_id}')
                continue

            for tag in tag_names:
                tag_obj = all_tags.get(tag)
                if tag_obj:
                    paper_tags.append(dict(paper_id=paper.id, tag_id=tag.id))

        db.engine.execute(paper_tag_table.insert(), paper_tags)


def migrate(data_dir=None):
    global base_dir
    if data_dir:
        base_dir = data_dir

    convert_papers()  # ~45 mins
    papers_map = {p.original_id: p for p in db.session.query(Paper).all()}
    add_tags(papers_map)  # ~1 min
    convert_authors(papers_map)  # ~2 hours
    convert_users()
    convert_groups()
    convert_group_papers(papers_map)  # 1 min
    convert_comments(papers_map)
    convert_tweets(papers_map)  # 35 mins

    # Not converting for now
    # convert_acronyms()
