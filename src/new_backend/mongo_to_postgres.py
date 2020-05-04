from .models import Collection, Comment, Paper, db, Author
import bson
import re

# Useful stuff
# paper = db.session.query(Paper).filter(Paper.original_id == rawid).first()
old_paper_id_map = {}
old_group_id_map = {}
old_user_id_map = {}

def convert_comments(file_name='mongo_data/comments.bson'):
    global old_group_id_map

    with open(file_name, 'rb') as f:
        for doc in bson.decode_all(f.read()):
            # Ex:
            # {'_id': ObjectId('5cc657e4debc51503e266113'), 'comment': {'text': ''}, 'content': {'text': 'Deep nonlinear classifiers can fit their data so well that network designers are often faced with thechoice of including stochastic regularizer like adding noise to hidden layers or applying dropout'}, 'position': {'boundingRect': {'x1': 136.15625, 'y1': 576.828125, 'x2': 635.42041015625, 'y2': 605.640625, 'width': 771.6, 'height': 998.5411764705882}, 'rects': [{'x1': 136.15625, 'y1': 576.828125, 'x2': 635.42041015625, 'y2': 591.828125, 'width': 771.6, 'height': 998.5411764705882}, {'x1': 136.15625, 'y1': 590.640625, 'x2': 611.1009521484375, 'y2': 605.640625, 'width': 771.6, 'height': 998.5411764705882}], 'pageNumber': 1}, 'visibility': 'public', 'pid': '1606.08415', 'created_at': datetime.datetime(2019, 4, 29, 1, 48, 20, 966000), 'user': {'username': 'Guest'}}
            id = doc['_id']
            comment = Comment(text=doc['comment']['text'], highlighted_text=doc['content']['text'], position=doc['position'], shared_with=doc['visibility'], paper_id=doc['pid'], creation_date=doc['created_at'])

            # Adding the shared with property (visibility in the previous Mongo model)
            comment.shared_with = comment.TYPES[doc['visibility']['type']]

            if doc['visibility']['type'] == 'group':
                collection = db.session.query(Collection).filter(Collection.id == old_group_id_map[doc['visibility']['id']]).first()
                comment.collection.append(collection)

            # Adding the paper
            paper = db.session.query(Paper).filter(Paper.id == old_paper_id_map[doc['pid']]).first()
            comment.paper = paper

            # Adding the user
            user = db.session.query(User).filter(User.email == doc['user'].get('email')).first()
            if user:
                comment.user = user

            db.session.add(comment)

            # TODO: handle guest? e.g. 'user': {'username': 'Guest'} and 'user': {'email': 'julian.harris@gmail.com', 'username': 'julian'}
            # TODO: handle reply comments!

    db.session.flush()

def convert_authors(file_name='mongo_data/authors.bson'):
    global old_paper_id_map
    bson_file = open(file_name, 'rb')

    for doc in bson.decode_all(bson_file.read()):
        # Doc example: {'_id': 'A . M. Barrett', 'papers': ['1905.10835']}
        author_id = doc['_id']

        for paper in doc['papers']:
            author = Author(name=doc['_id'])
            db.session.add(author)

            # Add relationship between author and paper
            for paper in doc['papers']:
                paper = db.session.query(Paper).filter(Paper.id == old_paper_id_map[paper]).first()
                author.papers.append(paper)

    db.session.flush()

def get_pdf_link(paper_data):
    for link in paper_data.get('links', []):
        if link.get('type', '') == 'application/pdf':
            return link.get('href', '')

    return None

def add_tags(tags, paper, source='arXiv'):
    for tag_name in tags:
        # For the time being we ignore non-arxiv tags.
        # ArXiv tags are always of the form archive.subject (https://arxiv.org/help/arxiv_identifier)
        if not re.match('[A-Za-z\\-]+\\.[A-Za-z\\-]+', tag_name):
            continue

        tag = db.session.query(Tag).filter(Tag.name == tag_name).first()

        if not tag:
            tag = Tag(name=tag_name, source=source)
            db.session.add(tag)

        tag.papers.append(paper)


# Returns the tags in a given paper_data (the tags are CS, CS.ML, gr, etc), always in lower-case
def get_tags(paper_data):
    tags = []

    for tag_dict in paper_data.get('tags', []):
        tag = tag_dict.get('term', '')

        if tag != '':
            tags.append(tag)

    return tags


def convert_papers(file_name='mongo_data/papers.bson'):
    global old_paper_id_map

    with open(file_name, 'rb') as f:
        for doc in bson.decode_all(f.read())[:5]:
            pdf_link = get_pdf_link(doc)
            paper = Paper(title=doc['title'], link=doc['link'], original_pdf=pdf_link, abstract=doc['summary'], original_id = doc['_rawid'], is_private=False, publication_date=doc['published'], last_update_dated=doc[''])

            db.session.add(paper)
            old_paper_id_map[doc['_id']] = paper.id

            # Handling tags
            tags = get_tags(doc)
            add_tags(tags, paper)

    db.session.flush()

    # TODO: Combine published and time_published & updated and time_updated
    # TODO: last_update_date
    # TODO: what is published_parsed and updated_parsed?
    # TODO: should we use arxiv_primary_category?


