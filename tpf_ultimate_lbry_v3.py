#!/usr/bin/env python3
"""
TPF ULTIMATE V3.0 - VESELOV-INTEGRATED ARCHITECTURE
====================================================
The Definitive Thermodynamic Probability Filter for LBRY Mining

Hardware: Goldshell LB-Box (Zynq-7010)
Pool: Mining-Dutch LBRY Solo
Algorithm: LBRY (SHA256+SHA512+RIPEMD160)

╔═══════════════════════════════════════════════════════════════════════════════╗
║  MATHEMATICAL INNOVATIONS (Based on Veselov Research Group Papers)           ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║  1. Hierarchical Representation with Exponential Growth                       ║
║     - Level k processes 64·2ᵏ bits                                          ║
║     - L = ⌈log₂(n/64 + 1)⌉ levels                                            ║
║                                                                               ║
║  2. Binomial Heaps for Component Management                                   ║
║     - O(log n) merge operations                                              ║
║     - Efficient parallel processing per level                                ║
║                                                                               ║
║  3. Powers-of-Two Representation                                              ║
║     - N = Σ 2^p(u) for all nodes u                                           ║
║     - Natural support for shift operations                                   ║
║                                                                               ║
║  4. DVFS-Inspired Adaptive Control                                            ║
║     - Dynamic "frequency/voltage" based on computational load                ║
║     - Energy-efficient filtering with αeff ≈ 0.2                             ║
╚═══════════════════════════════════════════════════════════════════════════════╝

Author: Francisco Angulo de Lafuente
Based on: Veselov Research Group Papers on Energy-Efficient AI Systems
Date: January 2026
"""

import socket
import threading
import json
import time
import csv
import signal
import sys
import statistics
import hashlib
import struct
import math
import heapq
import random
from collections import deque, defaultdict
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Tuple, Deque, Set
from datetime import datetime
from pathlib import Path
import logging

# ================= LOGGING =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('TPF-VESELOV')

# ================= CONFIGURATION =================
class Config:
    """Centralized configuration for TPF Ultimate LBRY"""
    
    # Network
    LOCAL_HOST = "0.0.0.0"
    LOCAL_PORT = 8888
    
    # Pool (Mining-Dutch LBRY Solo)
    REMOTE_HOST = "lbry.mining-dutch.nl"
    REMOTE_PORT = 9988
    
    # Account
    USER_WALLET = "apollo13.LBBox"
    POOL_PASS = "x"
    
    # Identity (Stealth)
    FAKE_AGENT = "LBC-Swarm/1.0"
    
    # Swarm Configuration
    SWARM_SIZE = 2
    
    # ═══════════════════════════════════════════════════════════════
    # VESELOV HIERARCHICAL ARCHITECTURE PARAMETERS
    # ═══════════════════════════════════════════════════════════════
    
    # Base word size for hierarchical levels (from paper: 64 bits)
    WORD_SIZE = 64
    
    # Number of hierarchical levels for timing analysis
    # L = ⌈log₂(n/64 + 1)⌉ where n = expected samples
    NUM_HIERARCHY_LEVELS = 6
    
    # Binomial heap order limit per level
    MAX_HEAP_ORDER = 10  # 2^10 = 1024 nodes max per heap
    
    # ═══════════════════════════════════════════════════════════════
    # MULTI-TIER RESONANCE FILTER (Veselov-Enhanced)
    # ═══════════════════════════════════════════════════════════════
    
    # TIER 1: Basic Timing Filter (z-score threshold)
    Z_SCORE_TIER1 = 0.8  # ~79% pass
    
    # TIER 2: Super-Resonance Detection
    Z_SCORE_TIER2 = -0.5  # Top ~31% are resonant
    
    # TIER 3: Hierarchical Jitter Analysis
    JITTER_CV_THRESHOLD = 0.95    # Adaptive based on hierarchy
    CALIBRATION_SAMPLES = 100
    
    # ═══════════════════════════════════════════════════════════════
    # DVFS-INSPIRED ADAPTIVE PARAMETERS
    # Based on: P_dyn = α · C · V² · f
    # ═══════════════════════════════════════════════════════════════
    
    # Effective activity coefficient (from paper: αeff ≈ 0.2)
    ALPHA_EFF = 0.2
    
    # Frequency scaling bounds (conceptual for filter intensity)
    MIN_FILTER_FREQ = 0.25   # Minimum filter activity (25%)
    MAX_FILTER_FREQ = 1.0    # Maximum filter activity (100%)
    
    # Temperature-like load thresholds
    T_MAX = 0.9              # High load threshold
    T_DELTA = 0.1            # Hysteresis band
    
    # ═══════════════════════════════════════════════════════════════
    # TIMING & PERSISTENCE
    # ═══════════════════════════════════════════════════════════════
    
    HEARTBEAT_SEC = 120           # Global pool keep-alive
    KEEP_ALIVE_SEC = 300          # Per-worker forced share
    
    # Veselov round check
    VESELOV_K = 5
    JITTER_WINDOW = 50
    JITTER_HISTORY = 5000
    
    # Worker Management
    AFFINITY_SHARES = 20
    
    # Safety
    SAFETY_KEEP_RATE = 0.03  # 3% random pass-through
    
    # Learning Engine Parameters
    MIN_WINNERS_FOR_LEARNING = 3
    PATTERN_SIGNIFICANCE = 0.01
    
    # x20 Window Configuration (Nonce space partitioning)
    NONCE_WINDOWS = 20
    PREDICTION_CONFIDENCE = 0.95
    
    # Logging
    VERBOSE = True
    LOG_FILTERED = False
    LOG_RESONANT = True
    LOG_HIERARCHY = True
    
    # State Persistence
    STATE_FILE = Path("./tpf_v3_veselov_state.json")
    AUTO_SAVE_INTERVAL = 3600
    
    # Experiment
    EXPERIMENT_NAME = f"tpf_v3_veselov_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    @classmethod
    def to_dict(cls):
        return {k: v for k, v in vars(cls).items() 
                if not k.startswith('_') and not callable(v)}


# ═══════════════════════════════════════════════════════════════════════════════
# VESELOV MATHEMATICAL STRUCTURES
# Based on: "Innovative Adder for Giant Numbers" & "Integrated Adder Architecture"
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class BinomialNode:
    """
    Node in a Binomial Heap
    
    Mathematical properties (from paper):
    - Contains 2^k nodes for order k
    - Tree height equals k
    - Root has degree k
    
    In our context: stores timing exponent p representing contribution 2^p
    """
    degree: int                          # Order k of this node
    value: float                         # The timing value (latency)
    exponent: int                        # Power-of-two exponent p
    parent: Optional['BinomialNode'] = None
    children: List['BinomialNode'] = field(default_factory=list)
    sibling: Optional['BinomialNode'] = None
    
    def __lt__(self, other):
        return self.value < other.value


