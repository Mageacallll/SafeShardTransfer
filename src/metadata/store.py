from common.types import ShardState


class MetadataStore:
    def __init__(self):
        self.shards = {}

    def init_shard(self, shard_id: str, owner: str, epoch: int = 1):
        self.shards[shard_id] = {
            "owner": owner,
            "epoch": epoch,
            "state": ShardState.STABLE,
            "target": None,
        }

    def get(self, shard_id: str):
        if shard_id not in self.shards:
            raise KeyError(f"Unknown shard_id: {shard_id}")
        return self.shards[shard_id]

    def update(self, shard_id: str, **kwargs):
        if shard_id not in self.shards:
            raise KeyError(f"Unknown shard_id: {shard_id}")
        self.shards[shard_id].update(kwargs)