def convert_users(file_name='mongo_data/users.bson'):
    global old_user_id_map

    # Ex
    # {'_id': ObjectId('5cb76867debc51623e186966'), 'email': 'ranihorev@gmail.com', 'password': 'pbkdf2:sha256:150000$YiHVt53M$743234a52a0e62056f079e8343e71056c728fce95fb8ed46246149a7e6438e1f', 'username': 'ranihorev', 'library': ['1904.08920'], 'groups': [ObjectId('5ccc55cfdebc5136066e913d'), ObjectId('5d9c007fdebc513900073ddf')], 'isAdmin': True, 'library_id': '7e6cf503-721f-4b8a-8447-130088720018'}
    with open(file_name, 'rb') as f:
        for doc in bson.decode_all(f.read())[:5]:
            user = User(email=doc['email'], password=doc['password'], username=doc['username'])
            db.session.add(user)

            # Creating a library for the user
            # TODO: color? what should be the creation_date?
            collection = Collection(is_library=True, name='Saved')
            db.session.add(collection)

            # Add papers in library
            for paper in doc['library']:
                collection.papers.add(paper)

            old_user_id_map[doc['_id']] = user.id

    # TODO: groups
    # TODO: what about library_id??

    db.session.flush()

def convert_groups(file_name='mongo_data/groups.bson'):
    # Ex
    # {'_id': ObjectId('5cd5e175debc517430f2f957'), 'name': 'Ecology', 'created_at': datetime.datetime(2019, 5, 10, 20, 39, 17, 142000), 'created_by': ObjectId('5cbcccafdebc511d170ab359'), 'users': [ObjectId('5cbcccafdebc511d170ab359')], 'papers': ['1005.3980', '1007.4914', '1010.6251', '0911.5556', '1503.01150', '1906.09144', '1709.01861'], 'color': 'YELLOW'}
    with open(file_name, 'rb') as f:
        for doc in bson.decode_all(f.read()):
            collection = Collection(is_library=doc['is_library'], name=doc['name'], color=doc['color'], creation_date=doc['created_at'])

            user = db.session.query(User).filter(User.id == old_user_id_map[doc['users'][0]]).first()
            
            if user:
                collection.user = user

            db.session.add(collection)

    # TODO: is created_by and user the same?

    db.session.flush()

def convert_group_papers(file_name='mongo_data/group_papers.bson'):
    # Ex
    # {'_id': ObjectId('5dcaf30914029c532302025d'), 'group_id': 'a3b56b94-aab2-4018-bf8a-13e1e5218ba7', 'paper_id': '1904.09970', 'date': datetime.datetime(2019, 11, 12, 17, 59, 37, 829000), 'is_library': True, 'user': '5cbcccafdebc511d170ab359'}
    # with open(file_name, 'rb') as f:
    #     for doc in bson.decode_all(f.read())[:5]:
    #         id = doc['_id']
    #         collection = Collection(is_library=doc['is_library'], name=doc['name'], color=doc['color'], creation_date=doc['creation_date'])
    #         db.session.add(collection)

    # # TODO: users, papers, created_by, created_by_id

    # db.session.flush()

def convert_tweets(file_name='mongo_data/tweets.bson'):
    # Ex
    # {'_id': '1000018920986808328', 'pids': ['1804.03984'], 'inserted_at_date': datetime.datetime(2020, 5, 1, 23, 46, 44, 341000), 'created_at_date': datetime.datetime(2018, 5, 25, 14, 21, 4), 'created_at_time': 1527258064.0, 'lang': 'en', 'text': 'Coolest part of @aggielaz et al\'s most recent emergent communication paper: when agents jointly learn "conceptual" reprs alongside communication protocol, these concepts are heavily biased by the natural statistics of the environment. https://t.co/K1X6ZSwH3G https://t.co/2eqav3ax6g', 'retweets': 2, 'likes': 5, 'replies': 0, 'user_screen_name': 'j_gauthier', 'user_name': 'Jon Gauthier', 'user_followers_count': 4304, 'user_following_count': 457}
    with open(file_name, 'rb') as f:
        for doc in bson.decode_all(f.read())[:5]:
            id = doc['_id']
            tweet = Tweet(insertion_date=doc['inserted_at_date'], creation_date=doc['created_at_date'], lang=doc['lang'], text=doc['text'], retweets=doc['retweets'], likes=doc['likes'], replies=doc['replies'], user_screen_name=doc['user_screen_name'], user_name=doc['user_name'], user_followers_count=doc['user_followers_count'], user_following_count=doc['user_following_count'])
            tweet.paper_id = doc['pids'][0] # Not sure I can do this, maybe need an add
            db.session.add(tweet)

    # TODO: why is pids a set of papers?
    # TODO: add created_at_time with created_at_date

    db.session.flush()

def main():
    convert_papers()
    convert_authors()
    convert_users()
    convert_groups()
    # convert_group_papers() # TODO
    convert_comments()
    convert_tweets()
    # convert_acronyms()

if __name__ == '__main__':
    main()