class BinomialHeap:
    """
    Binomial Heap Implementation for Timing Management
    
    From Veselov paper:
    - Heap H of order k contains 2^k nodes
    - Merge operation: O(log n)
    - Used for efficient parallel processing of hierarchical levels
    
    Application in TPF:
    - Each heap level manages timing samples within its bit range
    - Merge operation combines samples from multiple sources
    - Powers-of-two representation enables efficient shift operations
    """
    
    def __init__(self, level: int = 0):
        self.roots: List[BinomialNode] = []
        self.level = level  # Hierarchical level k
        self.size = 0
        self.min_node: Optional[BinomialNode] = None
        
        # Level k processes bits in range [64·2^(k-1), 64·2^k)
        self.bit_range_start = Config.WORD_SIZE * (2 ** (level - 1)) if level > 0 else 0
        self.bit_range_end = Config.WORD_SIZE * (2 ** level)
    
    def _link(self, y: BinomialNode, z: BinomialNode) -> BinomialNode:
        """
        Link two binomial trees of same order
        Makes y a child of z
        """
        y.parent = z
        y.sibling = z.children[0] if z.children else None
        z.children.insert(0, y)
        z.degree += 1
        return z
    
    def _merge_roots(self, h1_roots: List[BinomialNode], 
                     h2_roots: List[BinomialNode]) -> List[BinomialNode]:
        """Merge root lists sorted by degree"""
        merged = []
        i, j = 0, 0
        
        while i < len(h1_roots) and j < len(h2_roots):
            if h1_roots[i].degree <= h2_roots[j].degree:
                merged.append(h1_roots[i])
                i += 1
            else:
                merged.append(h2_roots[j])
                j += 1
        
        merged.extend(h1_roots[i:])
        merged.extend(h2_roots[j:])
        return merged
    
    def merge(self, other: 'BinomialHeap') -> 'BinomialHeap':
        """
        Merge two binomial heaps - O(log n)
        
        From paper Algorithm 3: ParallelHeapMerge
        """
        if not other.roots:
            return self
        if not self.roots:
            self.roots = other.roots
            self.size = other.size
            self._update_min()
            return self
        
        # Merge root lists
        merged = self._merge_roots(self.roots, other.roots)
        self.size += other.size
        
        if not merged:
            self.roots = []
            self._update_min()
            return self
        
        # Union binomial trees
        new_roots = []
        idx = 0
        
        while idx < len(merged):
            curr = merged[idx]
            
            # Case 1: Next node has different degree
            if idx + 1 == len(merged) or merged[idx + 1].degree != curr.degree:
                new_roots.append(curr)
                idx += 1
            # Case 2: Three nodes with same degree (keep one, merge two)
            elif idx + 2 < len(merged) and merged[idx + 2].degree == curr.degree:
                new_roots.append(curr)
                # Next two are merged
                if merged[idx + 1].value <= merged[idx + 2].value:
                    linked = self._link(merged[idx + 2], merged[idx + 1])
                else:
                    linked = self._link(merged[idx + 1], merged[idx + 2])
                merged[idx + 2] = linked
                idx += 2
            # Case 3: Two nodes with same degree (merge them)
            else:
                next_node = merged[idx + 1]
                if curr.value <= next_node.value:
                    linked = self._link(next_node, curr)
                else:
                    linked = self._link(curr, next_node)
                merged[idx + 1] = linked
                idx += 1
        
        self.roots = new_roots
        self._update_min()
        return self
    
    def insert(self, value: float, exponent: int = 0):
        """Insert a value with its power-of-two exponent"""
        node = BinomialNode(degree=0, value=value, exponent=exponent)
        temp_heap = BinomialHeap(self.level)
        temp_heap.roots = [node]
        temp_heap.size = 1
        self.merge(temp_heap)
    
    def get_min(self) -> Optional[float]:
        """Get minimum value"""
        return self.min_node.value if self.min_node else None
    
    def extract_min(self) -> Optional[BinomialNode]:
        """Extract minimum node"""
        if not self.min_node:
            return None
        
        min_node = self.min_node
        self.roots.remove(min_node)
        
        # Reverse children and merge back
        if min_node.children:
            child_heap = BinomialHeap(self.level)
            child_heap.roots = list(reversed(min_node.children))
            for child in child_heap.roots:
                child.parent = None
            self.merge(child_heap)
        
        self.size -= 1
        self._update_min()
        return min_node
    
    def _update_min(self):
        """Update minimum node reference"""
        self.min_node = None
        for root in self.roots:
            if self.min_node is None or root.value < self.min_node.value:
                self.min_node = root
    
    def shift_left(self):
        """
        SHIFT_LEFT operation from paper: multiply all values by 2
        
        For timing exponents: increment all exponents
        SHIFT_LEFT(H) = {p + 1 | p ∈ H}
        """
        stack = list(self.roots)
        while stack:
            node = stack.pop()
            node.exponent += 1
            stack.extend(node.children)
    
    def shift_right(self):
        """
        SHIFT_RIGHT operation: divide all values by 2
        
        Decreases all exponents, removes those that become negative
        SHIFT_RIGHT(H) = {p - 1 | p ∈ H and p > 0}
        """
        def _shift_node_iter(root: BinomialNode) -> Optional[BinomialNode]:
            # Iterative removal is complex in binomial tree, using reconstruction approach
            pass

        # Simplification: rebuild for shift_right if needed, but TPF mostly uses left/merge
        pass
    
    def get_exponent_distribution(self) -> Dict[int, int]:
        """Cycle-proof iterative exponent collection"""
        distribution = defaultdict(int)
        visited = set()
        stack = list(self.roots)
        
        while stack:
            node = stack.pop()
            if id(node) in visited: continue
            visited.add(id(node))
            
            distribution[node.exponent] += 1
            for child in reversed(node.children):
                stack.append(child)
                
        return dict(distribution)
    
    def normalize(self) -> 'BinomialHeap':
        """
        NORMALIZE_HEAP from paper Algorithm 4
        
        Eliminates conflicts when duplicate exponents exist
        Two nodes with same exponent p → one node with exponent p+1
        
        This represents the carry propagation in arithmetic
        """
        # Collect all exponents
        exponent_map = defaultdict(list)
        
        stack = list(self.roots)
        while stack:
            node = stack.pop()
            exponent_map[node.exponent].append(node.value)
            stack.extend(node.children)
        
        # Normalize: combine duplicates
        # 2^p + 2^p = 2^(p+1)
        sorted_exponents = sorted(exponent_map.keys())
        normalized_values = {}
        
        for exp in sorted_exponents:
            values = exponent_map[exp]
            while len(values) >= 2:
                v1, v2 = values.pop(), values.pop()
                # Combine: average value, increment exponent
                combined = (v1 + v2) / 2
                if (exp + 1) not in exponent_map:
                    exponent_map[exp + 1] = []
                exponent_map[exp + 1].append(combined)
            if values:
                normalized_values[exp] = values[0]
        
        # Rebuild heap with normalized values
        new_heap = BinomialHeap(self.level)
        for exp in sorted(normalized_values.keys()):
            new_heap.insert(normalized_values[exp], exp)
        
        self.roots = new_heap.roots
        self.size = new_heap.size
        self._update_min()
        return self
    
    def get_stats(self) -> dict:
        return {
            'level': self.level,
            'size': self.size,
            'min': self.get_min(),
            'bit_range': (self.bit_range_start, self.bit_range_end),
            'exponent_distribution': self.get_exponent_distribution()
        }


class HierarchicalTimingStructure:
    """
    Hierarchical Representation with Exponential Growth
    
    From Veselov paper:
    - Number is divided into levels where level k processes 64·2^k bits
    - L = ⌈log₂(n/64 + 1)⌉ levels total
    
    Application in TPF:
    - Each level manages timing samples of increasing granularity
    - Lower levels: fine-grained microsecond variations
    - Higher levels: macro-patterns in minutes/hours
    
    Formula: S_k = 64 · 2^k (size of level k in bits)
    """
    
    def __init__(self, num_levels: int = Config.NUM_HIERARCHY_LEVELS):
        self.num_levels = num_levels
        self.levels: List[BinomialHeap] = [
            BinomialHeap(level=k) for k in range(num_levels)
        ]
        
        # Track level sizes: S_k = 64 · 2^k
        self.level_sizes = [Config.WORD_SIZE * (2 ** k) for k in range(num_levels)]
        
        # Statistics per level
        self.level_stats = [{
            'samples': 0,
            'mean': 0.0,
            'std': 1.0,
            'resonant_count': 0
        } for _ in range(num_levels)]
        
        self.total_samples = 0
        self.lock = threading.Lock()
    
    def _compute_level(self, value: float) -> int:
        """
        Determine which hierarchical level a value belongs to
        
        Based on magnitude (log scale), maps to level k where:
        64·2^(k-1) ≤ log₂(value) < 64·2^k
        """
        if value <= 0:
            return 0
        
        # Use log scale to determine level
        log_val = math.log2(max(1, value))
        
        for k in range(self.num_levels - 1, -1, -1):
            if log_val >= self.level_sizes[k] / 1000:  # Scale factor for ms
                return k
        return 0
    
    def _value_to_exponent(self, value: float) -> int:
        """
        Convert value to power-of-two exponent
        
        From paper: Number N = Σ 2^p(u)
        We represent timing as 2^p where p = ⌊log₂(value)⌋
        """
        if value <= 0:
            return 0
        return int(math.log2(max(1, value)))
    
    def insert(self, value: float):
        """
        Insert timing value into appropriate hierarchical level
        
        Algorithm 1 from paper: InitializeHierarchy
        """
        with self.lock:
            level = self._compute_level(value)
            exponent = self._value_to_exponent(value)
            
            self.levels[level].insert(value, exponent)
            self.level_stats[level]['samples'] += 1
            self.total_samples += 1
            
            # Update running statistics
            stats = self.level_stats[level]
            n = stats['samples']
            old_mean = stats['mean']
            stats['mean'] = old_mean + (value - old_mean) / n
            
            if n > 1:
                # Welford's online algorithm for variance
                stats['std'] = math.sqrt(
                    (stats['std'] ** 2 * (n - 2) + (value - old_mean) * (value - stats['mean'])) / (n - 1)
                )
    
    def parallel_merge(self, other: 'HierarchicalTimingStructure'):
        """
        Algorithm 3: ParallelHeapMerge
        
        Merge another hierarchical structure into this one
        Each level is merged independently (parallel in hardware)
        """
        with self.lock:
            for k in range(self.num_levels):
                self.levels[k].merge(other.levels[k])
                # Normalize to handle carries between powers
                self.levels[k].normalize()
            
            # Process inter-level carries
            self._process_carries()
    
    def _process_carries(self):
        """
        Handle overflow between hierarchical levels
        
        When level k overflows, carry to level k+1
        """
        for k in range(self.num_levels - 1):
            max_size = 2 ** Config.MAX_HEAP_ORDER
            while self.levels[k].size > max_size:
                # Extract excess and promote to next level
                node = self.levels[k].extract_min()
                if node:
                    # Shift exponent for next level
                    self.levels[k + 1].insert(node.value, node.exponent + 1)
    
    def get_resonance_score(self) -> float:
        """
        Compute overall resonance score from hierarchical structure
        
        Based on paper's energy formula:
        E = k · log(n) · V²_DVFS · f_DVFS · α_eff
        
        Higher resonance = lower "energy" = more coherent timing
        """
        if self.total_samples < Config.CALIBRATION_SAMPLES:
            return 0.5  # Neutral during calibration
        
        scores = []
        for k, heap in enumerate(self.levels):
            if heap.size > 0:
                # Check exponent distribution uniformity
                dist = heap.get_exponent_distribution()
                if dist:
                    values = list(dist.values())
                    # Coefficient of variation of distribution
                    mean = statistics.mean(values)
                    if mean > 0:
                        cv = statistics.stdev(values) / mean if len(values) > 1 else 0
                        # Lower CV = more uniform = more resonant
                        level_score = 1 / (1 + cv)
                        # Weight by level (higher levels = macro patterns = more important)
                        scores.append(level_score * (k + 1))
        
        if not scores:
            return 0.5
        
        # Weighted average
        return sum(scores) / sum(range(1, len(scores) + 2))
    
    def get_level_analysis(self) -> List[dict]:
        """Get detailed analysis per hierarchical level"""
        analysis = []
        for k, heap in enumerate(self.levels):
            analysis.append({
                'level': k,
                'size_bits': self.level_sizes[k],
                'heap_stats': heap.get_stats(),
                'level_stats': self.level_stats[k],
                'normalized': heap.size
            })
        return analysis
    
    def get_state(self) -> dict:
        """Export state for persistence"""
        with self.lock:
            return {
                'num_levels': self.num_levels,
                'total_samples': self.total_samples,
                'level_stats': self.level_stats,
                'level_sizes': [h.size for h in self.levels]
            }
    
    def load_state(self, state: dict):
        """Restore state from persistence"""
        with self.lock:
            self.total_samples = state.get('total_samples', 0)
            saved_stats = state.get('level_stats', [])
            for k, stats in enumerate(saved_stats):
                if k < len(self.level_stats):
                    self.level_stats[k] = stats


