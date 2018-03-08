import os
from flask import Flask, request, g, redirect, url_for, send_from_directory, flash, render_template, session, abort
from flask_github import GitHub
from werkzeug.utils import secure_filename
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from functools import wraps
import base64
import hashlib
import random

import dev_config as config

app = Flask(__name__)
app.config.from_object(__name__)

app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['GITHUB_CLIENT_ID'] = config.GITHUB_CLIENT_ID
app.config['GITHUB_CLIENT_SECRET'] = config.GITHUB_CLIENT_SECRET
app.config['DATABASE_URI'] = config.DATABASE_URI
app.config['SECRET_KEY'] = config.SECRET_KEY
app.config['DEBUG'] = config.DEBUG
github = GitHub(app)
engine = create_engine(app.config['DATABASE_URI'])
db_session = scoped_session(sessionmaker(autocommit=False,
										 autoflush=False,
										 bind=engine))
Base = declarative_base()
Base.query = db_session.query_property()


def init_db():
	Base.metadata.create_all(bind=engine)

class User(Base):
	__tablename__ = 'users'

	id = Column(Integer, primary_key=True)
	username = Column(String(200))
	github_access_token = Column(String(200))
	api_key = Column(String(200))

	def __init__(self, github_access_token):
		self.github_access_token = github_access_token

def allowed_file(name):
	return '.' in name and name.rsplit('.', 1)[1].lower() in config.ALLOWED_EXTENSIONS

@app.before_request
def before_request():
	g.user = None
	if 'user_id' in session:
		g.user = User.query.get(session['user_id'])

# The Decorator for checking API Key
def apikey_check(view_function):
	@wraps(view_function)
	def decorated_function(*args, **kwargs):
		if request.headers.get('key'):
			g.user = None
			user = User.query.filter_by(api_key=request.headers.get('key'))
			if not user.count() == 1:
				return abort(401)
			g.user = user[0]
			return view_function(*args, **kwargs)
		else:
			abort(401)
	return decorated_function

import deployer
import dev_config as config

@app.after_request
def after_request(response):
	db_session.remove()
	return response

@github.access_token_getter
def token_getter():
	user = g.user
	if user is not None:
		return user.github_access_token

@app.route("/")
def hello():
	return "Hello World! <a href='/login'>Click Here To Login</a>"

@app.route('/upload', methods=['GET'])
def get_upload_page():
	return '''
	<!doctype html>
	<title>Upload new File</title>
	<h1>Upload new File</h1>
	<form method=post enctype=multipart/form-data>
	  <p><input type=file name=file>
		 <input type=submit value=Upload>
	</form>
	'''

@app.route('/upload', methods=['POST'])
@apikey_check
def upload_file():
	# check if the post request has the file part
	if 'file' not in request.files:
		flash('No file part')
		return redirect(request.url)
	file = request.files['file']
	# if user does not select file, browser also
	# submit a empty part without filename
	if file.filename == '':
		flash('No selected file')
		return redirect(request.url)
	if file and allowed_file(file.filename):
		filename = secure_filename(file.filename)
		username = "anonymous"
		if g.user:
			username = secure_filename(github.get('user').get('login'))
		filename = username + "-" + filename
		file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
		return redirect(url_for('uploaded_file', filename=filename))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
	return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

def generate_hash_key():
    return hashlib.sha256(str(random.getrandbits(256)).encode('utf-8')).hexdigest()

@app.route('/login/callback')
@github.authorized_handler
def authorized(access_token):
	next_url = request.args.get('next') or '/upload'
	if access_token is None:
		return redirect(next_url)

	user = User.query.filter_by(github_access_token=access_token).first()
	if user is None:
		user = User(access_token)
		db_session.add(user)
	user.github_access_token = access_token
	if not user.api_key:
		user.api_key = generate_hash_key()
	db_session.commit()

	session['user_id'] = user.id
	return redirect(next_url)

@app.route('/login')
def login():
	if session.get('user_id', None) is None:
		return github.authorize()
	else:
		return 'Already logged in'

@app.route('/logout')
def logout():
	session.pop('user_id', None)
	return redirect('/')

@app.route('/user')
def user():
	return str(github.get('user'))

@app.route('/user/key')
def user_api_key():
	return g.user.api_key

if __name__ == '__main__':
	init_db()
	app.run(debug=True)
