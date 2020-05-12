from .new_backend.models import Collection, Comment, Reply, Paper, db, Author, Tag, User, Tweet
import bson
import re
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.exc import MultipleResultsFound
import datetime

# Useful stuff
# paper = db.session.query(Paper).filter(Paper.original_id == rawid).first()
old_group_id_map = {}
data_dir = 'src/new_backend/mongo_data'


def create_comment(doc):
    """
    Creates a comment in Postgres based on the Mongo comment doc
    """
    # Ex:
    # {'_id': ObjectId('5cc657e4debc51503e266113'), 'comment': {'text': ''}, 'content': {'text': 'Deep nonlinear classifiers can fit their data so well that network designers are often faced with thechoice of including stochastic regularizer like adding noise to hidden layers or applying dropout'}, 'position': {'boundingRect': {'x1': 136.15625, 'y1': 576.828125, 'x2': 635.42041015625, 'y2': 605.640625, 'width': 771.6, 'height': 998.5411764705882}, 'rects': [{'x1': 136.15625, 'y1': 576.828125, 'x2': 635.42041015625, 'y2': 591.828125, 'width': 771.6, 'height': 998.5411764705882}, {'x1': 136.15625, 'y1': 590.640625, 'x2': 611.1009521484375, 'y2': 605.640625, 'width': 771.6, 'height': 998.5411764705882}], 'pageNumber': 1}, 'visibility': 'public', 'pid': '1606.08415', 'created_at': datetime.datetime(2019, 4, 29, 1, 48, 20, 966000), 'user': {'username': 'Guest'}}
    id = doc['_id']

    # Skip highlights that don't include text
    if 'content' not in doc:
        return None

    if 'type' in doc['visibility']:
        visibility = doc['visibility']['type']
    else:
        visibility = doc['visibility']

    comment = Comment(text=doc['comment'].get('text'), highlighted_text=doc['content'].get(
        'text'), position=doc['position'], shared_with=visibility, creation_date=doc['created_at'])

    # Adding the shared with property (visibility in the previous Mongo model)

    if visibility == 'group':
        collection = db.session.query(Collection).filter(Collection.old_id == doc['visibility']['id']).first()
        # TODO: should create group if it doesn't exist

        if collection:
            comment.collection = collection

    # Adding the paper
    comment.paper = db.session.query(Paper).filter(Paper.original_id == str(doc['pid'])).first()

    # if not paper:
    #     paper_doc = get_paper_doc(str(doc['pid']))
    #     paper = create_paper(paper_doc)

    # comment.paper = paper

    # Adding the user
    email = doc['user'].get('email')
    user = None

    if email:
        user = db.session.query(User).filter(User.email == email).first()

    if user:
        comment.user = user

    db.session.add(comment)
    db.session.commit()

    # Adding the replies if they exist
    # [{'text': 'asdf', 'created_at': datetime.datetime(2019, 11, 8, 5, 47, 27, 107000), 'id': 'c96b6a13-faac-4376-b3da-63245e0acb1d', 'user': {'email': 'yaron.hadad@gmail.com', 'username': 'Yaron'}}]
    if 'replies' in doc:
        replies_doc = doc['replies']

        for reply_doc in replies_doc:
            reply = Reply(text=reply_doc['text'], creation_date=reply_doc['created_at'], parent=comment)

            if 'email' in reply_doc['user']:
                reply.user = db.session.query(User).filter(User.email == reply_doc['user']['email']).first()

            db.session.add(reply)
            db.session.commit()

    return comment


def convert_comments(file_name=f'{data_dir}/comments.bson'):
    global old_group_id_map
    print('\n\nConverting comments')

    with open(file_name, 'rb') as f:
        for doc in bson.decode_all(f.read()):
            comment = create_comment(doc)


def convert_authors(file_name=f'{data_dir}/authors.bson'):
    print('\n\nConverting authors')
    bson_file = open(file_name, 'rb')

    count = 0
    docs = bson.decode_all(bson_file.read())
    total_authors = len(docs)

    for doc in docs:
        # print(doc)

        # Doc example: {'_id': 'A . M. Barrett', 'papers': ['1905.10835']}
        author_name = doc['_id']

        if type(author_name) == type({}):
            author_name = author_name['name']

        author = db.session.query(Author).filter(Author.name == author_name).first()

        if not author:
            author = Author(name=author_name[:79])
            db.session.add(author)
            db.session.commit()

        for paper_id in doc['papers']:
            # Add relationship between author and paper
            paper = db.session.query(Paper).filter(Paper.original_id == paper_id).first()
            # TODO: should check if relationship exists already?

            # if not paper:
            #     doc = get_paper_doc(paper_id)
            #     paper = create_paper(doc)

            if paper:
                author.papers.append(paper)

        db.session.commit()

        if count % 1000 == 0:
            print(f'{count}/{total_authors} completed')

        count += 1


