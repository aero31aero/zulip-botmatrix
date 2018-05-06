from werkzeug.utils import secure_filename

def normalize_username(username: str) -> str:
    return secure_filename(username)
