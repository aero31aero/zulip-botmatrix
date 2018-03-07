import os
from flask import Flask, request, g, redirect, url_for, send_from_directory, flash, render_template, session, abort
from flask_github import GitHub
from werkzeug.utils import secure_filename
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base

ALLOWED_EXTENSIONS = set(['zip', 'zbot'])
UPLOAD_FOLDER = 'bots'

DATABASE_URI = 'sqlite:////tmp/github-flask.db'
SECRET_KEY = 'development key'
DEBUG = True

GITHUB_CLIENT_ID = 'c233f46559fe59d748e2'
GITHUB_CLIENT_SECRET = 'c76d2178870fd509a2f01b433cb4c3789da40699'

app = Flask(__name__)
app.config.from_object(__name__)
github = GitHub(app)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['GITHUB_CLIENT_ID'] = GITHUB_CLIENT_ID
app.config['GITHUB_CLIENT_SECRET'] = GITHUB_CLIENT_SECRET

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

	def __init__(self, github_access_token):
		self.github_access_token = github_access_token

def allowed_file(name):
	return '.' in name and name.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.before_request
def before_request():
	g.user = None
	if 'user_id' in session:
		g.user = User.query.get(session['user_id'])

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
	return "Hello World! <a href='/upload'>Click Here</a>"

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
		file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
		return redirect(url_for('uploaded_file', filename=filename))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
	return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

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

if __name__ == '__main__':
	init_db()
	app.run(debug=True)
