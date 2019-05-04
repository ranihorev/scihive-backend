import pymongo

if __name__ == '__main__':
    client = pymongo.MongoClient()
    mdb = client.arxiv
    papers = mdb.papers
    sem_sch_papers = mdb.sem_sch_papers
    papers.drop_indexes()
    res = papers.create_index(
        [
            ('title', 'text'),
            ('authors.name', 'text'),
            ('summary', 'text'),
            ('tags.term', 'text')
        ],
        weights={
            'title': 10,
            'authors.name': 5,
            'summary': 5,
            'tags.term': 3,
        }
    )

    sem_sch_papers.drop_indexes()
    res = sem_sch_papers.create_index(
        [
            ('title', 'text'),
        ],
    )