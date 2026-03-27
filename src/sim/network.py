"""
Simulated message-passing network.

Supports:
- deterministic or configurable delay
- probabilistic drops
- targeted drop rules
- node crash awareness
- per-link configurations (asymmetric links)
- message reordering
- message duplication
- network partitions
"""

import random
from typing import Any, Callable
from dataclasses import dataclass


@dataclass
class LinkConfig:
    """Per-link network configuration.
    
    Attributes:
        source: sending node ID
        dest: receiving node ID
        drop_rate: probability of dropping each message (0.0 to 1.0)
        delay_min_ms: minimum delay for messages (inclusive)
        delay_max_ms: maximum delay for messages (inclusive)
        reorder_enabled: whether to allow out-of-order delivery
        duplicate_rate: probability of duplicating each message (0.0 to 1.0)
        duplicate_delay_ms: delay for duplicate relative to original
        partition_enabled: whether this link is partitioned
        partition_start_time: when partition begins (ms)
        partition_end_time: when partition ends (ms)
    """
    source: str
    dest: str
    drop_rate: float = 0.0
    delay_min_ms: int = 1
    delay_max_ms: int = 1
    reorder_enabled: bool = False
    duplicate_rate: float = 0.0
    duplicate_delay_ms: int = 5
    partition_enabled: bool = False
    partition_start_time: int = -1
    partition_end_time: int = -1
    
    def __post_init__(self):
        if not (0.0 <= self.drop_rate <= 1.0):
            raise ValueError(f"drop_rate must be in [0.0, 1.0], got {self.drop_rate}")
        if not (0.0 <= self.duplicate_rate <= 1.0):
            raise ValueError(f"duplicate_rate must be in [0.0, 1.0], got {self.duplicate_rate}")
        if self.delay_min_ms < 0 or self.delay_max_ms < self.delay_min_ms:
            raise ValueError(f"Require 0 <= delay_min_ms <= delay_max_ms, got {self.delay_min_ms}, {self.delay_max_ms}")
        if self.duplicate_delay_ms < 0:
            raise ValueError(f"duplicate_delay_ms must be >= 0, got {self.duplicate_delay_ms}")


