"""Explicit fake used only by tests; production never falls back to memory."""
from app.services.object_storage import unavailable


class FakeStorage:
    seconds = 900

    def __init__(self, fail_at=None):
        self.objects = {}
        self.uploads = 0
        self.fail_at = fail_at
        self.deleted = []

    def upload(self, key, raw, content_type):
        self.uploads += 1
        self.objects[key] = raw
        if self.uploads == self.fail_at:
            raise unavailable()

    def read(self, key):
        return self.objects[key]

    def signed_url(self, key, content_type, download=False):
        assert key in self.objects
        return 'https://storage.example.test/' + key + '?expires=900'

    def delete(self, key):
        self.deleted.append(key)
        self.objects.pop(key, None)
