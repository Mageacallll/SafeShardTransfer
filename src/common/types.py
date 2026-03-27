"""
Shared types and protocol messages.

This file defines the core data structures used across the system.
All components (coordinator, shard servers, client, simulator) import
from here to ensure consistent message formats.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict


# -----------------------------
# Basic Types
# -----------------------------

ShardId = str
NodeId = str
Epoch = int
AttemptId = int
Key = str
Value = Any


# -----------------------------
# Shard Protocol States
# -----------------------------

class ShardState(Enum):
    STABLE = "STABLE"
    FREEZE = "FREEZE"
    TRANSFER = "TRANSFER"
    ACTIVATE = "ACTIVATE"
    CLEANUP = "CLEANUP"


# -----------------------------
# Client Messages
# -----------------------------

@dataclass
class ClientRequest:
    shard_id: ShardId
    epoch: Epoch
    key: Key
    value: Value | None
    op: str  # "GET" or "PUT"
    request_id: str | None = None


@dataclass
class ClientReply:
    success: bool
    value: Value | None
    error: str | None = None


# -----------------------------
# Coordinator -> Server Messages
# -----------------------------

@dataclass
class FreezeShard:
    shard_id: ShardId
    epoch: Epoch
    attempt_id: AttemptId


@dataclass
class BeginTransfer:
    shard_id: ShardId
    epoch: Epoch
    target: NodeId
    attempt_id: AttemptId


@dataclass
class ActivateShard:
    shard_id: ShardId
    epoch: Epoch
    attempt_id: AttemptId


@dataclass
class CleanupShard:
    shard_id: ShardId
    epoch: Epoch
    attempt_id: AttemptId


@dataclass
class AbortReconfiguration:
    shard_id: ShardId
    epoch: Epoch
    attempt_id: AttemptId | None
    reason: str | None = None


# -----------------------------
# Server -> Coordinator Messages
# -----------------------------

@dataclass
class FreezeAck:
    shard_id: ShardId
    epoch: Epoch
    attempt_id: AttemptId


@dataclass
class TransferAck:
    shard_id: ShardId
    epoch: Epoch
    attempt_id: AttemptId


# -----------------------------
# Server -> Server Messages
# -----------------------------

@dataclass
class TransferShard:
    shard_id: ShardId
    epoch: Epoch
    attempt_id: AttemptId
    data: Dict[Key, Value]


# -----------------------------
# Internal / Harness Messages
# -----------------------------

@dataclass
class StartReconfiguration:
    shard_id: ShardId
    new_owner: NodeId


# -----------------------------
# Utility
# -----------------------------

def msg_name(msg) -> str:
    return msg.__class__.__name__