from werkzeug.utils import secure_filename

def normalize_username(username: str) -> str:
    return secure_filename(username)

def normalize_filename(filename: str) -> str:
    return secure_filename(filename).lower()

def normalize_bot_name(bot_name: str) -> str:
    return secure_filename(bot_name).lower()

def get_bot_filename(username: str, filename: str) -> str:
    return '{}-{}'.format(normalize_username(username), normalize_filename(filename))

def get_bot_name(username: str, name: str) -> str:
    return '{}-{}'.format(normalize_username(username), normalize_bot_name(name))

def get_bot_image_name(bot_name: str) -> str:
    # for backward compability bot_image_name equals to bot_name (temporary)
    return bot_name
