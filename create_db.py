from app import db

print "Creating db..."
db.create_all()
db.session.commit()
print "Done"