# -*- coding: utf-8 -*-
import sys
reload(sys)
sys.setdefaultencoding('utf-8')
import codecs, locale
sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

import os
import re
from datetime import timedelta, datetime
from flask import Flask, request, redirect, jsonify, url_for
from flask_sslify import SSLify
from flask.ext.mandrill import Mandrill
from flask.ext.sqlalchemy import SQLAlchemy
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from itsdangerous import SignatureExpired, BadSignature
import logging
from passlib.apps import custom_app_context as pwd_context
import smartfile
from sqlalchemy.dialects.postgresql import JSON


mail_template = '''<p>Thank you for registering .<br>
To proceed, please follow this link or copy it into your browser address bar:<br>
<a href='%s'>%s</a>
</p>
'''


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
RESOURCE_FILEPATH = os.environ.get('TARGET_FILEPATH')

app = Flask(__name__)
app.config.from_object(__name__) 

# logging
stream_handler = logging.StreamHandler()
app.logger.addHandler(stream_handler)
app.logger.setLevel(logging.INFO)

if app.debug:
	app.logger.setLevel(logging.DEBUG)
	app.logger.info('Running in debug mode')
else:
	app.logger.info('Running in prod mode')

# services
sslify = SSLify(app)
mandrill = Mandrill(app)
db = SQLAlchemy(app)
if db:
	app.logger.info("Connected to database")
else:
	app.logger.error("Failed connecting to database")
try:
	smartfile_client = smartfile.BasicClient()
	response = smartfile_client.get('/ping')
	if response and 'ping' in response and response['ping'] == 'pong':
		app.logger.info("Connected to file store")
	else:
		app.logger.error("Failed connecting to file store")
except:
		app.logger.error("Failed connecting to file store")


class User(db.Model):
    __tablename__ = 'user'    
    email = db.Column(db.String, primary_key=True)
    datetime = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)


def generate_token(email):
	s = Serializer(app.config['SECRET_KEY'], expires_in=app.config['TOKEN_EXPIRATION'])
	return s.dumps({ 'email': email })


def verify_token(token):
	s = Serializer(app.config['SECRET_KEY'])
	try:
		data = s.loads(token)
	except SignatureExpired:
		app.logger.info("Token %s expired" % token)
		return False # valid token, but expired
	except BadSignature:
		app.logger.info("Bad token: %s" % token)
		return False # invalid token	
	return data


@app.route('/login', methods=("GET", "POST"))
def login():
	if request.method == "GET":
		return app.send_static_file('login.html')
			
	password = request.form.get('password', '')		
	if not pwd_context.verify(password, app.config['PASSWORD']):
		app.logger.info("Bad password: %s" % password)
		return jsonify(success=False, reason="Bad password"), 403
	email = request.form.get('email', '')
	if not email:
		app.logger.info("Missing email in request")
		return jsonify(success=False, reason="Email missing request"), 400
	app.logger("Successful login with email: %s" % email)

	# check if user already exists
	user = User.query.get(email)
	if user:
		app.logger.info("Email %s already exists" % (email))
		return jsonify(success=False, reason="Email %s already exists"), 400
	# create new user
	user = User(email=email, timestamp=datetime.now())
	db.session.add(user)
	db.session.commit()
	# create user token
	token = generate_token(email)
	app.logger("Generated token %s for email %s" % (token, email))
	# send email with user token
	response = mandrill.send_email(
	    from_name='The Citadel',
	    subject='The Citadel Login',
	    html=mail_template % (url_for(download) + token),
	    to=[{'email': email}],
	    text='Hello World'
	)		
	response = response.json()[0]
	if response['status'] != 'sent':
		app.logger.warn("Failed sending mail to %s: %s" % (email, response['reject_reason']))
		return jsonify(success=False, reason=response['reject_reason']), 400
	app.logger.debug("Mail sent successfuly to %s" % email)
	return jsonify(success=True), 200
	

@app.route('/download/<string:token>')
def download(token):
	token_data = verify_token(token)	
	if not token_data:
		return jsonify(success=False, reason='Bad token: %s' % token), 403
	if not 'email' in token_data or not token_data['email']:
		return jsonify(success=False, reason='Token missing email: %s' % token), 500
	email = token_data['email']
	user = User.query.get(email)
	if not user:
		return jsonify(success=False, reason='Email address not found : %s' % email), 503
	if not user.is_active:
		return jsonify(success=False, reason='Email address %s already used to download' % email), 410
	user.is_active = False
	db.session.commit()
	expiration = ((user.datetime + timedelta(app.config['TOKEN_EXPIRATION'])) - datetime.now()).total_seconds()
	response = smartfile_client.post('/path/exchange', path=app.config['RESOURCE_FILEPATH'], expiration=expiration)
	return redirect(response.get('url'))


if __name__=='__main__':
	port = int(os.environ.get('PORT', 5000))
	host = '0.0.0.0' if os.environ.get('HEROKU') else '127.0.0.1'
	app.logger.info("Starting server at %s:%d" % (host, port))
	app.run(host=host, port=port, debug=app.debug)
	app.logger.info("Server shuting down")
