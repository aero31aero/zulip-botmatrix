# See readme.md for instructions on running this code.

from typing import Any
from urllib.parse import urlparse
import requests
import zipfile
import textwrap
import configparser
import os
import shutil
from pathlib import Path
import docker
from datetime import datetime
from naming import get_bot_image_name, get_bot_name, \
    extract_bot_name_from_image
import dev_config as config

BOTS_DIR = config.UPLOAD_FOLDER

CONTAINER_STATUS_LOW_PRIORITY = 0
CONTAINER_STATUS_MEDIUM_PRIORITY = 1
CONTAINER_STATUS_HIGH_PRIORITY = 2

CONTAINER_STATUS_PRIORITY = {
    'dead': CONTAINER_STATUS_LOW_PRIORITY,
    'exited': CONTAINER_STATUS_LOW_PRIORITY,
    'removing': CONTAINER_STATUS_MEDIUM_PRIORITY,
    'paused': CONTAINER_STATUS_MEDIUM_PRIORITY,
    'created': CONTAINER_STATUS_MEDIUM_PRIORITY,
    'restarting': CONTAINER_STATUS_MEDIUM_PRIORITY,
    'running': CONTAINER_STATUS_HIGH_PRIORITY,
}

provision = False
docker_client = docker.from_env()

def read_config_item(config_file, config_item):
    if not Path(config_file).is_file:
        print("No config file found")
        return False
    config = configparser.ConfigParser()
    with open(config_file) as conf:
        try:
            config.readfp(conf)
        except configparser.Error as e:
            print("Error in config file")
            display_config_file_errors(str(e), config_file)
            return False
    config = dict(config.items(config_item))
    return config

def get_config(bot_root):
    config_file = bot_root + '/config.ini'
    return read_config_item(config_file, 'deploy')

def get_bots_dir():
    return BOTS_DIR

def get_bot_root(bot_name):
    return os.path.join(BOTS_DIR, bot_name)

def find_bot_file(bot_name):
	for filename in os.listdir(BOTS_DIR):
		filepath = os.path.join(BOTS_DIR, filename)
		if os.path.isfile(filepath):
			name, ext = os.path.splitext(filename)
			if name == bot_name and ext in config.ALLOWED_EXTENSIONS:
				return filepath
	return None

def is_new_bot_message(message):
    msg = message['content']
    name = msg[msg.find("[")+1:msg.rfind("]")]
    url = msg[msg.find("(")+1:msg.rfind(")")]
    sender = message['sender_email']
    if name.endswith('.zip') and url.startswith('/user_uploads/'):
        file_name = sender + '-' + name
        url = url
        return True
    return False

def set_details_up(data):
    name = data['name']
    sender = data['sender']
    message = data['message']
    url = data['url']

def download_file(base_url):
    parsed_uri = urlparse(base_url)
    file_url = '{uri.scheme}://{uri.netloc}'.format(uri=parsed_uri)
    file_url = file_url + url
    r = requests.get(file_url, allow_redirects=True)
    open('bots/' + file_name, 'wb').write(r.content)

def extract_file(bot_name):
    bot_zip_path = find_bot_file(bot_name)
    if bot_zip_path is None:
        return False
    bot_zip = zipfile.ZipFile(bot_zip_path)
    bot_root = get_bot_root(bot_name)
    bot_zip.extractall(bot_root)
    bot_zip.close()
    return True

def check_and_load_structure(bot_name):
    bot_root = get_bot_root(bot_name)
    config = get_config(bot_root)
    bot_main_file = os.path.join(bot_root, config['bot'])
    if not Path(bot_main_file).is_file:
        print("Bot main file not found")
        return False
    zuliprc_file = os.path.join(bot_root, config['zuliprc'])
    if not Path(zuliprc_file).is_file:
        print("Zuliprc file not found")
        return False
    if Path(os.path.join(bot_root, 'requirements.txt')).is_file:
        print("Found a requirements file")
    return True

def create_docker_image(bot_name):
    bot_root = get_bot_root(bot_name)
    config = get_config(bot_root)
    dockerfile = textwrap.dedent('''\
        FROM python:3
        RUN pip install zulip zulip-bots zulip-botserver
        ADD ./* bot/
        RUN pip install -r bot/requirements.txt
        ''')
    dockerfile += 'CMD [ "zulip-run-bot", "bot/{bot}", "-c", "bot/{zuliprc}" ]\n'.format(bot=config['bot'], zuliprc=config['zuliprc'])
    with open(os.path.join(bot_root, 'Dockerfile'), "w") as file:
        file.write(dockerfile)
    _delete_bot_images(bot_name)
    bot_image_name = get_bot_image_name(bot_name)
    bot_image = docker_client.images.build(path=bot_root, tag=bot_image_name)