def get_pdf_link(paper_data):
    for link in paper_data.get('links', []):
        if link.get('type', '') == 'application/pdf':
            return link.get('href', '')

    return paper_data.get('link')


def add_tags(tags, paper, source='arXiv'):
    print("\n\nConverting tags")

    for tag_name in tags:
        # For the time being we ignore non-arxiv tags.
        # ArXiv tags are always of the form archive.subject (https://arxiv.org/help/arxiv_identifier)
        if not re.match('[A-Za-z\\-]+\\.[A-Za-z\\-]+', tag_name):
            continue

        tag = db.session.query(Tag).filter(Tag.name == tag_name).first()

        if not tag:
            tag = Tag(name=tag_name, source=source)
            db.session.add(tag)
            db.session.commit()

        tag.papers.append(paper)

# Returns the tags in a given paper_data (the tags are CS, CS.ML, gr, etc), always in lower-case


def get_tags(paper_data):
    tags = []

    for tag_dict in paper_data.get('tags', []):
        tag = tag_dict.get('term', '')

        if tag != '':
            tags.append(tag)

    return tags


def convert_tags(file_name=f'{data_dir}/papers.bson'):
    """
    Generates all the tags in the first run
    """
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

    paper = None
    original_id = str(doc['_id'])

    # 'md5': 'a62ef6230541e7db562998b2495eaa76', 'time_published': datetime.datetime(2015, 1, 15, 5, 0),
    # 'uploaded_by': {'email': 'jmramirezo@unal.edu.co', 'username': 'jmramirezo'}, 'created_at': datetime.datetime(2020, 1, 15, 16, 24, 0, 442000), 'is_private': True, 'link': 'https://arxiv.lyrn.ai/papers/a62ef6230541e7db562998b2495eaa76.pdf', 'total_bookmarks': 3, 'history': [{'time_published': datetime.datetime(2020, 1, 15, 16, 23, 52), 'stored_at': datetime.datetime(2020, 1, 20, 18, 7, 8, 745000), 'changed_by': 'jmramirezo@unal.edu.co'}
    paper = db.session.query(Paper).filter(Paper.original_id == original_id).first()
    publication_date = doc.get('published')
    last_update_date = doc.get('updated')

    if not publication_date:
        publication_date = datetime.datetime(1970, 1, 1, 5, 0)

    if not last_update_date:
        last_update_date = doc.get('created_at')

    if not paper:
        paper = Paper(title=doc['title'], link=doc['link'], original_pdf=pdf_link, abstract=doc['summary'],
                      is_private=False, publication_date=publication_date, last_update_date=last_update_date, original_id=original_id)

        # Handling tags
        tag_names = get_tags(doc)

        for tag_name in tag_names:
            tag = db.session.query(Tag).filter(Tag.name == tag_name).first()

            if tag:
                paper.tags.append(tag)

        db.session.add(paper)
        db.session.commit()

    return paper


def get_user_doc(user_id, file_name=f'{data_dir}/users.bson'):
    """
    Retrieves the doc of a user by the id
    """
    with open(file_name, 'rb') as f:
        for doc in bson.decode_all(f.read()):
            if doc['_id'] == user_id:
                return doc

    return None


def get_paper_doc(paper_id, file_name=f'{data_dir}/papers.bson'):
    """
    Retrieves the doc of a paper by its id
    """
    with open(file_name, 'rb') as f:
        for doc in bson.decode_all(f.read()):
            if doc['_rawid'] == paper_id:
                return doc

    return None


def fix_papers(file_name=f'{data_dir}/papers.bson'):
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


def convert_papers(file_name=f'{data_dir}/papers.bson'):
    print("\n\nConverting papers")

    current_count = 0

    with open(file_name, 'rb') as f:
        docs = bson.decode_all(f.read())
        papers_count = len(docs)

        for doc in docs:
            # print(doc)
            if current_count % 1000 == 0:
                print(f'{current_count}/{papers_count} compeleted')

            if current_count > 70000:
                create_paper(doc)
            current_count += 1


