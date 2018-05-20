from unittest import TestCase
from unittest.mock import patch, MagicMock, Mock, ANY
from tests.test_lib import test_docker_client, FakeDockerClient

from docker.errors import ImageNotFound

from naming import get_bot_name, get_bot_image_name
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

    @patch('builtins.open', return_value=MagicMock())
    def test_stop_bot_success(self, open_mock: ANY):
        bot_name = 'user1-bot_1'
        docker_client = test_docker_client(
            containers=[
                dict(id='c1', image_id='i1', status='running')
            ],
            images=[
                dict(id='i1', tags=['zulip-{}:latest'.format(bot_name)])
            ]
        )
        with patch('deployer.docker_client', new=docker_client):
            result = deployer.stop_bot(bot_name)
            self.assertTrue(result)
        stopped_container = docker_client.containers.get('c1')
        self.assertEquals(stopped_container.status, 'exited')
    
    def test_stop_bot_not_found(self):
        docker_client = test_docker_client(containers=[], images=[])
        with patch('deployer.docker_client', new=docker_client):
            result = deployer.stop_bot('non-existing-bot')
            self.assertFalse(result)

    @patch('builtins.open', return_value=MagicMock())
    def test_delete_bot_success(self, open_mock: ANY):
        bot_name = 'user1-bot_1'
        docker_client = test_docker_client(
            containers=[
                dict(id='c1', image_id='i1', status='running'),
                dict(id='c2', image_id='i1', status='exited'),
                dict(id='c3', image_id='i2', status='paused'),
                dict(id='c4', image_id='i3', status='running')
            ],
            images=[
                dict(id='i1', tags=['zulip-{}'.format(bot_name)]),
                dict(id='i2', tags=['zulip-{}:latest'.format(bot_name)]),
                dict(id='i3', tags=['zulip-user1-another_bot:latest'.format(bot_name)])
            ]
        )

        with patch('deployer.docker_client', new=docker_client):
            deployer.delete_bot(bot_name)

        self.assertFalse(docker_client.containers.contains('c1'))
        self.assertFalse(docker_client.containers.contains('c2'))
        self.assertFalse(docker_client.containers.contains('c3'))
        self.assertFalse(docker_client.images.contains('i1'))
        self.assertFalse(docker_client.images.contains('i2'))

        self.assertTrue(docker_client.containers.contains('c4'))
        self.assertTrue(docker_client.images.contains('i3'))

    def test_bot_log_all_success(self):
        bot_name = 'user1-bot_1'
        bot_logs = 'some\nbot\nlogs\nin\nseveral\nlines'
        docker_client = test_docker_client(
            containers=[
                dict(id='c1', image_id='i1', status='running', logs=bot_logs)
            ],
            images=[
                dict(id='i1', tags=['zulip-{}:latest'.format(bot_name)])
            ]
        )
        with patch('deployer.docker_client', new=docker_client):
            actual_logs = deployer.bot_log(bot_name)
            self.assertEqual(actual_logs, bot_logs)

    def test_bot_logs_last_lines_success(self):
        bot_name = 'user1-bot_1'
        bot_logs_lines = ['line1', 'line2', 'line3']
        docker_client = test_docker_client(
            containers=[
                dict(id='c1', image_id='i1', status='running', logs='\n'.join(bot_logs_lines))
            ],
            images=[
                dict(id='i1', tags=['zulip-{}:latest'.format(bot_name)])
            ]
        )
        with patch('deployer.docker_client', new=docker_client):
            lines_count = len(bot_logs_lines) // 2
            actual_logs = deployer.bot_log(bot_name, lines=lines_count)
            expected_logs = '\n'.join(bot_logs_lines[-lines_count:])
            self.assertEqual(actual_logs, expected_logs)

    def test_bot_logs_all_lines_success(self):
        bot_name = 'user1-bot_1'
        bot_logs_lines = ['line1', 'line2', 'line3']
        docker_client = test_docker_client(
            containers=[
                dict(id='c1', image_id='i1', status='running', logs='\n'.join(bot_logs_lines))
            ],
            images=[
                dict(id='i1', tags=['zulip-{}:latest'.format(bot_name)])
            ]
        )
        with patch('deployer.docker_client', new=docker_client):
            lines_count = len(bot_logs_lines) + 10 # read more logs than there are
            actual_logs = deployer.bot_log(bot_name, lines=lines_count)
            expected_logs = '\n'.join(bot_logs_lines)
            self.assertEqual(actual_logs, expected_logs)

    def test_bot_log_not_found(self):
        docker_client = test_docker_client(containers=[],images=[])
        with patch('deployer.docker_client', new=docker_client):
            logs = deployer.bot_log('non-existing-bot')
            self.assertEqual(logs, 'No logs found.')

    def test_get_user_bots_success(self):
        user_name = 'user1'
        bot1_name, bot1_status = get_bot_name(user_name, 'bot1'), 'running'
        bot2_name, bot2_status = get_bot_name(user_name, 'bot2'), 'paused'
        bot3_name, bot3_status = get_bot_name(user_name, 'bot3'), 'exited'
        bot_zuliprc_configs = {
            bot1_name: dict(email='{}@domain'.format(bot1_name), site='http://{}.com'.format(bot1_name)),
            bot2_name: dict(email='{}@domain'.format(bot2_name), site='http://{}.com'.format(bot2_name)),
            bot3_name: dict(email='{}@domain'.format(bot3_name), site='http://{}.com'.format(bot3_name)),
        }
        bot_name_prefix = get_bot_name(user_name, '')
        expected_bot_configs = [
            {'name': bot1_name[len(bot_name_prefix):], 'status': bot1_status, **bot_zuliprc_configs[bot1_name]},
            {'name': bot2_name[len(bot_name_prefix):], 'status': bot2_status, **bot_zuliprc_configs[bot2_name]},
            {'name': bot3_name[len(bot_name_prefix):], 'status': bot3_status, **bot_zuliprc_configs[bot3_name]},
        ]

        docker_client = test_docker_client(
            containers=[
                dict(id='c1', image_id='i1', status=bot1_status),
                dict(id='c2', image_id='i2', status=bot2_status),
                dict(id='c3', image_id='i3', status=bot3_status),

                dict(id='c4', image_id='i4', status='running'),
            ],
            images=[
                dict(id='i1', tags=['{}:latest'.format(get_bot_image_name(bot1_name))]),
                dict(id='i2', tags=['{}:latest'.format(get_bot_image_name(bot2_name))]),
                dict(id='i3', tags=['{}:latest'.format(get_bot_image_name(bot3_name))]),

                dict(id='i4', tags=['zulip-user2-bot4:latest'])
            ]
        )
        with patch('deployer.docker_client', new=docker_client):
            read_bot_zuliprc_mock = lambda bot_name: bot_zuliprc_configs[bot_name]
            with patch('deployer._read_bot_zuliprc', new=read_bot_zuliprc_mock):
                actual_bot_configs = deployer.get_user_bots(user_name)
            bot_config_key = lambda bot_config: bot_config['name']
            self.assertListEqual(sorted(actual_bot_configs, key=bot_config_key), sorted(expected_bot_configs, key=bot_config_key))