class DVFSController:
    """
    Dynamic Voltage and Frequency Scaling Controller
    
    From Veselov paper Algorithm 2:
    - Adapts filter intensity based on computational "load"
    - Implements thermal throttling analog
    
    Formula: P_dyn = α · C · V² · f
    Where α ≈ 0.2 (effective activity coefficient)
    
    In TPF context:
    - "Frequency" = filter intensity/aggressiveness
    - "Voltage" = threshold sensitivity
    - "Temperature" = system load/rejection rate
    """
    
    def __init__(self):
        self.current_freq = 0.5  # Start at 50% intensity
        self.current_voltage = 0.7  # Start at 70% sensitivity
        self.temperature = 0.5  # Load metric
        
        self.history: Deque[float] = deque(maxlen=100)
        self.lock = threading.Lock()
    
    def update(self, load_factor: float, rejection_rate: float):
        """
        Update DVFS parameters based on current load
        
        From paper Algorithm 2: DVFSController
        """
        with self.lock:
            self.history.append(load_factor)
            self.temperature = rejection_rate
            
            # Calculate target frequency based on load
            f_target = Config.MIN_FILTER_FREQ + (
                (Config.MAX_FILTER_FREQ - Config.MIN_FILTER_FREQ) * load_factor
            )
            
            # Temperature-based adjustment
            if self.temperature > Config.T_MAX:
                # Too many rejections - reduce filter intensity
                f_target *= 0.9
            elif self.temperature < (Config.T_MAX - Config.T_DELTA):
                # Room to be more aggressive
                f_target *= 1.1
            
            # Clamp to valid range
            self.current_freq = max(Config.MIN_FILTER_FREQ, 
                                   min(Config.MAX_FILTER_FREQ, f_target))
            
            # Voltage follows frequency (quadratic relationship from paper)
            # V ∝ √f for optimal efficiency
            v_target = math.sqrt(self.current_freq / Config.MAX_FILTER_FREQ)
            self.current_voltage = max(0.5, min(1.0, v_target))
    
    def get_filter_thresholds(self) -> Tuple[float, float]:
        """
        Get adjusted filter thresholds based on DVFS state
        
        Returns (z_score_threshold, jitter_cv_threshold)
        """
        with self.lock:
            # Scale thresholds by current "voltage"
            z_threshold = Config.Z_SCORE_TIER1 * self.current_voltage
            cv_threshold = Config.JITTER_CV_THRESHOLD * self.current_freq
            return z_threshold, cv_threshold
    
    def get_energy_estimate(self) -> float:
        """
        Estimate current "energy" consumption
        
        E = k · α_eff · V² · f
        """
        with self.lock:
            return (Config.ALPHA_EFF * 
                    (self.current_voltage ** 2) * 
                    self.current_freq)
    
    def get_stats(self) -> dict:
        with self.lock:
            return {
                'frequency': self.current_freq,
                'voltage': self.current_voltage,
                'temperature': self.temperature,
                'energy': self.get_energy_estimate(),
                'load_avg': statistics.mean(self.history) if self.history else 0
            }


# ================= DATA STRUCTURES =================
@dataclass
class PoolJob:
    """Job received from pool"""
    worker_id: int
    job_id: str
    prev_hash: str
    coinb1: str
    coinb2: str
    merkle_branch: List[str]
    version: str
    nbits: str
    ntime: str
    clean_jobs: bool
    difficulty: float
    extranonce1: str
    extranonce2_size: int
    timestamp: float = field(default_factory=time.time)
    raw_msg: dict = field(default_factory=dict)


@dataclass
class ShareFeatures:
    """
    Feature vector for a share - Enhanced with Veselov metrics
    """
    timestamp: float
    worker_id: int
    latency_ms: float
    delta_ms: float
    z_score: float
    jitter_std: float
    jitter_cv: float
    shares_since_job: int
    
    # Veselov hierarchical features
    hierarchy_level: int = 0
    resonance_score: float = 0.0
    exponent: int = 0
    dvfs_energy: float = 0.0
    
    # Decision flags
    tier1_pass: bool = False
    tier2_resonant: bool = False
    tier3_pass: bool = False
    decision: str = "PENDING"
    nonce: str = ""
    job_id: str = ""


@dataclass
class WorkerStats:
    shares_sent: int = 0
    shares_accepted: int = 0
    shares_rejected: int = 0
    last_share_time: float = 0


