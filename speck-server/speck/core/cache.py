

class SharedCache:
    """Simple cache shared across all processes using a multiprocessing manager"""
    def __init__(self, cache_manager_dict, cache_manager_lock):
        self.cache = cache_manager_dict
        self.lock = cache_manager_lock

    def get(self, key):
        with self.lock:
            return self.cache.get(key)

    def set(self, key, value):
        with self.lock:
            self.cache[key] = value

    def delete(self, key):
        with self.lock:
            del self.cache[key]

cache = None

def initialize_cache(
        manager=None,
        cache_manager_dict=None,
        cache_manager_lock=None):
    # If cache_manager_dict and cache_manager_lock are not provided, use the manager to create them
    if cache_manager_dict is None or cache_manager_lock is None:
        cache_manager_dict = manager.dict()
        cache_manager_lock = manager.Lock()

    global cache
    cache = SharedCache(cache_manager_dict, cache_manager_lock)

    return cache
