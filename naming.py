from werkzeug.utils import secure_filename

def normalize_username(username: str) -> str:
    return secure_filename(username)

def normalize_filename(filename: str) -> str:
    return secure_filename(filename).lower()

def normalize_bot_name(bot_name: str) -> str:
    return secure_filename(bot_name).lower()

def get_bot_filename(username: str, filename: str) -> str:
    return '{}-{}'.format(normalize_username(username), normalize_filename(filename))
