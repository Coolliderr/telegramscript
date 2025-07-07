# data_store.py

_user_data = {}

def set_user_state(user_id, key, value):
    if user_id not in _user_data:
        _user_data[user_id] = {}
    _user_data[user_id][key] = value

def get_user_state(user_id, key):
    return _user_data.get(user_id, {}).get(key)

def clear_user_state(user_id):
    if user_id in _user_data:
        _user_data[user_id] = {}