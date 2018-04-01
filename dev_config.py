import os
ALLOWED_EXTENSIONS = set(['zip', 'zbot'])
UPLOAD_FOLDER = 'bots'

DATABASE_URI = 'sqlite:////tmp/github-flask.db'
SECRET_KEY = 'development key'
DEBUG = True

GITHUB_CLIENT_ID = os.environ.get('github_client_id')
GITHUB_CLIENT_SECRET = os.environ.get('github_client_secret')
