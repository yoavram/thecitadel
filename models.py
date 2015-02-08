from app import db
from sqlalchemy.dialects.postgresql import JSON


class Product(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String)
    token = db.Column(db.String)
    is_active = db.Column(db.Boolean, default=True)