def create_user(doc):
    """
    Creates a user in Postgres based on a Mongo doc for a user
    """
    # doc = {'_id': ObjectId('5cb76867debc51623e186966'), 'email': 'ranihorev@gmail.com', 'password': 'pbkdf2:sha256:150000$YiHVt53M$743234a52a0e62056f079e8343e71056c728fce95fb8ed46246149a7e6438e1f', 'username': 'ranihorev', 'library': ['1904.08920'], 'groups': [ObjectId('5ccc55cfdebc5136066e913d'), ObjectId('5d9c007fdebc513900073ddf')], 'isAdmin': True, 'library_id': '7e6cf503-721f-4b8a-8447-130088720018'}
    user = db.session.query(User).filter(User.old_id == str(doc['_id'])).first()

    if not user:
        user = User(email=doc['email'], password=doc['password'], username=doc['username'], old_id=str(doc['_id']))
        db.session.add(user)
        db.session.commit()

    # Creating the library for the user
    if 'library_id' in doc:
        collection = db.session.query(Collection).filter(Collection.old_id == doc['library_id']).first()

        if not collection:
            collection = Collection(name='Saved', creation_date=datetime.datetime.utcnow(),
                                    created_by=user, old_id=doc['library_id'])
            db.session.add(collection)
            db.session.commit()

        if not user in collection.users:
            collection.users.append(user)

        # Add library papers TODO: change to library_id object
        # if 'library' in doc:
        #     for paper_id in doc['library']:
        #         paper = db.session.query(Paper).filter(Paper.original_id == paper_id).first()

        #         if not paper:
        #             doc = get_paper_doc(paper_id)
        #             paper = create_paper(doc)

        #         if paper and not paper in collection.papers:
        #             collection.papers.append(paper)

    # TODO: groups

    db.session.commit()
    return user


def convert_users(file_name=f'{data_dir}/users.bson'):
    print("\n\nConverting users")

    # Ex
    # {'_id': ObjectId('5cb76867debc51623e186966'), 'email': 'ranihorev@gmail.com', 'password': 'pbkdf2:sha256:150000$YiHVt53M$743234a52a0e62056f079e8343e71056c728fce95fb8ed46246149a7e6438e1f', 'username': 'ranihorev', 'library': ['1904.08920'], 'groups': [ObjectId('5ccc55cfdebc5136066e913d'), ObjectId('5d9c007fdebc513900073ddf')], 'isAdmin': True, 'library_id': '7e6cf503-721f-4b8a-8447-130088720018'}
    with open(file_name, 'rb') as f:
        for doc in bson.decode_all(f.read()):
            create_user(doc)


def create_group(doc):
    """
    Creates a collection based on a mongo doc of a group
    """

    # {'_id': ObjectId('5cd5e175debc517430f2f957'), 'name': 'Ecology', 'created_at': datetime.datetime(2019, 5, 10, 20, 39, 17, 142000), 'created_by': ObjectId('5cbcccafdebc511d170ab359'), 'users': [ObjectId('5cbcccafdebc511d170ab359')], 'papers': ['1005.3980', '1007.4914', '1010.6251', '0911.5556', '1503.01150', '1906.09144', '1709.01861'], 'color': 'YELLOW'}

    color = doc.get('color', None)

    created_by = str(doc['created_by'])
    created_by_user = db.session.query(User).filter(User.old_id == created_by).first()

    if not created_by_user:
        doc = get_user_doc(created_by)
        created_by_user = create_user(doc)

    collection = db.session.query(Collection).filter(Collection.old_id == str(doc['_id'])).first()

    if not collection:
        collection = Collection(is_library=False, name=doc['name'], color=color, creation_date=doc['created_at'], old_id=str(
            doc['_id']), created_by=created_by_user)

    if not collection.users:
        for user_id in doc['users']:
            user = db.session.query(User).filter(User.old_id == str(user_id)).first()

            if not user:
                user_doc = get_user_doc(user_id)
                user = create_user(user_doc)

            if user not in collection.users:
                collection.users.append(user)

    # if not collection.papers:
    #     if 'papers' in doc:
    #         for paper_id in doc['papers']:
    #             paper = db.session.query(Paper).filter(Paper.original_id == str(paper_id)).first()

    #             if not paper:
    #                 paper_doc = get_paper_doc(paper_id)
    #                 paper = create_paper(paper_doc)

    #             if paper not in collection.papers:
    #                 collection.papers.append(paper)

    db.session.add(collection)
    db.session.commit()

    return collection


def convert_groups(file_name=f'{data_dir}/groups.bson'):
    print("\n\nConverting groups")

    # Ex
    # {'_id': ObjectId('5cd5e175debc517430f2f957'), 'name': 'Ecology', 'created_at': datetime.datetime(2019, 5, 10, 20, 39, 17, 142000), 'created_by': ObjectId('5cbcccafdebc511d170ab359'), 'users': [ObjectId('5cbcccafdebc511d170ab359')], 'papers': ['1005.3980', '1007.4914', '1010.6251', '0911.5556', '1503.01150', '1906.09144', '1709.01861'], 'color': 'YELLOW'}
    with open(file_name, 'rb') as f:
        for doc in bson.decode_all(f.read()):
            collection = create_group(doc)


