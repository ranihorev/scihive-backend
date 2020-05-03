from .models import Collection, Comment, Paper, db, Author
import bson

# Useful stuff
# paper = db.session.query(Paper).filter(Paper.original_id == rawid).first()

def convert_comments(file_name='mongo_data/comments.bson'):
    with open(file_name, 'rb') as f:
        for doc in bson.decode_all(f.read()):
            # Ex:
            # {'_id': ObjectId('5cc657e4debc51503e266113'), 'comment': {'text': ''}, 'content': {'text': 'Deep nonlinear classifiers can fit their data so well that network designers are often faced with thechoice of including stochastic regularizer like adding noise to hidden layers or applying dropout'}, 'position': {'boundingRect': {'x1': 136.15625, 'y1': 576.828125, 'x2': 635.42041015625, 'y2': 605.640625, 'width': 771.6, 'height': 998.5411764705882}, 'rects': [{'x1': 136.15625, 'y1': 576.828125, 'x2': 635.42041015625, 'y2': 591.828125, 'width': 771.6, 'height': 998.5411764705882}, {'x1': 136.15625, 'y1': 590.640625, 'x2': 611.1009521484375, 'y2': 605.640625, 'width': 771.6, 'height': 998.5411764705882}], 'pageNumber': 1}, 'visibility': 'public', 'pid': '1606.08415', 'created_at': datetime.datetime(2019, 4, 29, 1, 48, 20, 966000), 'user': {'username': 'Guest'}}
            id = doc['_id']
            comment = Comment(text=doc['comment']['text'], highlighted_text=doc['content']['text'], position=doc['position'], shared_with=doc['visibility'], paper_id=doc['pid'], creation_date=doc['created_at'])
            # TODO: handle visibility cases, user
            # TODO: what are collections for?
            # TODO: link to paper
            # TODO: handle reply comments!

    db.session.flush()

def convert_authors(file_name='mongo_data/authors.bson'):
    bson_file = open(file_name, 'rb')

    for doc in bson.decode_all(bson_file.read()):
        # Doc example: {'_id': 'A . M. Barrett', 'papers': ['1905.10835']}
        author_id = doc['_id']

        for paper in doc['papers']:
            author = Author(name=doc['_id'])
            db.session.add(author)

            for paper in doc['papers']:
                print("add relationship between paper and author")

    db.session.flush()


def convert_papers(file_name='mongo_data/papers.bson'):
    with open(file_name, 'rb') as f:
        for doc in bson.decode_all(f.read())[:5]:
            paper = Paper(title=doc['title'], link=doc['link'], original_pdf=doc[''], abstract=doc['summary'], original_id = doc['_rawid'], is_private=False)
            db.session.add(paper)

    db.session.flush()

            # Missing in models
            # original_pdf
            # publication_date
            # last_update_date

            # Not used from mongo
            # authors->authors
            # published / published_parsed -> last_update_date
            # tags -> tags
            # Fields left: 'arxiv_primary_category', 'id', 'links', 'published', 'published_parsed', 'time_published', 'time_updated', 'updated', 'updated_parsed'


def convert_users(file_name='mongo_data/users.bson'):
    # Ex
    # {'_id': ObjectId('5cb76867debc51623e186966'), 'email': 'ranihorev@gmail.com', 'password': 'pbkdf2:sha256:150000$YiHVt53M$743234a52a0e62056f079e8343e71056c728fce95fb8ed46246149a7e6438e1f', 'username': 'ranihorev', 'library': ['1904.08920'], 'groups': [ObjectId('5ccc55cfdebc5136066e913d'), ObjectId('5d9c007fdebc513900073ddf')], 'isAdmin': True, 'library_id': '7e6cf503-721f-4b8a-8447-130088720018'}
    with open(file_name, 'rb') as f:
        for doc in bson.decode_all(f.read())[:5]:
            id = doc['_id']
            user = User(email=doc['email'], password=doc['password'], username=doc['username'])
            db.session.add(user)

    # TODO: groups, library, library_id

    db.session.flush()

def convert_groups(file_name='mongo_data/groups.bson'):
    # Ex
    # {'_id': ObjectId('5cd5e175debc517430f2f957'), 'name': 'Ecology', 'created_at': datetime.datetime(2019, 5, 10, 20, 39, 17, 142000), 'created_by': ObjectId('5cbcccafdebc511d170ab359'), 'users': [ObjectId('5cbcccafdebc511d170ab359')], 'papers': ['1005.3980', '1007.4914', '1010.6251', '0911.5556', '1503.01150', '1906.09144', '1709.01861'], 'color': 'YELLOW'}
    with open(file_name, 'rb') as f:
        for doc in bson.decode_all(f.read())[:5]:
            id = doc['_id']
            collection = Collection(is_library=doc['is_library'], name=doc['name'], color=doc['color'], creation_date=doc['creation_date'])
            db.session.add(collection)

    # TODO: users, papers, created_by, created_by_id
    # Rani said to ignore papers here

    db.session.flush()

def convert_group_papers(file_name='mongo_data/group_papers.bson'):
    pass
    # Ex
    # {'_id': ObjectId('5dcaf30914029c5323020255'), 'group_id': '4f62a896-c054-4d82-83bc-bd8621013438', 'paper_id': '1904.05873', 'date': datetime.datetime(2019, 11, 12, 17, 59, 37, 813000), 'is_library': True, 'user': '5cb37c3ddebc5125a336dcf4'}
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
            tweet = Tweet(paper_id=doc['pids'][0], insertion_date=doc['inserted_at_date'], creation_date=doc['created_at_date'], lang=doc['lang'], text=doc['text'], retweets=doc['retweets'], likes=doc['likes'], replies=doc['replies'], user_screen_name=doc['user_screen_name'], user_name=doc['user_name'], user_followers_count=doc['user_followers_count'], user_following_count=doc['user_following_count'])
            db.session.add(tweet)

    # TODO: why is pids a set of papers?
    # TODO: handle paper
    # TODO: add created_at_time with created_at_date

    db.session.flush()

def main():
    convert_papers()
    convert_authors()
    convert_users()
    convert_groups()
    convert_group_papers()
    convert_comments()
    convert_tweets()
    # convert_acronyms()

if __name__ == '__main__':
    main()
