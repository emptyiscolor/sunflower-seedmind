#!/bin/bash

# Define the image and container name
IMAGE="rabbitmq:3-management"
CONTAINER_NAME="local-rabbit"

# Check if the RabbitMQ Docker image exists locally; if not, pull it
if [[ -z "$(docker images -q $IMAGE 2>/dev/null)" ]]; then
    echo "RabbitMQ image '$IMAGE' not found locally. Pulling image..."
    docker pull $IMAGE
else
    echo "RabbitMQ image '$IMAGE' already exists locally."
fi

# Check if the RabbitMQ container exists
# If the container exists, remove it
if [ "$(docker ps -aq -f name=^/${CONTAINER_NAME}$)" ]; then
    echo "Container '$CONTAINER_NAME' exists. Removing container..."
    docker rm -f $CONTAINER_NAME
fi

echo "Creating and starting container..."
docker run -d --name $CONTAINER_NAME --hostname my-rabbit -p 5672:5672 -p 15672:15672 $IMAGE

echo "RabbitMQ is up and running."