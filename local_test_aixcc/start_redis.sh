#!/bin/bash

# Define the image and container name
IMAGE="redis"
CONTAINER_NAME="local-redis"

# Check if the Redis Docker image exists locally; if not, pull it
if [[ -z "$(docker images -q $IMAGE 2>/dev/null)" ]]; then
    echo "Redis image '$IMAGE' not found locally. Pulling image..."
    docker pull $IMAGE
else
    echo "Redis image '$IMAGE' already exists locally."
fi

# Check if the Redis container exists
# If the container exists, remove it
if [ "$(docker ps -aq -f name=^/${CONTAINER_NAME}$)" ]; then
    echo "Container '$CONTAINER_NAME' exists. Removing container..."
    docker rm -f $CONTAINER_NAME
fi

echo "Creating and starting container..."
docker run --name $CONTAINER_NAME -p 6379:6379 -d $IMAGE

echo "Redis is up and running."