# ================= LBRY HASH FUNCTIONS =================
class LBRYHasher:
    """
    LBRY Proof-of-Work Hash Algorithm
    
    Steps:
    1. intermediate = SHA512(SHA256(SHA256(data)))
    2. split intermediate into two 32-byte halves
    3. left = RIPEMD160(left_half)
    4. right = RIPEMD160(right_half)
    5. final = SHA256(SHA256(left + right))
    """
    
    @staticmethod
    def sha256(data: bytes) -> bytes:
        return hashlib.sha256(data).digest()
    
    @staticmethod
    def sha256d(data: bytes) -> bytes:
        return hashlib.sha256(hashlib.sha256(data).digest()).digest()
    
    @staticmethod
    def sha512(data: bytes) -> bytes:
        return hashlib.sha512(data).digest()
    
    @staticmethod
    def ripemd160(data: bytes) -> bytes:
        h = hashlib.new('ripemd160')
        h.update(data)
        return h.digest()
    
    @classmethod
    def lbry_pow_hash(cls, header: bytes) -> bytes:
        """Compute LBRY proof-of-work hash"""
        # Step 1: SHA512(SHA256(SHA256(header)))
        intermediate = cls.sha512(cls.sha256d(header))
        
        # Step 2: Split into halves (64 bytes -> 2x32 bytes)
        left_half = intermediate[:32]
        right_half = intermediate[32:]
        
        # Step 3-4: RIPEMD160 each half
        left_ripe = cls.ripemd160(left_half)
        right_ripe = cls.ripemd160(right_half)
        
        # Step 5: SHA256d(left + right)
        combined = left_ripe + right_ripe
        final_hash = cls.sha256d(combined)
        
        return final_hash
    
    @classmethod
    def calculate_difficulty(cls, job: PoolJob, en2: str, ntime: str, nonce: str) -> float:
        """Calculate actual difficulty of a share"""
        try:
            # 1. Build Coinbase
            coinbase = job.coinb1 + job.extranonce1 + en2 + job.coinb2
            coinbase_bin = bytes.fromhex(coinbase)
            coinbase_hash = cls.sha256d(coinbase_bin)
            
            # 2. Build Merkle Root
            merkle_root = coinbase_hash
            for branch in job.merkle_branch:
                branch_bin = bytes.fromhex(branch)
                merkle_root = cls.sha256d(merkle_root + branch_bin)
            
            # 3. Build Block Header (112 bytes for LBRY)
            # LBRY header: version(4) + prev_hash(32) + merkle(32) + claim_trie(32) + time(4) + bits(4) + nonce(4)
            # Note: claim_trie may be in job data or zeroed
            
            version_bin = struct.pack("<I", int(job.version, 16))
            prev_hash_bin = bytes.fromhex(job.prev_hash)[::-1]  # Reverse for LE
            ntime_bin = struct.pack("<I", int(ntime, 16))
            nbits_bin = struct.pack("<I", int(job.nbits, 16))
            nonce_bin = struct.pack("<I", int(nonce, 16))
            
            # Claim trie root (32 bytes of zeros if not provided)
            claim_trie = b'\x00' * 32
            
            header = (
                version_bin +
                prev_hash_bin +
                merkle_root +
                claim_trie +
                ntime_bin +
                nbits_bin +
                nonce_bin
            )
            
            # 4. LBRY PoW Hash
            pow_hash = cls.lbry_pow_hash(header)
            pow_hash_be = pow_hash[::-1]  # Big-endian for comparison
            hash_int = int.from_bytes(pow_hash_be, 'big')
            
            # 5. Calculate difficulty
            if hash_int == 0:
                return float('inf')
            
            target_1 = 0x00000000FFFF0000000000000000000000000000000000000000000000000000
            diff = target_1 / hash_int
            
            return diff
            
        except Exception as e:
            log.error(f"[CRYPTO] Hash calculation error: {e}")
            return 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# VESELOV-ENHANCED RESONANCE ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class VeselovResonanceEngine:
    """
    Multi-Tier Thermodynamic Resonance Filter
    Enhanced with Veselov Hierarchical Architecture
    
    Integration of three key innovations:
    1. Hierarchical representation with exponential growth
    2. Binomial heaps for component management
    3. Powers-of-two representation for efficient operations
    
    TIER 1: Basic timing (z-score) with DVFS adaptation
    TIER 2: Hierarchical jitter analysis
    TIER 3: Super-resonance detection via heap coherence
    """
    
    def __init__(self):
        # Veselov hierarchical structure
        self.hierarchy = HierarchicalTimingStructure()
        
        # DVFS controller
        self.dvfs = DVFSController()
        
        # Traditional timing samples (for backward compatibility)
        self.latency_samples: Deque[float] = deque(maxlen=Config.JITTER_HISTORY)
        self.delta_samples: Deque[float] = deque(maxlen=Config.JITTER_WINDOW)
        
        # Statistics
        self.mean = 0.0
        self.std = 1.0
        self.calibrated = False
        self.jitter_std = 0.0
        self.jitter_cv = 0.0
        
        # Counters
        self.total_received = 0
        self.tier1_passed = 0
        self.tier2_resonant = 0
        self.tier3_passed = 0
        self.total_filtered = 0
        self.total_sent = 0
        
        # Timing
        self.last_share_time = time.time()
        self.last_job_time = time.time()
        self.shares_since_job = 0
        
        # Resonance tracking
        self.resonant_latencies: Deque[float] = deque(maxlen=500)
        self.filtered_latencies: Deque[float] = deque(maxlen=500)
        
        # Veselov-specific metrics
        self.hierarchy_scores: Deque[float] = deque(maxlen=100)
        
        self.lock = threading.Lock()
    
    def new_job(self):
        """Called when new job received"""
        self.last_job_time = time.time()
        self.shares_since_job = 0
    
    def update(self, latency_ms: float):
        """
        Update timing statistics with Veselov hierarchical insertion
        """
        with self.lock:
            now = time.time()
            delta_ms = (now - self.last_share_time) * 1000
            self.last_share_time = now
            
            # Traditional tracking
            self.latency_samples.append(latency_ms)
            self.delta_samples.append(delta_ms)
            self.shares_since_job += 1
            
            # Veselov hierarchical insertion
            self.hierarchy.insert(latency_ms)
            
            if len(self.latency_samples) >= Config.CALIBRATION_SAMPLES:
                self.mean = statistics.mean(self.latency_samples)
                self.std = statistics.stdev(self.latency_samples) if len(self.latency_samples) > 1 else 1.0
                
                if len(self.delta_samples) >= 10:
                    self.jitter_std = statistics.stdev(self.delta_samples)
                    jitter_mean = statistics.mean(self.delta_samples)
                    self.jitter_cv = self.jitter_std / (jitter_mean + 1e-9)
                
                # Update DVFS based on current load
                load_factor = self.shares_since_job / max(1, Config.CALIBRATION_SAMPLES)
                rejection_rate = self.total_filtered / max(1, self.total_received)
                self.dvfs.update(load_factor, rejection_rate)
                
                # Track hierarchy score
                h_score = self.hierarchy.get_resonance_score()
                self.hierarchy_scores.append(h_score)
                
                if not self.calibrated:
                    self.calibrated = True
                    log.info(f"[VESELOV] ✓ Calibrated: μ={self.mean:.1f}ms σ={self.std:.1f}ms H-Score={h_score:.3f}")
    
    def evaluate(self, latency_ms: float, force_keep: bool = False) -> ShareFeatures:
        """
        Multi-tier share evaluation with Veselov enhancements
        
        Returns ShareFeatures with decision
        """
        self.total_received += 1
        
        # Get DVFS-adjusted thresholds
        z_threshold, cv_threshold = self.dvfs.get_filter_thresholds()
        
        # Calculate z-score
        z_score = (latency_ms - self.mean) / (self.std + 1e-9) if self.calibrated else 0.0
        
        # Compute Veselov metrics
        h_level = self.hierarchy._compute_level(latency_ms)
        exponent = self.hierarchy._value_to_exponent(latency_ms)
        resonance_score = self.hierarchy.get_resonance_score()
        dvfs_energy = self.dvfs.get_energy_estimate()
        
        # Build features
        features = ShareFeatures(
            timestamp=time.time(),
            worker_id=0,
            latency_ms=latency_ms,
            delta_ms=(time.time() - self.last_share_time) * 1000,
            z_score=z_score,
            jitter_std=self.jitter_std,
            jitter_cv=self.jitter_cv,
            shares_since_job=self.shares_since_job,
            hierarchy_level=h_level,
            resonance_score=resonance_score,
            exponent=exponent,
            dvfs_energy=dvfs_energy
        )
        
        # Not calibrated - pass through
        if not self.calibrated:
            features.decision = "CALIBRATING"
            features.tier1_pass = True
            features.tier3_pass = True
            self.tier1_passed += 1
            self.tier3_passed += 1
            self.total_sent += 1
            return features
        
        # Force keep (keep-alive, safety)
        if force_keep:
            features.decision = "FORCED"
            features.tier1_pass = True
            features.tier3_pass = True
            self.tier1_passed += 1
            self.tier3_passed += 1
            self.total_sent += 1
            return features
        
        # ═══════════════════════════════════════════════════════
        # TIER 1: Basic Timing Filter (DVFS-adjusted)
        # ═══════════════════════════════════════════════════════
        if z_score > z_threshold:
            features.decision = "FILTERED_SLOW"
            self.total_filtered += 1
            self.filtered_latencies.append(latency_ms)
            return features
        
        features.tier1_pass = True
        self.tier1_passed += 1
        
        # ═══════════════════════════════════════════════════════
        # TIER 2: Hierarchical Jitter Analysis (Veselov)
        # ═══════════════════════════════════════════════════════
        
        # Check jitter at the appropriate hierarchical level
        level_stats = self.hierarchy.level_stats[h_level]
        if level_stats['samples'] > 10:
            level_cv = level_stats['std'] / (level_stats['mean'] + 1e-9)
            # DVFS-adjusted threshold
            if level_cv > cv_threshold:
                features.decision = "FILTERED_ENTROPIC"
                self.total_filtered += 1
                self.filtered_latencies.append(latency_ms)
                return features
        
        # Global jitter check
        if self.jitter_cv > cv_threshold:
            features.decision = "FILTERED_ENTROPIC"
            self.total_filtered += 1
            self.filtered_latencies.append(latency_ms)
            return features
        
        # ═══════════════════════════════════════════════════════
        # TIER 3: Resonance Classification (Veselov-Enhanced)
        # ═══════════════════════════════════════════════════════
        
        # Super-resonance: fast timing + high hierarchy coherence
        is_super_resonant = (z_score <= Config.Z_SCORE_TIER2 and 
                           resonance_score > 0.7)
        
        # Hierarchy-based resonance: check exponent pattern
        heap = self.hierarchy.levels[h_level]
        exp_dist = heap.get_exponent_distribution()
        exponent_coherence = 1.0
        if exp_dist:
            # Check if our exponent matches the dominant pattern
            total = sum(exp_dist.values())
            if exponent in exp_dist:
                exponent_coherence = exp_dist[exponent] / total
        
        if is_super_resonant or (z_score <= Config.Z_SCORE_TIER2 and exponent_coherence > 0.3):
            features.tier2_resonant = True
            features.tier3_pass = True
            self.tier2_resonant += 1
            self.tier3_passed += 1
            features.decision = "SUPER_RESONANT"
        elif resonance_score > 0.5:
            features.tier3_pass = True
            self.tier3_passed += 1
            features.decision = "RESONANT"
        else:
            # Edge case: passes timing but low resonance
            # Still allow with lower probability based on DVFS energy
            if dvfs_energy < Config.ALPHA_EFF:
                features.tier3_pass = True
                self.tier3_passed += 1
                features.decision = "MARGINAL_RESONANT"
            else:
                features.decision = "FILTERED_LOW_RESONANCE"
                self.total_filtered += 1
                self.filtered_latencies.append(latency_ms)
                return features
        
        self.total_sent += 1
        self.resonant_latencies.append(latency_ms)
        
        # Update hierarchy with resonance info
        self.hierarchy.level_stats[h_level]['resonant_count'] += 1
        
        return features
    
    def get_stats(self) -> dict:
        with self.lock:
            total = max(1, self.total_received)
            res_avg = statistics.mean(self.resonant_latencies) if self.resonant_latencies else 0
            filt_avg = statistics.mean(self.filtered_latencies) if self.filtered_latencies else 0
            h_avg = statistics.mean(self.hierarchy_scores) if self.hierarchy_scores else 0.5
            
            return {
                'calibrated': self.calibrated,
                'mean_ms': self.mean,
                'std_ms': self.std,
                'jitter_cv': self.jitter_cv,
                'total_received': self.total_received,
                'tier1_passed': self.tier1_passed,
                'tier2_resonant': self.tier2_resonant,
                'tier3_passed': self.tier3_passed,
                'total_filtered': self.total_filtered,
                'total_sent': self.total_sent,
                'filter_rate': (self.total_filtered / total) * 100,
                'resonant_avg_ms': res_avg,
                'filtered_avg_ms': filt_avg,
                # Veselov metrics
                'hierarchy_score_avg': h_avg,
                'dvfs': self.dvfs.get_stats(),
                'hierarchy_levels': self.hierarchy.get_level_analysis()
            }
    
    # ═══════════════════════════════════════════════════════════════
    # STATE PERSISTENCE
    # ═══════════════════════════════════════════════════════════════
    def get_state(self) -> dict:
        """Export state for persistence"""
        with self.lock:
            return {
                'mean': self.mean,
                'std': self.std,
                'calibrated': self.calibrated,
                'jitter_cv': self.jitter_cv,
                'latency_samples': list(self.latency_samples)[-500:],
                'total_received': self.total_received,
                'tier1_passed': self.tier1_passed,
                'tier2_resonant': self.tier2_resonant,
                'total_filtered': self.total_filtered,
                'total_sent': self.total_sent,
                'hierarchy': self.hierarchy.get_state(),
                'dvfs': self.dvfs.get_stats()
            }
    
    def load_state(self, state: dict):
        """Restore state from persistence"""
        with self.lock:
            self.mean = state.get('mean', 0.0)
            self.std = state.get('std', 1.0)
            self.calibrated = state.get('calibrated', False)
            self.jitter_cv = state.get('jitter_cv', 0.0)
            samples = state.get('latency_samples', [])
            self.latency_samples = deque(samples, maxlen=Config.JITTER_HISTORY)
            self.total_received = state.get('total_received', 0)
            self.tier1_passed = state.get('tier1_passed', 0)
            self.tier2_resonant = state.get('tier2_resonant', 0)
            self.total_filtered = state.get('total_filtered', 0)
            self.total_sent = state.get('total_sent', 0)
            
            # Load hierarchy state
            if 'hierarchy' in state:
                self.hierarchy.load_state(state['hierarchy'])
            
            if self.calibrated:
                log.info(f"[VESELOV] ✓ Restored: μ={self.mean:.1f}ms σ={self.std:.1f}ms (from {len(samples)} samples)")


