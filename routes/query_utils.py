import bson


def fix_paper_id(paper_id: str):
    return bson.ObjectId(paper_id) if bson.ObjectId.is_valid(paper_id) else paper_id
