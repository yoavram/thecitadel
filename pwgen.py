import sys
password = sys.argv[1]

from passlib.apps import custom_app_context as pwd_context

pw_hash = pwd_context.encrypt(password)
print pw_hash
assert pwd_context.verify(password, pw_hash)
