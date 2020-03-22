
class Author(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, unique=False, nullable=False)
    original_json = db.Column(db.String, unique=False, nullable=False)