def convert_group_papers(file_name=f'{data_dir}/group_papers.bson'):
    # Ex
    # {'_id': ObjectId('5dcaf30914029c532302025d'), 'group_id': '   ', 'paper_id': '1904.09970', 'date': datetime.datetime(2019, 11, 12, 17, 59, 37, 829000), 'is_library': True, 'user': '5cbcccafdebc511d170ab359'}
    count = 0

    with open(file_name, 'rb') as f:
        docs = bson.decode_all(f.read())
        total_group_papers = len(docs)

        for doc in docs:
            collection = db.session.query(Collection).filter(Collection.old_id == str(doc['group_id'])).first()
            user = db.session.query(User).filter(User.old_id == str(doc['user'])).first()

            if user and not collection:
                collection = Collection(name='Saved', creation_date=datetime.datetime.utcnow(),
                                        created_by=user, old_id=str(doc['group_id']))
                db.session.add(collection)
                db.session.commit()

            paper = Paper.query.filter(Paper.original_id == str(doc['paper_id'])).first()

            if collection and user and paper:
                collection.papers.append(paper)
            else:
                print("Error mapping group paper")
                print(doc)

            count += 1
            if count % 100 == 0:
                print(f'Parsed {count}/{total_group_papers} group papers')

            db.session.commit()


def create_tweet(doc):
    """
    Creates a Tweet object in Postgres based on a mongo db doc
    """
    # {'_id': '1000018920986808328', 'pids': ['1804.03984'], 'inserted_at_date': datetime.datetime(2020, 5, 1, 23, 46, 44, 341000), 'created_at_date': datetime.datetime(2018, 5, 25, 14, 21, 4), 'created_at_time': 1527258064.0, 'lang': 'en', 'text': 'Coolest part of @aggielaz et al\'s most recent emergent communication paper: when agents jointly learn "conceptual" reprs alongside communication protocol, these concepts are heavily biased by the natural statistics of the environment. https://t.co/K1X6ZSwH3G https://t.co/2eqav3ax6g', 'retweets': 2, 'likes': 5, 'replies': 0, 'user_screen_name': 'j_gauthier', 'user_name': 'Jon Gauthier', 'user_followers_count': 4304, 'user_following_count': 457}

    tweet_id = str(doc['_id'])

    tweet = db.session.query(Tweet).filter(Tweet.id == tweet_id).first()

    if tweet:
        return tweet

    tweet = Tweet(id=tweet_id, insertion_date=doc['inserted_at_date'], creation_date=doc['created_at_date'], lang=doc['lang'], text=doc['text'], retweets=doc['retweets'], likes=doc['likes'], replies=doc.get(
        'replies'), user_screen_name=doc['user_screen_name'], user_name=doc.get('user_name'), user_followers_count=doc['user_followers_count'], user_following_count=doc['user_following_count'])

    paper_id = str(doc['pids'][0])
    tweet.paper = db.session.query(Paper).filter(Paper.original_id == paper_id).first()

    # if not paper:
    #     paper_doc = get_paper_doc(paper_id)
    #     paper = create_paper(paper_doc)

    # tweet.paper = paper # Not sure I can do this, maybe need an add
    db.session.add(tweet)
    db.session.commit()


def convert_tweets(file_name=f'{data_dir}/tweets.bson'):
    print("\n\nConverting tweets")
    # Ex
    # {'_id': '1000018920986808328', 'pids': ['1804.03984'], 'inserted_at_date': datetime.datetime(2020, 5, 1, 23, 46, 44, 341000), 'created_at_date': datetime.datetime(2018, 5, 25, 14, 21, 4), 'created_at_time': 1527258064.0, 'lang': 'en', 'text': 'Coolest part of @aggielaz et al\'s most recent emergent communication paper: when agents jointly learn "conceptual" reprs alongside communication protocol, these concepts are heavily biased by the natural statistics of the environment. https://t.co/K1X6ZSwH3G https://t.co/2eqav3ax6g', 'retweets': 2, 'likes': 5, 'replies': 0, 'user_screen_name': 'j_gauthier', 'user_name': 'Jon Gauthier', 'user_followers_count': 4304, 'user_following_count': 457}
    with open(file_name, 'rb') as f:
        count = 0
        docs = bson.decode_all(f.read())
        total_tweets = len(docs)
        for doc in docs:
            count += 1
            if count % 1000 == 0:
                print(f'{count}/{total_tweets} tweets parsed')

            tweet = create_tweet(doc)


def migrate():
    convert_tags()  # ~1 min
    convert_papers()  # ~45 mins
    convert_authors()  # ~2 hours
    convert_users()
    convert_groups()
    convert_comments()
    convert_tweets()  # 35 mins
    convert_group_papers()  # 1 min

    # Not converting for now
    # convert_acronyms()
