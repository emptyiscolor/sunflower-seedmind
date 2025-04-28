import redis
from redis.sentinel import Sentinel

redis_client = None
sentinel = None

def init_redis(sentinel_hosts, master_name, password=None, db=0):
    """
    Initialize Redis client using Sentinel
    
    Args:
        sentinel_hosts (list): List of (host, port) tuples for Sentinel nodes
        master_name (str): Name of the master to monitor
        password (str, optional): Redis password
        db (int, optional): Redis database number
    """
    global redis_client, sentinel
    
    # Initialize Sentinel
    sentinel = Sentinel(sentinel_hosts, socket_timeout=5.0, password=password)
    
    try:
        # Get master for the specified master name
        redis_client = sentinel.master_for(
            master_name,
            socket_timeout=5.0,
            password=password,
            db=db
        )
        
        if redis_client.ping():
            print(f"Redis client initialized via Sentinel for master '{master_name}'")
    except redis.exceptions.ConnectionError as e:
        print(f"Redis Sentinel connection failed: {e}")

def get_redis_client():
    return redis_client

def get_sentinel():
    """Get the Sentinel object for additional operations if needed"""
    return sentinel