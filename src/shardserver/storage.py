class ShardStorage:
    def __init__(self, initial_data=None):
        self._data = dict(initial_data or {})

    def get(self, key):
        return self._data.get(key)

    def put(self, key, value):
        self._data[key] = value

    def snapshot(self):
        return dict(self._data)

    def load_snapshot(self, data):
        self._data = dict(data)

    def as_dict(self):
        return dict(self._data)