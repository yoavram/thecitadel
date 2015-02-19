from app import db
import sys

if raw_input("This will drop all tables in the db, do you want to continue? (y,N)\n") != 'y':
	sys.exit()
db.drop_all()
print "Creating db..."
db.create_all()
db.session.commit()
print "Done"