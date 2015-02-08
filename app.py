# -*- coding: utf-8 -*-
import sys
reload(sys)
sys.setdefaultencoding('utf-8')
import codecs, locale
sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

import os
import re
from datetime import timedelta, datetime
from flask import Flask, request, redirect, jsonify, url_for, abort
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
<a href='%s'>%s</a>.<br>
<br>
The Citadel.
</p>
'''


# add environment variables using 'heroku config:add VARIABLE_NAME=variable_name'
DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'
TESTING = DEBUG
PASSWORD = os.environ.get('PASSWORD', '$6$rounds=100661$1MPIOVHOyNUNicFJ$6oJ1NSrvVKvKKPvrLinuAEw.ObwBXn10pWQ3KmPcPsYpvuRE0O1XZRHxns4/zuTn2dSQoJUw488tVRvN9RjTx0')
SECRET_KEY = os.environ.get('SECRET_KEY', 'thebestsecretismysecret')
TOKEN_EXPIRATION = int(os.environ.get('TOKEN_EXPIRATION', 3600)) # in secs
MANDRILL_API_KEY = os.environ.get('MANDRILL_APIKEY')
MANDRILL_DEFAULT_FROM = os.environ.get('MANDRILL_USERNAME')
SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
RESOURCE_FILEPATH = os.environ.get('RESOURCE_FILEPATH')


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
if not app.config['RESOURCE_FILEPATH']:
	app.logger.error('RESOURCE_FILEPATH config var is missing')

	
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

@app.route('/')
def root():
	return redirect(url_for('signin'))


@app.route('/signin', methods=("GET", "POST"))
def signin():
	if request.method == "GET":
		return app.send_static_file('signin.html')
	password = request.form.get('password', '')		
	if not pwd_context.verify(password, app.config['PASSWORD']):
		app.logger.info("Bad password: %s" % password)
		return jsonify(success=False, reason="Bad password"), 403
	email = request.form.get('email', '')
	if not email:
		app.logger.info("Missing email in request")
		return jsonify(success=False, reason="Email missing request"), 400
	app.logger.info("Successful signin with email: %s" % email)

	# check if user already exists
	user = User.query.get(email)
	if user:
		app.logger.info("Email %s already exists" % (email))
		return jsonify(success=False, reason="Email %s already exists"), 400
	# create new user
		user = User(email=email, datetime=datetime.now())
		db.session.add(user)
		db.session.commit()
	# create user token
	token = generate_token(email)
	app.logger.info("Generated token %s for email %s" % (token, email))
	# send email with user token
	download_url = request.url_root[:-1] + url_for('download', token=token)
	response = mandrill.send_email(
	    from_name='The Citadel',
	    subject='The Citadel signin',
	    html=mail_template % (download_url, download_url),
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
		return abort(403)
	if not 'email' in token_data or not token_data['email']:
		app.logger.error('No email in token: %s' % token)
		return abort(500)
	email = token_data['email']
	user = User.query.get(email)
	if not user:
		app.logger.error("User not found: %s" % email)
		return abort(503)
	if not user.is_active:
		app.logger.debug("User unactive: %s" % email)
		return abort(410)
	user.is_active = False
	db.session.commit()
	expiration = ((user.datetime + timedelta(app.config['TOKEN_EXPIRATION'])) - datetime.now()).total_seconds()
	try:
		app.logger.debug("Creating a link for resource: %s" % app.config['RESOURCE_FILEPATH'])
		response = smartfile_client.post('/path/exchange', path=app.config['RESOURCE_FILEPATH'], expiration=expiration)
		app.logger.debug("SmartFile response: %s" % response)
		return redirect(response.get('url'))
	except smartfile.ResponseError as e:
		#app.logger.error("Failed creating a link for token %s: %s" % (token, e))
		app.logger.error("Failed creating a link: %s" % ( e))
		abort(500)


if __name__=='__main__':
	port = int(os.environ.get('PORT', 5000))
	host = '0.0.0.0' if os.environ.get('HEROKU') else '127.0.0.1'
	app.logger.info("Starting server at %s:%d" % (host, port))
	app.run(host=host, port=port, debug=app.debug)
	app.logger.info("Server shuting down")
