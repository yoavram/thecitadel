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

# init cache store
app.logger.info("Connecting to Redis")
redis_url = urlparse.urlparse(app.config['REDIS_URI'])
redis_store = redis.Redis(host=redis_url.hostname, port=redis_url.port, password=redis_url.password) 
try:
	if redis_store.ping():
		app.logger.info("Connected to Redis")
except:
	app.logger.error("Failed connecting to Redis")



@app.route('/login', methods=("GET", "POST"))
def login():
	if request.method == "GET":
		return app.send_static_file('login.html')
	else:
		email = request.form.get('email')
		password = request.form.get('password')		
		if not pwd_context.verify(password, app.config['PASSWORD']):
			abort(403)
		response = mandrill.send_email(
		    from_name='The Citadel',
		    subject='Login',
		    to=[{'email': email}],
		    text='Hello World'
		)
		response = response.json()[0]
		if response['status'] == 'sent':
			return "Sent mail to %s" % (response['email'])
		else:
			return "Failed sending mail to %s because" % (response['email'], response['reject_reason'])


if __name__=='__main__':
	port = int(os.environ.get('PORT', 5000))
	host = '0.0.0.0' if os.environ.get('HEROKU') else '127.0.0.1'
	app.logger.info("Starting server at %s:%d" % (host, port))
	app.run(host=host, port=port, debug=app.debug)
	app.logger.info("Server shuting down")
