import redis

redis_client = None

def init_redis(redis_url: str):
    global redis_client
    redis_client = redis.from_url(redis_url)
    try:
        if redis_client.ping():
            print("Redis client initialized")
    except redis.exceptions.ConnectionError as e:
        print(f"Redis connection failed: {e}")

def get_redis_client():
    return redis_client
