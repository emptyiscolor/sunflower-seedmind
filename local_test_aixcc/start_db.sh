#!/bin/bash

# Define the image and container name
IMAGE="postgres"
CONTAINER_NAME="postgres-container"

# Check if the Postgres Docker image exists locally; if not, pull it
if [[ -z "$(docker images -q $IMAGE 2>/dev/null)" ]]; then
    echo "Postgres image '$IMAGE' not found locally. Pulling image..."
    docker pull $IMAGE
else
    echo "Postgres image '$IMAGE' already exists locally."
fi

# Check if the Postgres container exists
# If the container exists, remove it
if [ "$(docker ps -aq -f name=^/${CONTAINER_NAME}$)" ]; then
    echo "Container '$CONTAINER_NAME' exists. Removing container..."
    docker rm -f $CONTAINER_NAME
fi

echo "Creating and starting container..."
docker run --name $CONTAINER_NAME -e POSTGRES_USER=user -e POSTGRES_PASSWORD=password -e POSTGRES_DB=mydatabase -p 5432:5432 -d postgres
sleep 3
docker exec -i $CONTAINER_NAME psql -U user -d mydatabase < ./sample_db.txt

echo "Postgres is up and running."
