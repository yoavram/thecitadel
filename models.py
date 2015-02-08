from sqlalchemy.dialects.postgresql import JSON


class User(db.Model):
    __tablename__ = 'user'    
    email = db.Column(db.String, primary_key=True)
    datetime = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)