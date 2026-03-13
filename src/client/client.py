from common.types import ClientRequest
from sim.process import Process

# stub, waiting for implementation
class Client(Process):

    def __init__(self, node_id, server_id):
        super().__init__(node_id)
        self.server_id = server_id
        self.replies = []

    def get(self, shard_id, epoch, key):
        req = ClientRequest(
            shard_id=shard_id,
            epoch=epoch,
            key=key,
            value=None,
            op="GET",
        )
        self.send(self.server_id, req)

    def put(self, shard_id, epoch, key, value):
        req = ClientRequest(
            shard_id=shard_id,
            epoch=epoch,
            key=key,
            value=value,
            op="PUT",
        )
        self.send(self.server_id, req)

    def on_message(self, src, message):
        self.replies.append((src, message))