from unittest import TestCase
from unittest.mock import patch
from tests.test_lib import test_docker_client, FakeDockerClient

from docker.errors import ImageNotFound

import deployer

class DeployerTest(TestCase):

    def test_start_bot_success(self):
        docker_client = test_docker_client(
            containers=[
                dict(id='c1', image_id='i1', status='created')
            ],
            images=[
                dict(id='i1', tags=['zulip-user1-bot_1:latest'])
            ]
        )
        with patch('deployer.docker_client', new=docker_client):
            result = deployer.start_bot('user1-bot_1')
            self.assertTrue(result)

    def test_start_bot_already_running(self):
        docker_client = test_docker_client(
            containers=[
                dict(id='c1', image_id='i1', status='running')
            ],
            images=[
                dict(id='i1', tags=['zulip-user1-bot_1:latest'])
            ]
        )
        with patch('deployer.docker_client', new=docker_client):
            result = deployer.start_bot('user1-bot_1')
            self.assertFalse(result)

    def test_start_bot_image_not_found(self):
        docker_client = test_docker_client(containers=[], images=[])
        with patch('deployer.docker_client', new=docker_client):
            self.assertRaises(ImageNotFound, deployer.start_bot, 'user1-bot_1')
