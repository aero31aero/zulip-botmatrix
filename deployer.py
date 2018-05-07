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

def extract_file(bot_root):
    file_name = bot_root + ".zip"
    bot_zip = zipfile.ZipFile('bots/' + file_name)
    bot_name = file_name.split('.zip')[0]
    bot_root = 'bots/' + bot_name
    bot_zip.extractall(bot_root)
    bot_zip.close()

def check_and_load_structure(bot_root):
    bot_root = "bots/" + bot_root
    config = get_config(bot_root)
    bot_file = bot_root + '/' + config['bot']
    if not Path(bot_file).is_file:
        print("Bot main file not found")
        return False
    zuliprc_file = bot_root + '/' + config['zuliprc']
    if not Path(zuliprc_file).is_file:
        print("Zuliprc file not found")
        return False
    provision = False
    if Path(bot_root + '/requirements.txt').is_file:
        "Found a requirements file"
        provision = True
    return True

def create_docker_image(bot_root):
    bot_name = bot_root
    bot_root = "bots/" + bot_root
    config = get_config(bot_root)
    dockerfile = textwrap.dedent('''\
        FROM python:3
        RUN pip install zulip zulip-bots zulip-botserver
        ADD ./* bot/
        RUN pip install -r bot/requirements.txt
        ''')
    dockerfile += 'CMD [ "zulip-run-bot", "bot/{bot}", "-c", "bot/{zuliprc}" ]\n'.format(bot=config['bot'], zuliprc=config['zuliprc'])
    with open(bot_root + '/Dockerfile', "w") as file:
        file.write(dockerfile)

    bot_image = docker_client.images.build(path=bot_root, tag=bot_name)

def start_bot(bot_name):
    containers = docker_client.containers.list()
    for container in containers:
        for tag in container.image.tags:
            if tag.startswith(bot_name.replace('@', '')):
                # Bot already running
                return False
    container = docker_client.containers.run(bot_name.replace('@', ''), detach=True)
    return True

def stop_bot(bot_name):
    containers = docker_client.containers.list()
    for container in containers:
        for tag in container.image.tags:
            if tag.startswith(bot_name.replace('@', '')):
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
    containers = docker_client.containers.list(all=True)
    for container in containers:
        for tag in container.image.tags:
            if tag.startswith(bot_name.replace('@', '')):
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
    with open('bots/' + bot_name + '/logs.txt', 'a') as logfile:
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
    bot_root = 'bots/' + bot_name
    if Path(bot_root).is_dir:
        shutil.rmtree(bot_root)
        print("Bot dir was removed.")
    else:
        print("Bot dir not found.")
    
    bot_zip_file = 'bots/' + bot_name + '.zip'
    if Path(bot_zip_file).is_file:
        os.remove(bot_zip_file)
        print("Bot zip file was removed.")
    else:
        print("Bot zip file not found.")

def bot_log(bot_name, **kwargs):
    lines = kwargs.get('lines', None)
    if lines is not None:
        lines = int(lines)
    containers = docker_client.containers.list(all=True)
    for container in containers:
        for tag in container.image.tags:
            if tag.startswith(bot_name.replace('@', '')):
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
    bot_name_prefix = username + '-'
    bot_status_by_name = _get_bot_statuses(bot_name_prefix)
    for bot_name, bot_status in bot_status_by_name.items():
        bot_root = 'bots/' + bot_name
        config = get_config(bot_root)
        zuliprc_file = bot_root + '/' + config['zuliprc']
        zuliprc = read_config_item(zuliprc_file, 'api')
        bot_info = dict(
            name=bot_name[len(bot_name_prefix):], # remove 'username-' prefix
            status=bot_status,
            email=zuliprc['email'],
            site=zuliprc['site'],
        )
        bots.append(bot_info)
    return bots

def _get_bot_statuses(bot_name_prefix):
    bot_status_by_name = dict()
    containers = docker_client.containers.list(all=True)
    for container in containers:
        for tag in container.image.tags:
            if tag.startswith(bot_name_prefix):
                bot_name = tag[:tag.find(':')]
                bot_status = container.status
                if bot_name in bot_status_by_name:
                    if bot_status > bot_status_by_name[bot_name]:
                        bot_status_by_name[bot_name] = bot_status
                else:
                    bot_status_by_name[bot_name] = bot_status
    return bot_status_by_name