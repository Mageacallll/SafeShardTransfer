from metadata.coordinator import Coordinator
from shardserver.server import ShardServer
from sim.harness import Harness


def main():
    h = Harness(drop_prob=0.0, min_delay=1, max_delay=1, seed=0)

    coord = Coordinator("coord")
    server_a = ShardServer("A", coordinator_id="coord")
    server_b = ShardServer("B", coordinator_id="coord")

    h.add_node(coord)
    h.add_node(server_a)
    h.add_node(server_b)

    # Initial shard placement
    coord.init_shard("s1", owner="A", epoch=1)
    server_a.init_shard("s1", epoch=1, data={"x": 10, "y": 20})

    # Trigger reassignment at logical time 1
    h.schedule(1, coord.reassign, "s1", "B")

    h.run()

    print("\nFinal coordinator metadata:")
    print(coord.store.get("s1"))

    print("\nFinal server state:")
    print("A shards:", server_a.shards)
    print("B shards:", server_b.shards)


if __name__ == "__main__":
    main()