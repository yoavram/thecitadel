from app import User

print "Getting all users"
users = User.query.all()
print users