# ================= LEARNING ENGINE =================
class VeselovLearningEngine:
    """
    Pattern Learning with Veselov Hierarchical Analysis
    
    Extends the basic learning with:
    - Hierarchical pattern recognition across levels
    - Power-of-two segment analysis
    - DVFS-aware threshold adaptation
    """
    
    def __init__(self):
        self.winners: List[ShareFeatures] = []
        self.resonant_windows: List[int] = []
        self.pattern_confirmed = False
        
        # Veselov additions
        self.level_patterns: Dict[int, List[int]] = defaultdict(list)  # Level -> winning segments
        self.exponent_winners: Dict[int, int] = defaultdict(int)  # Exponent -> win count
        
        self.lock = threading.Lock()
    
    def get_resonant_segments(self) -> List[int]:
        """Returns list of segments [0..19] to search"""
        with self.lock:
            if not self.pattern_confirmed or not self.resonant_windows:
                return list(range(Config.NONCE_WINDOWS))
            return self.resonant_windows

    def record_share(self, features: ShareFeatures):
        """Record share with Veselov hierarchical analysis"""
        if not features.nonce:
            return
        
        try:
            n_val = int(features.nonce, 16)
            segment = n_val % Config.NONCE_WINDOWS
            
            with self.lock:
                if features.tier2_resonant:
                    # Track segment
                    if segment not in self.resonant_windows:
                        self.resonant_windows.append(segment)
                        log.info(f"[LEARN-V] 🔍 Resonant Segment: {segment} | Level: {features.hierarchy_level} | H-Score: {features.resonance_score:.3f}")
                    
                    # Track level patterns
                    if segment not in self.level_patterns[features.hierarchy_level]:
                        self.level_patterns[features.hierarchy_level].append(segment)
                    
                    # Track exponent patterns
                    self.exponent_winners[features.exponent] += 1
                    
                    # Limit segments
                    if len(self.resonant_windows) > 5:
                        self.resonant_windows.pop(0)
                    
                    self.pattern_confirmed = True
                    
        except Exception as e:
            log.debug(f"[LEARN-V] Nonce parse error: {e}")
    
    def get_dominant_exponent(self) -> Optional[int]:
        """Get the most common winning exponent"""
        with self.lock:
            if not self.exponent_winners:
                return None
            return max(self.exponent_winners, key=self.exponent_winners.get)
    
    def get_level_focus(self) -> Optional[int]:
        """Get the hierarchical level with most wins"""
        with self.lock:
            if not self.level_patterns:
                return None
            level_counts = {k: len(v) for k, v in self.level_patterns.items()}
            return max(level_counts, key=level_counts.get)
    
    def get_stats(self) -> dict:
        with self.lock:
            return {
                'num_winners': len(self.winners),
                'pattern_confirmed': self.pattern_confirmed,
                'resonant_segments': self.resonant_windows,
                'focal_ratio': len(self.resonant_windows) / Config.NONCE_WINDOWS if self.pattern_confirmed else 1.0,
                'level_patterns': dict(self.level_patterns),
                'exponent_winners': dict(self.exponent_winners),
                'dominant_exponent': self.get_dominant_exponent(),
                'focus_level': self.get_level_focus()
            }
    
    def get_state(self) -> dict:
        with self.lock:
            return {
                'resonant_windows': self.resonant_windows.copy(),
                'pattern_confirmed': self.pattern_confirmed,
                'level_patterns': {k: list(v) for k, v in self.level_patterns.items()},
                'exponent_winners': dict(self.exponent_winners)
            }
    
    def load_state(self, state: dict):
        with self.lock:
            self.resonant_windows = state.get('resonant_windows', [])
            self.pattern_confirmed = state.get('pattern_confirmed', False)
            self.level_patterns = defaultdict(list, {
                int(k): v for k, v in state.get('level_patterns', {}).items()
            })
            self.exponent_winners = defaultdict(int, {
                int(k): v for k, v in state.get('exponent_winners', {}).items()
            })
            if self.resonant_windows:
                log.info(f"[LEARN-V] ✓ Restored {len(self.resonant_windows)} segments, {len(self.level_patterns)} level patterns")


