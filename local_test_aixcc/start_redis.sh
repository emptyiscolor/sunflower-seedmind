#!/bin/bash

# Define image and container names
IMAGE="redis"
REDIS_CONTAINER_NAME="local-redis"
SENTINEL_CONTAINER_NAME="local-redis-sentinel"
SENTINEL_CONF="sentinel.conf"

# Create a minimal sentinel config if it doesn't exist
if [ ! -f $SENTINEL_CONF ]; then
    cat <<EOF > $SENTINEL_CONF
port 26379
sentinel monitor mymaster 127.0.0.1 6379 2
sentinel down-after-milliseconds mymaster 999999
sentinel parallel-syncs mymaster 1
sentinel failover-timeout mymaster 10000
EOF
    echo "Created minimal $SENTINEL_CONF"
fi

# Check if the Redis Docker image exists locally; if not, pull it
if [[ -z "$(docker images -q $IMAGE 2>/dev/null)" ]]; then
    echo "Redis image '$IMAGE' not found locally. Pulling image..."
    docker pull $IMAGE
else
    echo "Redis image '$IMAGE' already exists locally."
fi

# Remove existing containers if they exist
if [ "$(docker ps -aq -f name=^/${REDIS_CONTAINER_NAME}$)" ]; then
    echo "Container '$REDIS_CONTAINER_NAME' exists. Removing container..."
    docker rm -f $REDIS_CONTAINER_NAME
fi
if [ "$(docker ps -aq -f name=^/${SENTINEL_CONTAINER_NAME}$)" ]; then
    echo "Container '$SENTINEL_CONTAINER_NAME' exists. Removing container..."
    docker rm -f $SENTINEL_CONTAINER_NAME
fi

# Start Redis server
echo "Creating and starting Redis server container..."
docker run --name $REDIS_CONTAINER_NAME \
    -p 6379:6379 \
    -d $IMAGE

# Start Redis Sentinel
echo "Creating and starting Redis Sentinel container..."
docker run --name $SENTINEL_CONTAINER_NAME \
    --link $REDIS_CONTAINER_NAME:redis \
    -v "$(pwd)/$SENTINEL_CONF:/data/$SENTINEL_CONF" \
    -p 26379:26379 \
    -d $IMAGE \
    redis-sentinel /data/$SENTINEL_CONF

echo "Redis server and Sentinel are up and running."