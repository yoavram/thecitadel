# -*- coding: utf-8 -*-
import sys
reload(sys)
sys.setdefaultencoding('utf-8')
import codecs, locale
sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

import os
import re
from flask import Flask, abort, make_response, request, Response, redirect, current_app,jsonify
from datetime import timedelta, datetime
from flask.ext.httpauth import HTTPBasicAuth
from flask_sslify import SSLify
from flask.ext.mandrill import Mandrill
from flask.ext.sqlalchemy import SQLAlchemy
from models import User
import uuid

from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from itsdangerous import SignatureExpired, BadSignature
import logging
from passlib.apps import custom_app_context as pwd_context
from functools import wraps
import urlparse
import redis


# add environment variables using 'heroku config:add VARIABLE_NAME=variable_name'
DEBUG = os.environ.get('DEBUG', 'True') == 'True'
TESTING = DEBUG
PASSWORD = os.environ.get('PASSWORD', '$6$rounds=100661$1MPIOVHOyNUNicFJ$6oJ1NSrvVKvKKPvrLinuAEw.ObwBXn10pWQ3KmPcPsYpvuRE0O1XZRHxns4/zuTn2dSQoJUw488tVRvN9RjTx0')
SECRET_KEY = os.environ.get('SECRET_KEY', 'thebestsecretismysecret')
TOKEN_EXPIRATION = int(os.environ.get('TOKEN_EXPIRATION', 3600)) # in secs
REDIS_URI = os.environ.get('REDISCLOUD_URL', 'redis://127.0.0.1:6379')
MANDRILL_API_KEY = os.environ.get('MANDRILL_APIKEY')
MANDRILL_DEFAULT_FROM = os.environ.get('MANDRILL_USERNAME')
SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')


app = Flask(__name__)
sslify = SSLify(app)
auth = HTTPBasicAuth()
app.config.from_object(__name__) 
mandrill = Mandrill(app)
stream_handler = logging.StreamHandler()
app.logger.addHandler(stream_handler)
app.logger.setLevel(logging.INFO)

if app.debug:
	app.logger.setLevel(logging.DEBUG)
	app.logger.info('Running in debug mode')
else:
	app.logger.info('Running in prod mode')

# init db
db = SQLAlchemy(app)

# # init cache store
# app.logger.info("Connecting to Redis")
# redis_url = urlparse.urlparse(app.config['REDIS_URI'])
# redis_store = redis.Redis(host=redis_url.hostname, port=redis_url.port, password=redis_url.password) 
# try:
# 	if redis_store.ping():
# 		app.logger.info("Connected to Redis")
# except:
# 	app.logger.error("Failed connecting to Redis")


def generate_token(email):
	s = Serializer(app.config['SECRET_KEY'], expires_in=app.config['TOKEN_EXPIRATION'])
	return s.dumps({ 'id': user.id, 'email': user.email, 'timestamp': datetime.now().isoformat() })


def verify_token(token):
	s = Serializer(app.config['SECRET_KEY'])
	try:
		data = s.loads(token)
	except SignatureExpired:
		app.logger.info("Token %s from %s expired" % (token, data.get('email', '?')))
		return False # valid token, but expired
	except BadSignature:
		app.logger.info("Bad token: %s" % token)
		return False # invalid token
	if 'timestamp' not in data:
		app.logger.info("Missing timestamp in token: %s" % token)
		return False
	if 'email' not in data:
		app.logger.info("Missing email in token: %s" % token)
		return False
	return data


@app.route('/login', methods=("GET", "POST"))
def login():
	if request.method == "GET":
		return app.send_static_file('login.html')
	else:		
		password = request.form.get('password')		
		if not pwd_context.verify(password, app.config['PASSWORD']):
			app.logger("Bad password: %s" % password)
			abort(403)
		email = request.form.get('email')
		if not email:
			abort(400)
		app.logger("Successful login with email: %s" % email)


		user = User(id=str(uuid.uuid4()),
            		email=email)
		db.session.add(user)
    	db.session.commit()

		token = generate_token(user)
		app.logger("Generated token %s for email %s" % (token, email))

		user.token = token
    	db.session.commit()

		response = mandrill.send_email(
		    from_name='The Citadel',
		    subject='The Citadel Login',
		    html="<p>Thank you for registering with us.<br>To download the data please follow this link or copy it into your browser address bar:<br><a href='%s'>%s</a></p>" % (token, token),
		    to=[{'email': email}],
		    text='Hello World'
		)		
		response = response.json()[0]
		if not response['status'] == 'sent':
			app.logger.warn("Failed sending mail to %s, %s" % (email, response['reject_reason']))
			return app.send_static_file('failure.html')			
		app.logger.debug("Mail sent successfuly to %s" % email)
		return app.send_static_file('success.html')
		

@app.route('/download/<string:token>')
def download(token):
	token_data = verify_token(token)	
	if not token_data:		
		abort(403)
	user = User.query.get(token_data['id'])
	if user.is_active:
		user.is_active = False
		db.session.commit()
		return app.send_static_file('download.html')
	else:
		# TODO error
		abort(403)


if __name__=='__main__':
	port = int(os.environ.get('PORT', 5000))
	host = '0.0.0.0' if os.environ.get('HEROKU') else '127.0.0.1'
	app.logger.info("Starting server at %s:%d" % (host, port))
	app.run(host=host, port=port, debug=app.debug)
	app.logger.info("Server shuting down")
