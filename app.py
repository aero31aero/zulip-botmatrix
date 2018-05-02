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
import json

import deployer
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
			users = User.query.filter_by(api_key=request.headers.get('key')) 
			if not users.count() == 1:
				return abort(401)
			g.user = users[0]
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
def index():
	if g.user:
		return '''
		Welcome to BotMatrix <br>
		Find your API key <a href='/user/key'>here</a>.
		'''
	return '''
	Welcome to BotMatrix <br>
	You must login and then get your API key.<br>
	<a href='/login'>Click Here To Login</a>
	'''

@app.route('/bots/upload', methods=['POST'])
@apikey_check
def upload_file():
	# check if the post request has the file part
	if 'file' not in request.files:
		flash('No file part')
		return redirect(request.url)
	file = request.files['file']
	if file.filename == '':
		flash('No selected file')
		return redirect(request.url)
	if file and allowed_file(file.filename):
		filename = secure_filename(file.filename)
		username = secure_filename(github.get('user').get('login'))
		filename = username + "-" + filename
		filename = filename.lower()
		file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
		return "Bot uploaded successfully. Now you need to process it."

@app.route('/uploads/<filename>')
def uploaded_file(filename):
	return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

def generate_hash_key():
	return hashlib.sha256(str(random.getrandbits(256)).encode('utf-8')).hexdigest()

@app.route('/login/callback')
@github.authorized_handler
def authorized(access_token):
	next_url = request.args.get('next') or '/'
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

@app.route('/bots/process', methods=['POST'])
@apikey_check
def do_process_bot():
	data = request.get_json(force=True)
	if not data.get('name', False):
		return "Specify a bot name."
	username = secure_filename(github.get('user').get('login'))
	bot_root = username + "-" + secure_filename(data.get('name'))
	bot_root = bot_root.lower()
	deployer.extract_file(bot_root)
	if not deployer.check_and_load_structure(bot_root):
		return "Failure. Something's wrong with your zip file."
	deployer.create_docker_image(bot_root)
	return "done"

@app.route('/bots/start', methods=['POST'])
@apikey_check
def do_start_bot():
	data = request.get_json(force=True)
	if not data.get('name', False):
		return "Specify a bot name."
	username = secure_filename(github.get('user').get('login'))
	bot_root = username + "-" + secure_filename(data.get('name'))
	bot_root = bot_root.lower()
	if deployer.start_bot(bot_root):
		return "done"
	return "error"

@app.route('/bots/stop', methods=['POST'])
@apikey_check
def do_stop_bot():
	data = request.get_json(force=True)
	if not data.get('name', False):
		return "Specify a bot name."
	username = secure_filename(github.get('user').get('login'))
	bot_root = username + "-" + secure_filename(data.get('name'))
	bot_root = bot_root.lower()
	deployer.stop_bot(bot_root)
	return "done"

@app.route('/bots/logs/<botname>', methods=['GET'])
@apikey_check
def do_get_log(botname, **kwargs):
	data = request.get_json(force=True)
	lines = data.get('lines', None)
	if not data.get('name', False):
		return "Specify a bot name."
	username = secure_filename(github.get('user').get('login'))
	bot_root = username + "-" + secure_filename(data.get('name'))
	bot_root = bot_root.lower()
	logs = deployer.bot_log(bot_root, lines=lines)
	return logs

@app.route('/bots/delete', methods=['POST'])
@apikey_check
def do_delete_bot():
	data = request.get_json(force=True)
	if not data.get('name', False):
		return "Specify a bot name"
	username = secure_filename(github.get('user').get('login'))
	bot_root = username + "-" + secure_filename(data.get('name'))
	bot_root = bot_root.lower()
	if not deployer.delete_bot(bot_root):
		return "error"
	return "done"

@app.route('/bots/list', methods=['GET'])
@apikey_check
def do_list_bots():
	username = secure_filename(github.get('user').get('login'))
	bots = deployer.get_user_bots(username)
	return json.dumps(dict(bots=bots))

if __name__ == '__main__':
	init_db()
	app.run(debug=True)
