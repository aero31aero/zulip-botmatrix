from typing import List, Dict, Any

from docker.errors import ImageNotFound

class DockerError(Exception):
    def __init__(self, msg):
        super(DockerError, self).__init__(msg)

class DockerImage:
    def __init__(self, id: str, tags: List[str]):
        self.id = id
        self.tags = tags

class DockerImages:
    def __init__(self, images: List[DockerImage]):
        self.images = images

    def remove(self, image, force):
        self.images = [docker_image for docker_image in self.images if docker_image.id != image]

    def contains(self, image_id):
        return image_id in [image.id for image in self.images]

class DockerContainer:
    def __init__(self, id: str, image: DockerImage, status: str, logs=''):
        self.id = id
        self.short_id = id
        self.image = image
        self.status = status
        self._logs = logs

    def setOwner(self, owner):
        self._owner = owner

    def is_running(self):
        return self.status == 'running'

    def logs(self):
        return bytearray(self._logs, 'utf-8')

    def stop(self):
        self.status = 'exited'

    def remove(self, v, force):
        self._owner._onContainerRemoved(self.id)

class DockerContainers:
    def __init__(self, containers: List[DockerContainer]):
        self.containers = containers
        for container in containers:
            container.setOwner(self)

    def list(self, all=False):
        return [container for container in self.containers if all or container.is_running()]

    def get(self, container_id):
        return next(container for container in self.containers if container.id == container_id)

    def contains(self, container_id):
        return container_id in [container.id for container in self.containers]

    def run(self, image, **kwargs):
        for container in self.containers:
            for tag in container.image.tags:
                if tag.startswith(image):
                    if container.status == 'running':
                        raise DockerError('Container is already running')
                    container.status = 'running'
                    return container
        raise ImageNotFound('Image \'{}\' not found'.format(image))

    def _onContainerRemoved(self, container_id):
        self.containers = [container for container in self.containers if container.id != container_id]

class TestDockerEnvironment:
    def __init__(self,
                 containers: List[Dict[str, Any]],
                 images: List[Dict[str, Any]]):
        self.containers = containers
        self.images = images
        self.client = None

    def get_client(self):
        if self.client is None:
            self.client = self._create_client()
        return self.client

    def _create_client(self):
        images_by_id = {image['id']: self._create_image(image) for image in self.images}
        containers = [self._create_container(container, images_by_id)
                      for container in self.containers]
        return FakeDockerClient(
            containers=DockerContainers(containers),
            images=DockerImages(images_by_id.values())
        )

    def _create_image(self, image: Dict[str, Any]):
        return DockerImage(id=image['id'], tags=image['tags'])

    def _create_container(self, container: Dict[str, Any], images: Dict[str, DockerImage]):
        return DockerContainer(
            id=container['id'], 
            image=images[container['image_id']], 
            status=container['status'],
            logs=container.get('logs', '')
        )

class FakeDockerClient(object):
    def __init__(self, containers: DockerContainers, images: DockerImages):
        self.containers = containers
        self.images = images


def test_docker_client(containers: List[Dict[str, Any]], images: List[Dict[str, Any]]):
    env = TestDockerEnvironment(containers=containers, images=images)
    return env.get_client()