class Network:
    def __init__(
        self,
        loop,
        drop_prob: float = 0.0,
        min_delay: int = 1,
        max_delay: int = 1,
        seed: int = 0,
    ):
        if min_delay < 0 or max_delay < min_delay:
            raise ValueError("Require 0 <= min_delay <= max_delay")

        self.loop = loop
        self.nodes = {}
        self.drop_prob = drop_prob
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.random = random.Random(seed)

        # Each rule: fn(src, dst, msg) -> bool, where True means drop
        self.drop_rules: list[Callable[[str, str, Any], bool]] = []
        
        # Per-link configurations: {(src, dst): LinkConfig}
        self.link_configs: dict[tuple[str, str], LinkConfig] = {}
        
        # In-flight messages for reordering: {(src, dst): [(scheduled_time, message)]}
        self.in_flight: dict[tuple[str, str], list[tuple[int, Any]]] = {}

    def register(self, node):
        self.nodes[node.node_id] = node
        node.network = self

    def unregister(self, node_id: str):
        if node_id in self.nodes:
            self.nodes[node_id].network = None
            del self.nodes[node_id]

    def add_drop_rule(self, rule: Callable[[str, str, Any], bool]):
        self.drop_rules.append(rule)

    def clear_drop_rules(self):
        self.drop_rules.clear()
    
    def set_link_config(self, config: LinkConfig):
        """Set configuration for a specific link (directed: src -> dst)."""
        key = (config.source, config.dest)
        self.link_configs[key] = config
        # Initialize reordering buffer if needed
        if config.reorder_enabled and key not in self.in_flight:
            self.in_flight[key] = []
    
    def get_link_config(self, src: str, dst: str) -> LinkConfig | None:
        """Get configuration for a specific link, or None if using global defaults."""
        return self.link_configs.get((src, dst))
    
    def clear_link_configs(self):
        """Clear all per-link configurations."""
        self.link_configs.clear()
        self.in_flight.clear()

    def send(self, src: str, dst: str, message: Any):
        """Send a message from src to dst, applying link-specific faults and delays.
        
        Applies:
        1. Link-specific drop rate (or global if no link config)
        2. Partition check
        3. Link-specific delay bounds
        4. Optional reordering
        5. Optional duplication
        6. Delivery to destination
        """
        # sender missing or crashed
        if src not in self.nodes or not self.nodes[src].alive:
            return

        # destination missing: model as lost
        if dst not in self.nodes:
            return

        # targeted drop rules (legacy)
        for rule in self.drop_rules:
            if rule(src, dst, message):
                return
        
        # Get link-specific config or use global defaults
        link_config = self.get_link_config(src, dst)
        
        if link_config is not None:
            # Use per-link configuration
            drop_rate = link_config.drop_rate
            delay_min = link_config.delay_min_ms
            delay_max = link_config.delay_max_ms
            reorder_enabled = link_config.reorder_enabled
            duplicate_rate = link_config.duplicate_rate
            duplicate_delay = link_config.duplicate_delay_ms
            
            # Check partition
            if link_config.partition_enabled:
                if (link_config.partition_start_time <= self.loop.time < link_config.partition_end_time):
                    return  # Message dropped due to partition
        else:
            # Use global defaults
            drop_rate = self.drop_prob
            delay_min = self.min_delay
            delay_max = self.max_delay
            reorder_enabled = False
            duplicate_rate = 0.0
            duplicate_delay = 0
        
        # Apply per-link drop rate
        if self.random.random() < drop_rate:
            return
        
        # Calculate delay for this message
        delay = self.random.randint(delay_min, delay_max)
        
        # Schedule delivery
        delivery_time = self.loop.time + delay
        self._schedule_delivery(src, dst, message, delivery_time, reorder_enabled)
        
        # Optionally duplicate
        if duplicate_rate > 0 and self.random.random() < duplicate_rate:
            dup_delay = delay + duplicate_delay
            dup_delivery_time = self.loop.time + dup_delay
            self._schedule_delivery(src, dst, message, dup_delivery_time, reorder_enabled)
    
    def _schedule_delivery(self, src: str, dst: str, message: Any, delivery_time: int, reorder_enabled: bool):
        """Schedule message delivery at the specified time.
        
        If reordering is enabled, adds to in-flight buffer and may deliver out-of-order.
        Otherwise, delivers in FIFO order.
        """
        link_key = (src, dst)
        
        if reorder_enabled:
            # Add to reordering buffer
            if link_key not in self.in_flight:
                self.in_flight[link_key] = []
            self.in_flight[link_key].append((delivery_time, message))
            
            # Schedule reordering check at delivery time
            def check_reorder():
                self._deliver_with_reorder(src, dst)
            
            self.loop.schedule(delivery_time - self.loop.time, check_reorder)
        else:
            # Deliver immediately at scheduled time
            def deliver():
                if dst not in self.nodes:
                    return
                dst_node = self.nodes[dst]
                if not dst_node.alive:
                    return
                dst_node.on_message(src, message)
            
            self.loop.schedule(delivery_time - self.loop.time, deliver)
    
    def _deliver_with_reorder(self, src: str, dst: str):
        """Deliver messages on a reordering-enabled link.
        
        Randomly selects from in-flight messages that are ready for delivery,
        allowing out-of-order delivery.
        """
        link_key = (src, dst)
        if link_key not in self.in_flight:
            return
        
        in_flight = self.in_flight[link_key]
        if not in_flight:
            return
        
        # Find messages that are ready (scheduled time <= current time)
        ready = [(i, (t, msg)) for i, (t, msg) in enumerate(in_flight) if t <= self.loop.time]
        
        if not ready:
            return
        
        # Randomly pick one to deliver
        idx, (delivery_time, message) = self.random.choice(ready)
        
        # Remove from buffer
        in_flight.pop(idx)
        
        # Deliver
        if dst in self.nodes:
            dst_node = self.nodes[dst]
            if dst_node.alive:
                dst_node.on_message(src, message)