import docker
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_docker_image(docker_image: str):
    client = docker.from_env()
    try:
        image = client.images.get(docker_image)
        return image
    except docker.errors.APIError as e:
        logger.error(f"An error occurred while pulling the Docker image: {e}")
        raise
    except docker.errors.ImageNotFound:
        logger.error(f"Docker image '{docker_image}' not found.")
        raise


def get_entrypoint(image):
    entrypoint = image.attrs["Config"]["Entrypoint"]
    if not entrypoint:
        return ""
    elif isinstance(entrypoint, list):
        return " ".join(entrypoint)
    elif isinstance(entrypoint, str):
        return entrypoint