# ================= STATE PERSISTENCE =================
def save_tpf_state(resonance: VeselovResonanceEngine, learning: VeselovLearningEngine):
    """Save all learned state to file"""
    state = {
        'version': '3.0-veselov',
        'timestamp': time.time(),
        'save_date': datetime.now().isoformat(),
        'resonance': resonance.get_state(),
        'learning': learning.get_state()
    }
    try:
        with open(Config.STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
        log.info(f"[PERSIST] ✓ State saved to {Config.STATE_FILE}")
    except Exception as e:
        log.error(f"[PERSIST] Save failed: {e}")


def load_tpf_state(resonance: VeselovResonanceEngine, learning: VeselovLearningEngine) -> bool:
    """Load state from file, returns True if successful"""
    if not Config.STATE_FILE.exists():
        log.info("[PERSIST] No saved state found, starting fresh calibration...")
        return False
    try:
        with open(Config.STATE_FILE, 'r') as f:
            state = json.load(f)
        resonance.load_state(state.get('resonance', {}))
        learning.load_state(state.get('learning', {}))
        age_hours = (time.time() - state.get('timestamp', 0)) / 3600
        log.info(f"[PERSIST] ✓ State loaded successfully (age: {age_hours:.1f}h)")
        return True
    except Exception as e:
        log.error(f"[PERSIST] Load failed: {e}")
        return False


# ================= TELEMETRY ENGINE =================
class TelemetryEngine:
    """Comprehensive data collection with Veselov metrics"""
    
    def __init__(self):
        self.start_time = time.time()
        self.output_dir = Path(f"./results/{Config.EXPERIMENT_NAME}")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.shares_file = self.output_dir / "shares.csv"
        self.stats_file = self.output_dir / "stats.csv"
        self.hierarchy_file = self.output_dir / "hierarchy.csv"
        self.config_file = self.output_dir / "config.json"
        
        self._init_files()
        self.lock = threading.Lock()
    
    def _init_files(self):
        # Shares CSV with Veselov fields
        with open(self.shares_file, 'w', newline='') as f:
            csv.writer(f).writerow([
                'timestamp', 'worker_id', 'latency_ms', 'z_score',
                'jitter_cv', 'decision', 'nonce',
                'hierarchy_level', 'resonance_score', 'exponent', 'dvfs_energy'
            ])
        
        # Stats CSV
        with open(self.stats_file, 'w', newline='') as f:
            csv.writer(f).writerow([
                'timestamp', 'elapsed_min', 'workers_connected',
                'total_received', 'total_sent', 'total_filtered',
                'pool_accepts', 'pool_rejects', 'accept_rate',
                'mean_ms', 'std_ms', 'filter_rate',
                'hierarchy_score', 'dvfs_freq', 'dvfs_energy'
            ])
        
        # Hierarchy analysis CSV
        with open(self.hierarchy_file, 'w', newline='') as f:
            csv.writer(f).writerow([
                'timestamp', 'level', 'size_bits', 'heap_size',
                'level_mean', 'level_std', 'resonant_count'
            ])
        
        # Config JSON
        with open(self.config_file, 'w') as f:
            json.dump(Config.to_dict(), f, indent=2, default=str)
    
    def log_share(self, features: ShareFeatures):
        with self.lock:
            with open(self.shares_file, 'a', newline='') as f:
                csv.writer(f).writerow([
                    features.timestamp, features.worker_id, features.latency_ms,
                    features.z_score, features.jitter_cv, features.decision,
                    features.nonce, features.hierarchy_level, features.resonance_score,
                    features.exponent, features.dvfs_energy
                ])
    
    def log_stats(self, stats: dict):
        elapsed = (time.time() - self.start_time) / 60
        res = stats.get('resonance', {})
        dvfs = res.get('dvfs', {})
        
        with open(self.stats_file, 'a', newline='') as f:
            csv.writer(f).writerow([
                time.time(), elapsed, stats.get('workers_connected', 0),
                res.get('total_received', 0), res.get('total_sent', 0),
                res.get('total_filtered', 0), stats.get('pool_accepts', 0),
                stats.get('pool_rejects', 0), stats.get('accept_rate', 0),
                res.get('mean_ms', 0), res.get('std_ms', 0),
                res.get('filter_rate', 0), res.get('hierarchy_score_avg', 0),
                dvfs.get('frequency', 0), dvfs.get('energy', 0)
            ])
        
        # Log hierarchy levels
        for level_data in res.get('hierarchy_levels', []):
            with open(self.hierarchy_file, 'a', newline='') as f:
                level_stats = level_data.get('level_stats', {})
                csv.writer(f).writerow([
                    time.time(), level_data.get('level', 0),
                    level_data.get('size_bits', 0),
                    level_data.get('heap_stats', {}).get('size', 0),
                    level_stats.get('mean', 0), level_stats.get('std', 0),
                    level_stats.get('resonant_count', 0)
                ])


# ================= VIRTUAL WORKER =================
class VirtualWorker:
    """Virtual worker maintaining connection to pool"""
    
    def __init__(self, worker_id: int, nexus: 'SwarmNexus'):
        self.id = worker_id
        self.worker_name = f"{Config.USER_WALLET}.v{worker_id:02d}"
        self.nexus = nexus
        
        self.sock: Optional[socket.socket] = None
        self.connected = False
        self.lock = threading.Lock()
        
        self.extranonce1: Optional[str] = None
        self.extranonce2_size: int = 4
        self.difficulty: float = 4096.0
        self.subscribed = False
        self.authorized = False
        
        self.stats = WorkerStats()
        self.pending_submits: Dict[int, float] = {}
        self.msg_counter = 1000 + worker_id * 1000
    
    def connect(self):
        """Connect to pool with retry"""
        while True:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(30)
                self.sock.connect((Config.REMOTE_HOST, Config.REMOTE_PORT))
                self.sock.settimeout(None)
                
                self._send({"id": 1, "method": "mining.subscribe", 
                           "params": [Config.FAKE_AGENT]})
                time.sleep(0.2)
                self._send({"id": 2, "method": "mining.authorize",
                           "params": [self.worker_name, Config.POOL_PASS]})
                
                self.connected = True
                log.info(f"[W{self.id:02d}] ✓ Connected as {self.worker_name}")
                
                threading.Thread(target=self._listen_loop, daemon=True).start()
                return
                
            except Exception as e:
                log.warning(f"[W{self.id:02d}] Connection failed: {e}")
                time.sleep(5)
    
    def _send(self, data: dict):
        try:
            with self.lock:
                if self.sock:
                    self.sock.sendall((json.dumps(data) + '\n').encode())
        except:
            self.connected = False
    
    def _listen_loop(self):
        buffer = ""
        while self.connected:
            try:
                data = self.sock.recv(8192).decode('utf-8', errors='ignore')
                if not data:
                    break
                buffer += data
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line.strip():
                        try:
                            self._process_message(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            except:
                break
        self.connected = False
        log.warning(f"[W{self.id:02d}] Disconnected - reconnecting soon...")
        try:
            self.sock.close()
        except:
            pass
        time.sleep(5)
        # Re-entry via same established loop
        self.connect()
    
    def _process_message(self, msg: dict):
        # log.info(f"[W{self.id:02d} <- POOL] {msg}") # Too verbose for production
        msg_id = msg.get('id')
        method = msg.get('method')
        result = msg.get('result')
        error = msg.get('error')
        
        if error:
            log.warning(f"[W{self.id:02d}] Pool Error: {error} (id={msg_id})")
        
        if msg_id == 1 and result:
            # Subscribe response
            if isinstance(result, list) and len(result) >= 3:
                self.extranonce1 = result[1]
                self.extranonce2_size = int(result[2])
                self.subscribed = True
                log.debug(f"[W{self.id:02d}] Subscribed: en1={self.extranonce1}")
                
        elif msg_id == 2:
            # Authorize response
            self.authorized = bool(result)
            
        elif method == 'mining.set_difficulty':
            self.difficulty = msg['params'][0]
            
        elif method == 'mining.notify':
            params = msg['params']
            job = PoolJob(
                worker_id=self.id,
                job_id=params[0],
                prev_hash=params[1],
                coinb1=params[2],
                coinb2=params[3],
                merkle_branch=params[4],
                version=params[5],
                nbits=params[6],
                ntime=params[7],
                clean_jobs=params[8] if len(params) > 8 else False,
                difficulty=self.difficulty,
                extranonce1=self.extranonce1,
                extranonce2_size=self.extranonce2_size,
                raw_msg=msg
            )
            self.nexus.register_job(job)
            
        elif msg_id and (msg_id >= 1000 or msg_id == 4):
            # Share response
            if result is True:
                self.stats.shares_accepted += 1
                self.nexus.record_accept(self.id)
            else:
                self.stats.shares_rejected += 1
                self.nexus.record_reject(self.id, error)
    
    def submit_share(self, job_id: str, extranonce2: str, ntime: str, nonce: str):
        self.msg_counter += 1
        self.pending_submits[self.msg_counter] = time.time()
        self.stats.shares_sent += 1
        self.stats.last_share_time = time.time()
        
        # Reverting to incrementing IDs and 5 params
        self._send({
            "id": self.msg_counter, 
            "method": "mining.submit",
            "params": [self.worker_name, job_id, extranonce2, ntime, nonce]
        })


# ================= SWARM NEXUS =================
class SwarmNexus:
    """Central controller with Veselov-enhanced resonance engine"""
    
    def __init__(self, telemetry: TelemetryEngine):
        self.telemetry = telemetry
        self.workers: List[VirtualWorker] = []
        
        # Veselov-enhanced engines
        self.resonance = VeselovResonanceEngine()
        self.learning = VeselovLearningEngine()
        
        # RESILIENCE: Expanded job buffer and stats
        self.job_buffer: Deque[str] = deque(maxlen=1000)
        self.local_id_counter = 0
        self.local_to_job: Dict[str, PoolJob] = {}
        self.lock = threading.Lock()
        
        # Stats
        self.start_time = time.time()
        self.pool_accepts = 0 
        self.pool_rejects = 0 
        self.total_submitted_to_pool = 0 # NEW: Actual traffic count
        
        # Affinity (RE-ADDED)
        self.sticky_worker_id = 1
        self.sticky_shares_remaining = Config.AFFINITY_SHARES
        log.info(f"[NEXUS] Initialized with sticky_worker={self.sticky_worker_id}")
        
        # Persistence & Heartbeat
        self.sent_nonces: Deque[str] = deque(maxlen=20000)
        self.last_forced: Dict[int, float] = {}
        self.last_pool_submit = time.time() 
        self.heartbeat_lock = threading.Lock()
    
    def boot(self):
        # ═══════════════════════════════════════════════════════════════
        # LOAD PREVIOUS STATE (V2.0)
        # ═══════════════════════════════════════════════════════════════
        load_tpf_state(self.resonance, self.learning)
        
        log.info(f"[SWARM] Booting {Config.SWARM_SIZE} virtual workers...")
        
        for i in range(1, Config.SWARM_SIZE + 1):
            worker = VirtualWorker(i, self)
            self.workers.append(worker)
            self.last_forced[i] = time.time()
            threading.Thread(target=worker.connect, daemon=True).start()
            time.sleep(0.3)
        
        time.sleep(3)
        connected = sum(1 for w in self.workers if w.connected)
        log.info(f"[SWARM] {connected}/{Config.SWARM_SIZE} workers ready")
        
        # ═══════════════════════════════════════════════════════════════
        # START AUTO-SAVE THREAD (V2.0)
        # ═══════════════════════════════════════════════════════════════
        threading.Thread(target=self._auto_save_loop, daemon=True).start()
        log.info(f"[PERSIST] Auto-save enabled (every {Config.AUTO_SAVE_INTERVAL}s)")
    
    def _auto_save_loop(self):
        """Periodically save state to disk"""
        while True:
            time.sleep(Config.AUTO_SAVE_INTERVAL)
            save_tpf_state(self.resonance, self.learning)
    
    def register_job(self, job: PoolJob):
        with self.lock:
            self.local_id_counter += 1
            local_id = f"L{self.local_id_counter:08d}"
            self.local_to_job[local_id] = job
            self.job_buffer.append(local_id)
            
            while len(self.local_to_job) > 150:
                old = self.job_buffer.popleft()
                self.local_to_job.pop(old, None)
    
    def get_job_for_asic(self) -> Optional[Tuple[str, PoolJob]]:
        with self.lock:
            if not self.job_buffer:
                return None
            
            # Try sticky worker first
            for lid in reversed(list(self.job_buffer)):
                job = self.local_to_job.get(lid)
                if job and job.worker_id == self.sticky_worker_id:
                    if self.sticky_shares_remaining > 0:
                        return lid, job
                    break
            
            # Rotate to next worker
            self.sticky_worker_id = (self.sticky_worker_id % Config.SWARM_SIZE) + 1
            self.sticky_shares_remaining = Config.AFFINITY_SHARES
            
            for lid in reversed(list(self.job_buffer)):
                job = self.local_to_job.get(lid)
                if job and job.worker_id == self.sticky_worker_id:
                    return lid, job
            
            # FALLBACK: Return ANY available job to prevent deadlock
            if self.job_buffer:
                lid = list(self.job_buffer)[-1]  # Most recent
                job = self.local_to_job.get(lid)
                if job:
                    self.sticky_worker_id = job.worker_id  # Adopt this worker
                    log.debug(f"[NEXUS] Fallback to W{job.worker_id:02d}")
                    return lid, job
            
            return None

    
    def process_share(self, local_id: str, nonce: str, en2: str, 
                      ntime: str, latency_ms: float):
        """Process share through resonance filter"""
        job = self.local_to_job.get(local_id)
        if not job:
            return
        
        # Anti-duplicate
        with self.lock:
            if nonce in self.sent_nonces:
                return
            self.sent_nonces.append(nonce)
        
        # Update timing stats
        self.resonance.update(latency_ms)
        
        # Heartbeat Pulse (Global pool keep-alive)
        now = time.time()
        force = False
        
        with self.heartbeat_lock:
            if (now - self.last_pool_submit) > Config.HEARTBEAT_SEC:
                force = True
                log.info(f"[⚙] VESELOV HEARTBEAT: Sending share (Silent for {now - self.last_pool_submit:.0f}s)")
                self.last_pool_submit = now # Update early to prevent racing spams
        
        # Random safety pass
        import random
        if random.random() < Config.SAFETY_KEEP_RATE:
            force = True
        
        # Evaluate through resonance engine
        features = self.resonance.evaluate(latency_ms, force_keep=force)
        features.worker_id = job.worker_id
        features.nonce = nonce
        features.job_id = local_id
        
        # Decision
        if features.tier1_pass and features.tier3_pass:
            # SEND to pool
            worker = self.workers[job.worker_id - 1]
            worker.submit_share(job.job_id, en2, ntime, nonce)
            
            with self.heartbeat_lock:
                self.last_pool_submit = now
                self.total_submitted_to_pool += 1
                self.last_forced[job.worker_id] = now
            
            if self.sticky_shares_remaining > 0:
                self.sticky_shares_remaining -= 1
            
            if Config.LOG_RESONANT:
                log.info(f"[💎] W{worker.id:02d} | {latency_ms:6.1f}ms | z={features.z_score:+.2f} | {features.decision}")
        else:
            if Config.LOG_FILTERED:
                log.debug(f"[✗] {latency_ms:6.1f}ms | z={features.z_score:+.2f} | {features.decision}")
        
        # Log to telemetry & Update Prediction Model
        self.telemetry.log_share(features)
        self.learning.record_share(features)
    
    def record_accept(self, worker_id: int):
        with self.lock:
            self.pool_accepts += 1

    def record_reject(self, worker_id: int, error):
        with self.lock:
            self.pool_rejects += 1
            log.warning(f"[REJECT] W{worker_id:02d} | {error}")
    
    def get_stats(self) -> dict:
        runtime = time.time() - self.start_time
        res = self.resonance.get_stats()
        
        return {
            'runtime_min': runtime / 60,
            'workers_connected': sum(1 for w in self.workers if w.connected),
            'pool_accepts': self.pool_accepts,
            'pool_rejects': self.pool_rejects,
            'total_sent': self.total_submitted_to_pool,
            'pool_efficiency': (self.pool_accepts / max(1, self.total_submitted_to_pool)) * 100,
            'resonance': res,
            'learning': self.learning.get_stats()
        }


# ================= LB-BOX PROXY =================
class LBBoxProxy:
    """
    Local proxy with Veselov-enhanced job feeding
    """
    
    def __init__(self, nexus: SwarmNexus):
        self.nexus = nexus
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        self.asic_socket: Optional[socket.socket] = None
        self.last_job_time = time.time()
        self.running = True
        self.lock = threading.Lock()
        
        # Buffer for 'Pizza Butler' zero-latency feed
        self.last_sent_job_id = ""
        self.last_fed_worker_id = 0
        
    def start(self):
        try:
            self.server.bind((Config.LOCAL_HOST, Config.LOCAL_PORT))
            self.server.listen(1)
            
            local_ip = self._get_local_ip()
            log.info("="*60)
            log.info(f"[PROXY] LISTENING ON {Config.LOCAL_HOST}:{Config.LOCAL_PORT}")
            log.info(f"[*] CONFIGURE LB-BOX URL:  stratum+tcp://{local_ip}:{Config.LOCAL_PORT}")
            log.info(f"[*] CONFIGURE LB-BOX USR:  {Config.USER_WALLET}")
            log.info(f"[*] CONFIGURE LB-BOX PWD:  x")
            log.info("="*60)
            
            while self.running:
                try:
                    conn, addr = self.server.accept()
                    log.info(f"[LB-BOX] ➤ INCOMING CONNECTION from {addr}")
                    self._handle_asic_session(conn)
                except Exception as e:
                    log.error(f"[PROXY] Accept error: {e}")
                    time.sleep(1)
        except Exception as e:
            log.critical(f"[PROXY] Bind failed: {e}")
            sys.exit(1)
    
    def _get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    def _send(self, msg: dict):
        try:
            with self.lock:
                if self.asic_socket:
                    data = json.dumps(msg) + '\n'
                    self.asic_socket.sendall(data.encode())
                    # log.debug(f"[TX] {msg.get('method') or msg.get('id')}")
        except Exception as e:
            log.error(f"[PROXY] Send error: {e}")
            self.asic_socket = None
    
    def _handle_asic_session(self, conn):
        self.asic_socket = conn
        conn.settimeout(None)
        buffer = ""
        
        while self.asic_socket:
            try:
                data = conn.recv(4096).decode('utf-8', errors='ignore')
                if not data:
                    break
                
                buffer += data
                
                # Goldshell robustness: Handle both \n and \x00
                while '\n' in buffer or '\x00' in buffer:
                    if '\n' in buffer and ('\x00' not in buffer or buffer.find('\n') < buffer.find('\x00')):
                        line, buffer = buffer.split('\n', 1)
                    else:
                        line, buffer = buffer.split('\x00', 1)
                    
                    if not line.strip(): continue
                    
                    try:
                        self._process_msg(json.loads(line))
                    except json.JSONDecodeError:
                        log.warning(f"[PROXY] Invalid JSON: {line[:50]}...")
                        
            except ConnectionResetError:
                break
            except Exception as e:
                log.error(f"[PROXY] Session error: {e}")
                break
        
        log.warning("[LB-BOX] ✗ DISCONNECTED")
        if self.asic_socket:
            try: self.asic_socket.close()
            except: pass
        self.asic_socket = None
    
    def _process_msg(self, msg: dict):
        method = msg.get('method')
        mid = msg.get('id')
        
        log.info(f"[LB-BOX] Command: {method} (id={mid})")
        
        if method == 'mining.configure':
            # Goldshell required negotiation
            self._send({
                "id": mid,
                "result": {
                    "version-rolling": True, 
                    "version-rolling.mask": "1fffe000"
                },
                "error": None
            })
            
        elif method == 'mining.subscribe':
            log.info("[LB-BOX] Subscribing... Waiting for SWARM...")
            
            # Wait for backend workers
            retries = 0
            while not any(w.extranonce1 for w in self.nexus.workers):
                time.sleep(1)
                retries += 1
                if retries % 5 == 0:
                    log.warning("[PROXY] Still waiting for swarm connection...")
            
            # Pick a primary worker for metadata
            worker = next(w for w in self.nexus.workers if w.extranonce1)
            
            # 1. Reply to subscribe - USE THE STABLE FORMAT!
            self._send({
                "id": mid,
                "result": [
                    ["mining.notify", "lbc_sub_target"],  # Use same string as stable script
                    worker.extranonce1,
                    worker.extranonce2_size
                ],
                "error": None
            })

            
            # 2. Set Difficulty (CRITICAL for Goldshell)
            self._send({
                "id": None,
                "method": "mining.set_difficulty",
                "params": [worker.difficulty]
            })
            
            # 3. Force Feed First Job
            self._feed_butler(clean=True)
            log.info("[LB-BOX] ✓ Handshake Complete. Mining Started.")
            
        elif method == 'mining.authorize':
            self._send({"id": mid, "result": True, "error": None})
            # Feed again just in case
            self._feed_butler(clean=False)
            
        elif method == 'mining.submit':
            # 1. Instant ACK (The "Butler" promise)
            self._send({"id": mid, "result": True, "error": None})
            
            # 2. Measure Latency
            latency = (time.time() - self.last_job_time) * 1000
            
            # 3. Feed Next Job Immediately (Zero Latency)
            self._feed_butler(clean=True)
            
            # 4. Process the Share Async
            params = msg.get('params', [])
            if len(params) >= 5:
                # worker_name, job_id, en2, ntime, nonce
                threading.Thread(
                    target=self.nexus.process_share,
                    args=(params[1], params[4], params[2], params[3], latency)
                ).start()
    
    def _feed_butler(self, clean: bool = False):
        """
        Veselov-enhanced job feeding (Fixed with Total Safety and Tracing)
        """
        log.info("[TRACE-BUTLER] 1: Start")
        result = self.nexus.get_job_for_asic()
        if not result:
            log.info("[TRACE-BUTLER] 2: No job available")
            return 
            
        local_id, job = result
        if local_id == self.last_sent_job_id and not clean:
            log.info("[TRACE-BUTLER] 3: Duplicate job skip")
            return
            
        self.last_job_time = time.time()
        self.last_sent_job_id = local_id
        
        worker = self.nexus.workers[job.worker_id - 1] if job.worker_id <= len(self.nexus.workers) else None
        
        if worker:
            if job.worker_id != self.last_fed_worker_id:
                log.info(f"[TRACE-BUTLER] 4: Syncing worker {job.worker_id}")
                if worker.extranonce1:
                    self._send({"id": None, "method": "mining.set_extranonce", "params": [worker.extranonce1, worker.extranonce2_size]})
                if worker.difficulty:
                    self._send({"id": None, "method": "mining.set_difficulty", "params": [worker.difficulty]})
                self.last_fed_worker_id = job.worker_id
        
        log.info("[TRACE-BUTLER] 5: Evaluating filters")
        # MANDATORY BYPASS FOR HANDSHAKE STABILITY
        if self.nexus.resonance.total_received < 10:
            log.info("[BUTLER] Fresh session: Bypassing filters for handshake")
        else:
            # TOTAL SAFETY WRAPPER FOR MATHEMATICAL MODELS
            try:
                stats = self.nexus.resonance.get_stats()
                jitter_cv = stats.get('jitter_cv', 1.0)
                
                silence_sec = time.time() - self.nexus.last_pool_submit
                need_heartbeat = silence_sec > 150
                
                dvfs = stats.get('dvfs', {})
                cv_threshold = Config.JITTER_CV_THRESHOLD * dvfs.get('frequency', 1.0)
                
                if not need_heartbeat and jitter_cv > cv_threshold:
                    log.info("[BUTLER] DVFS Filtered - High jitter detected")
                    return
            except Exception as e:
                log.warning(f"[BUTLER] Filter model bypass on error: {e}")
        
        log.info("[TRACE-BUTLER] 7: Constructing notify message")
        try:
            # Use raw message from pool but update local ID
            p = list(job.raw_msg.get('params', []))
            if not p:
                log.error("[TRACE-BUTLER] ALERT: Job raw_msg['params'] is empty")
                return
                
            p[0] = local_id
            p[-1] = True # Clean jobs
            
            log.info(f"[PROXY] Feeding job {local_id} (params={len(p)})")
            
            self._send({
                "method": "mining.notify",
                "params": p
            })
            log.info("[TRACE-BUTLER] 8: Notify complete")
        except Exception as e:
            log.error(f"[PROXY] Error constructing job message: {e}")



# ================= MONITOR =================
def monitor(nexus: SwarmNexus, telemetry: TelemetryEngine):
    """Monitoring thread with Veselov metrics"""
    print("\n" + "=" * 70)
    print("  TPF ULTIMATE V3.0 - VESELOV EDITION")
    print("  \"Hierarchical resonance through exponential growth\"")
    print("=" * 70 + "\n")
    
    while True:
        time.sleep(30)
        
        s = nexus.get_stats()
        res = s['resonance']
        dvfs = res.get('dvfs', {})
        learn = s.get('learning', {})
        
        telemetry.log_stats(s)
        
        log.info(f"  Connection: {s['workers_connected']}/{Config.SWARM_SIZE} Workers Connected")
        log.info(f"  Pool Accepts: {s['pool_accepts']} | Rejects: {s['pool_rejects']} | Sent: {s['total_sent']}")
        log.info(f"  H-Pulse: {time.time() - nexus.last_pool_submit:.0f}s ago")
        
        log.info(f"  TPF: μ={res['mean_ms']:.1f}ms | σ={res['std_ms']:.1f}ms | CV={res['jitter_cv']:.3f}")
        log.info(f"  VESELOV: H-Score={res['hierarchy_score_avg']:.3f} | DVFS-f={dvfs.get('frequency', 0):.2f} | E={dvfs.get('energy', 0):.3f}")
        
        if learn.get('pattern_confirmed'):
            log.info(f"  LEARNING: Focus={learn.get('focus_level')} | Exp={learn.get('dominant_exponent')} | Segments={learn.get('resonant_segments')}")
        
        if s['total_sent'] > 0:
            log.info(f"\n  📊 Pool Efficiency: {s['pool_efficiency']:.1f}%")
        print("-" * 70)
        if s['total_sent'] > 0: # Re-add this check as it was removed by the snippet
            accept_rate = s['pool_accepts'] / s['total_sent'] * 100
            effective = s['pool_accepts'] / max(1, res['total_received']) * 100
            log.info(f"  📊 Accept Rate: {accept_rate:.1f}% | Effective: {effective:.2f}%")


# ================= MAIN =================
def main():
    print("""
    ╔═══════════════════════════════════════════════════════════════════════════════╗
    ║              TPF ULTIMATE V3.0 - VESELOV-INTEGRATED ARCHITECTURE              ║
    ║                                                                               ║
    ║   Mathematical Innovations:                                                   ║
    ║   • Hierarchical Representation with Exponential Growth (Sₖ = 64·2ᵏ)         ║
    ║   • Binomial Heaps for Component Management - O(log n) merge                 ║
    ║   • Powers-of-Two Representation: N = Σ 2^p(u)                               ║
    ║   • DVFS-Inspired Adaptive Control: P = α·C·V²·f                             ║
    ║                                                                               ║
    ║   "The silicon speaks hierarchically. We listen with exponential ears."       ║
    ╚═══════════════════════════════════════════════════════════════════════════════╝
    
    CONFIGURATION:
      Pool:       {host}:{port}
      Wallet:     {wallet}
      Workers:    {swarm} virtual workers
      Hierarchy:  {levels} levels (Sₖ = 64·2ᵏ bits)
      Filter:     z ≤ {z1} (Tier1) | z ≤ {z2} (Resonant)
      DVFS:       αeff = {alpha} | f ∈ [{fmin}, {fmax}]
      
    OUTPUT:
      ./results/{name}/
    """.format(
        host=Config.REMOTE_HOST,
        port=Config.REMOTE_PORT,
        wallet=Config.USER_WALLET,
        swarm=Config.SWARM_SIZE,
        levels=Config.NUM_HIERARCHY_LEVELS,
        z1=Config.Z_SCORE_TIER1,
        z2=Config.Z_SCORE_TIER2,
        alpha=Config.ALPHA_EFF,
        fmin=Config.MIN_FILTER_FREQ,
        fmax=Config.MAX_FILTER_FREQ,
        name=Config.EXPERIMENT_NAME
    ))
    
    # Initialize
    telemetry = TelemetryEngine()
    nexus = SwarmNexus(telemetry)
    
    # Graceful shutdown
    def shutdown(sig, frame):
        print("\n\n[SHUTDOWN] Saving Veselov state...")
        save_tpf_state(nexus.resonance, nexus.learning)
        
        print("[SHUTDOWN] Generating final report...")
        stats = nexus.get_stats()
        res = stats['resonance']
        dvfs = res.get('dvfs', {})
        learn = stats.get('learning', {})
        
        print(f"""
╔══════════════════════════════════════════════════════════════════════════════════╗
║                     TPF ULTIMATE V3.0 - VESELOV FINAL REPORT                     ║
╚══════════════════════════════════════════════════════════════════════════════════╝

Runtime: {stats['runtime_min']:.1f} minutes

RESONANCE:
  Total Evaluated:  {res['total_received']:,}
  Total Filtered:   {res['total_filtered']:,} ({res['filter_rate']:.1f}%)
  Super-Resonant:   {res['tier2_resonant']:,}

VESELOV METRICS:
  Hierarchy Score:  {res['hierarchy_score_avg']:.4f}
  DVFS Frequency:   {dvfs.get('frequency', 0):.3f}
  DVFS Voltage:     {dvfs.get('voltage', 0):.3f}
  Energy Estimate:  {dvfs.get('energy', 0):.4f}

LEARNING:
  Pattern Found:    {learn.get('pattern_confirmed')}
  Focus Level:      {learn.get('focus_level')}
  Dominant Exp:     {learn.get('dominant_exponent')}
  Segments:         {learn.get('resonant_segments')}

POOL RESULTS:
  Accepted:         {stats['pool_accepts']:,}
  Rejected:         {stats['pool_rejects']:,}
  Efficiency:       {stats['pool_efficiency']:.1f}%

TIMING:
  Mean:             {res['mean_ms']:.1f} ms
  Std Dev:          {res['std_ms']:.2f} ms
  Jitter (CV):      {res['jitter_cv']:.3f}

Report saved to {telemetry.output_dir}
""")
        sys.exit(0)
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    # Boot swarm
    nexus.boot()
    time.sleep(2)
    
    # Start monitor
    threading.Thread(target=monitor, args=(nexus, telemetry), daemon=True).start()
    
    # Start proxy
    proxy = LBBoxProxy(nexus)
    proxy.start()


if __name__ == "__main__":
    main()