def start_bot(bot_name):
    bot_image_name = get_bot_image_name(bot_name)
    containers = docker_client.containers.list()
    for container in containers:
        for tag in container.image.tags:
            if tag.startswith(bot_image_name):
                # Bot already running
                return False
    container = docker_client.containers.run(bot_image_name, detach=True)
    return True

def stop_bot(bot_name):
    bot_image_name = get_bot_image_name(bot_name)
    containers = docker_client.containers.list()
    for container in containers:
        for tag in container.image.tags:
            if tag.startswith(bot_image_name):
                _stop_bot_container(bot_name, container)
                return True
    return False

def delete_bot(bot_name):
    _delete_bot_images(bot_name)
    _delete_bot_files(bot_name)
    return True

def _delete_bot_images(bot_name):
    bot_containers = []
    bot_image_ids = set()
    bot_image_name = get_bot_image_name(bot_name)
    containers = docker_client.containers.list(all=True)
    for container in containers:
        for tag in container.image.tags:
            if tag.startswith(bot_image_name):
                if container.status == 'running':
                    _stop_bot_container(bot_name, container)
                    # retrieve object for same container with updated status
                    container = docker_client.containers.get(container.id)
                bot_containers.append(container)
                bot_image_ids.add(container.image.id)

    for bot_container in bot_containers:
        _delete_bot_container(bot_container)
    
    for bot_image_id in bot_image_ids:
        _delete_bot_image(bot_image_id)


def _stop_bot_container(bot_name, container):
    logs = container.logs().decode("utf-8")
    bot_logs_path = os.path.join(get_bot_root(bot_name), 'logs.txt')
    with open(bot_logs_path, 'a') as logfile:
        logfile.write("Container id: " + container.short_id + "\n")
        logfile.write("Stop Time: " + str(datetime.now()) + "\n")
        logfile.write(logs + "\n")
        logfile.write("--------------------\n")
    container.stop()

def _delete_bot_container(container):
    container.remove(v=True, force=True)
    print("Bot container was removed.")

def _delete_bot_image(image_id):
    docker_client.images.remove(image=image_id, force=True)
    print("Bot image was removed.")

def _delete_bot_files(bot_name):
    bot_root = get_bot_root(bot_name)
    if Path(bot_root).is_dir():
        shutil.rmtree(bot_root)
        print("Bot dir was removed.")
    else:
        print("Bot dir not found.")
    
    bot_zip_file = find_bot_file(bot_name)
    if bot_zip_file is not None:
        os.remove(bot_zip_file)
        print("Bot zip file was removed.")
    else:
        print("Bot zip file not found.")

def bot_log(bot_name, **kwargs):
    lines = kwargs.get('lines', None)
    if lines is not None:
        lines = int(lines)
    bot_image_name = get_bot_image_name(bot_name)
    containers = docker_client.containers.list(all=True)
    for container in containers:
        for tag in container.image.tags:
            if tag.startswith(bot_image_name):
                logs = container.logs().decode("utf-8")
                if lines is None:
                    return logs
                else:
                    logs = logs.split('\n')
                    lines = max(0, len(logs)-lines)
                    logs = '\n'.join(logs[lines:])
                    return logs
    return 'No logs found.'

def get_user_bots(username):
    bots = []
    bot_name_prefix = get_bot_name(username, '')
    bot_status_by_name = _get_bot_statuses(bot_name_prefix)
    for bot_name, bot_status in bot_status_by_name.items():
        zuliprc = _read_bot_zuliprc(bot_name)
        bot_info = dict(
            name=bot_name[len(bot_name_prefix):], # remove 'username-' prefix
            status=bot_status,
            email=zuliprc['email'],
            site=zuliprc['site'],
        )
        bots.append(bot_info)
    return bots

def _read_bot_zuliprc(bot_name):
    bot_root = get_bot_root(bot_name)
    config = get_config(bot_root)
    zuliprc_file = os.path.join(bot_root, config['zuliprc'])
    return read_config_item(zuliprc_file, 'api')

def _get_bot_statuses(bot_name_prefix):
    bot_status_by_name = dict()
    bot_image_name_prefix = get_bot_image_name(bot_name_prefix)
    containers = docker_client.containers.list(all=True)
    for container in containers:
        for tag in container.image.tags:
            if tag.startswith(bot_image_name_prefix):
                bot_image_name = tag[:tag.find(':')]
                bot_name = extract_bot_name_from_image(bot_image_name)
                bot_status = container.status
                if bot_name in bot_status_by_name:
                    if bot_status > bot_status_by_name[bot_name]:
                        bot_status_by_name[bot_name] = bot_status
                else:
                    bot_status_by_name[bot_name] = bot_status
    return bot_status_by_name