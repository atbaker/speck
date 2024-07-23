

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

def initialize_cache(cache_manager_dict, cache_manager_lock):
    global cache
    cache = SharedCache(cache_manager_dict, cache_manager_lock)

    return cache
