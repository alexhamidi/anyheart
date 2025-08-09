# Simple in-memory database for development
import threading

# Thread-safe in-memory storage
_storage = {}
_lock = threading.Lock()


def get(key: str):
    """Get value from in-memory storage by key"""
    with _lock:
        data = _storage.get(key)
        return data


def set(key: str, data):
    """Store data in in-memory storage with key"""
    with _lock:
        _storage[key] = data
        return True


def clear():
    """Clear all data from storage (useful for testing)"""
    with _lock:
        _storage.clear()


def list_keys():
    """List all keys in storage (useful for debugging)"""
    with _lock:
        keys = list(_storage.keys())
        return keys
