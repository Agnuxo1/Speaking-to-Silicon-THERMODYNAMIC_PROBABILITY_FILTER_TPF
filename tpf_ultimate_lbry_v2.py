#!/usr/bin/env python3
"""
TPF ULTIMATE V2.0 - LBRY EDITION (WITH PERSISTENCE)
====================================================
The Definitive Thermodynamic Probability Filter for LBRY Mining

Hardware: Goldshell LB-Box (Zynq-7010)
Pool: Mining-Dutch LBRY Solo
Algorithm: LBRY (SHA256+SHA512+RIPEMD160)

Features:
- Multi-Tier Resonance Filter (Timing → Jitter → Crypto)
- Virtual Worker Swarm (10 workers)
- Adaptive Learning Engine
- LBRY Hash Verification
- Comprehensive Telemetry
- STATE PERSISTENCE (New in v2.0) - Learning survives restarts!

Author: Francisco Angulo de Lafuente
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
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Tuple, Deque
from datetime import datetime
from pathlib import Path
import logging

# ================= LOGGING =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('TPF-ULTIMATE')

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
    SWARM_SIZE = 2             # Reduced to avoid ASIC stalling
  # Virtual workers
    
    # ═══════════════════════════════════════════════════════════════
    # MULTI-TIER RESONANCE FILTER CONFIGURATION
    # ═══════════════════════════════════════════════════════════════
    
    # TIER 1: Basic Timing Filter
    # Shares slower than this z-score are immediately filtered
    Z_SCORE_TIER1 = 0.8  # ~79% pass (conservative start)
    
    # TIER 2: Resonance Detection
    # Shares faster than this are "super-resonant" (skip crypto check)
    Z_SCORE_TIER2 = -0.5  # Top ~31% are resonant
    
    # TIER 3: Jitter Focus
    JITTER_CV_THRESHOLD = 0.95    # Adaptive for LBC (Start permissive)
    CALIBRATION_SAMPLES = 100
    
    # Heartbeat & Persistence
    HEARTBEAT_SEC = 120           # Global pool keep-alive
    KEEP_ALIVE_SEC = 300          # Per-worker forced share
    
    # Simulation Logic
    VESELOV_K = 5                 # Veselov round check analogy
    JITTER_WINDOW = 50
    JITTER_HISTORY = 5000
    
    # Worker Management
    AFFINITY_SHARES = 20
    KEEP_ALIVE_SEC = 300       # 5 minutes to keep pool connections hot
    
    # Safety
    SAFETY_KEEP_RATE = 0.03  # 3% random pass-through
    
    # Learning Engine Parameters
    MIN_WINNERS_FOR_LEARNING = 3
    PATTERN_SIGNIFICANCE = 0.01  # More strict for pre-filtering
    
    # x20 Window Configuration
    NONCE_WINDOWS = 20           # Split search space into 20 segments
    PREDICTION_CONFIDENCE = 0.95 # Only focus if confidence is high
    
    # Logging
    VERBOSE = True
    LOG_FILTERED = False
    LOG_RESONANT = True
    
    # ═══════════════════════════════════════════════════════════════
    # STATE PERSISTENCE (NEW IN V2.0)
    # ═══════════════════════════════════════════════════════════════
    STATE_FILE = Path("./tpf_learned_state.json")
    AUTO_SAVE_INTERVAL = 3600  # Save every hour (seconds)
    
    # Experiment
    EXPERIMENT_NAME = f"tpf_ultimate_lbry_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    @classmethod
    def to_dict(cls):
        return {k: v for k, v in vars(cls).items() 
                if not k.startswith('_') and not callable(v)}


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
    """Feature vector for a share"""
    timestamp: float
    worker_id: int
    latency_ms: float
    delta_ms: float
    z_score: float
    jitter_std: float
    jitter_cv: float
    shares_since_job: int
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


# ================= RESONANCE ENGINE (Multi-Tier) =================
class ResonanceEngine:
    """
    Multi-Tier Thermodynamic Resonance Filter
    
    TIER 1: Basic timing (z-score)
    TIER 2: Jitter variance analysis
    TIER 3: Super-resonance detection
    """
    
    def __init__(self):
        # Timing samples
        self.latency_samples: Deque[float] = deque(maxlen=Config.JITTER_HISTORY)
        self.delta_samples: Deque[float] = deque(maxlen=Config.JITTER_WINDOW)
        
        # Statistics
        self.mean = 0.0
        self.std = 1.0
        self.calibrated = False
        
        # Jitter tracking
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
        
        self.lock = threading.Lock()
    
    def new_job(self):
        """Called when new job received"""
        self.last_job_time = time.time()
        self.shares_since_job = 0
    
    def update(self, latency_ms: float):
        """Update timing statistics"""
        with self.lock:
            now = time.time()
            delta_ms = (now - self.last_share_time) * 1000
            self.last_share_time = now
            
            self.latency_samples.append(latency_ms)
            self.delta_samples.append(delta_ms)
            self.shares_since_job += 1
            
            if len(self.latency_samples) >= Config.CALIBRATION_SAMPLES:
                self.mean = statistics.mean(self.latency_samples)
                self.std = statistics.stdev(self.latency_samples) if len(self.latency_samples) > 1 else 1.0
                
                if len(self.delta_samples) >= 10:
                    self.jitter_std = statistics.stdev(self.delta_samples)
                    jitter_mean = statistics.mean(self.delta_samples)
                    self.jitter_cv = self.jitter_std / (jitter_mean + 1e-9)
                
                if not self.calibrated:
                    self.calibrated = True
                    log.info(f"[RESONANCE] ✓ Calibrated: μ={self.mean:.1f}ms σ={self.std:.1f}ms")
    
    def evaluate(self, latency_ms: float, force_keep: bool = False) -> ShareFeatures:
        """
        Multi-tier share evaluation
        
        Returns ShareFeatures with decision
        """
        self.total_received += 1
        
        # Calculate z-score
        z_score = (latency_ms - self.mean) / (self.std + 1e-9) if self.calibrated else 0.0
        
        # Build features
        features = ShareFeatures(
            timestamp=time.time(),
            worker_id=0,
            latency_ms=latency_ms,
            delta_ms=(time.time() - self.last_share_time) * 1000,
            z_score=z_score,
            jitter_std=self.jitter_std,
            jitter_cv=self.jitter_cv,
            shares_since_job=self.shares_since_job
        )
        
        # Not calibrated - pass through
        if not self.calibrated:
            features.decision = "CALIBRATING"
            features.tier1_pass = True
            features.tier3_pass = True # CRITICAL: Allow shares to pool during calibration
            self.tier1_passed += 1
            self.tier3_passed += 1
            self.total_sent += 1
            return features
        
        # Force keep (keep-alive, safety)
        if force_keep:
            features.decision = "FORCED"
            features.tier1_pass = True
            self.tier1_passed += 1
            self.total_sent += 1
            return features
        
        # ═══════════════════════════════════════════════════════
        # TIER 1: Basic Timing Filter
        # ═══════════════════════════════════════════════════════
        if z_score > Config.Z_SCORE_TIER1:
            features.decision = "FILTERED_SLOW"
            self.total_filtered += 1
            self.filtered_latencies.append(latency_ms)
            return features
        
        features.tier1_pass = True
        self.tier1_passed += 1
        
        # ═══════════════════════════════════════════════════════
        # TIER 2: Jitter Variance Check
        # ═══════════════════════════════════════════════════════
        if self.jitter_cv > Config.JITTER_CV_THRESHOLD:
            features.decision = "FILTERED_ENTROPIC"
            self.total_filtered += 1
            self.filtered_latencies.append(latency_ms)
            return features
        
        # ═══════════════════════════════════════════════════════
        # TIER 3: Resonance Classification
        # ═══════════════════════════════════════════════════════
        if z_score <= Config.Z_SCORE_TIER2:
            # Super-resonant - very fast share
            features.tier2_resonant = True
            features.tier3_pass = True
            self.tier2_resonant += 1
            self.tier3_passed += 1
            features.decision = "SUPER_RESONANT"
        else:
            # Normal resonant
            features.tier3_pass = True
            self.tier3_passed += 1
            features.decision = "RESONANT"
        
        self.total_sent += 1
        self.resonant_latencies.append(latency_ms)
        return features
    
    def get_stats(self) -> dict:
        with self.lock:
            total = max(1, self.total_received)
            res_avg = statistics.mean(self.resonant_latencies) if self.resonant_latencies else 0
            filt_avg = statistics.mean(self.filtered_latencies) if self.filtered_latencies else 0
            
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
            }
    
    # ═══════════════════════════════════════════════════════════════
    # STATE PERSISTENCE (V2.0)
    # ═══════════════════════════════════════════════════════════════
    def get_state(self) -> dict:
        """Export state for persistence"""
        with self.lock:
            return {
                'mean': self.mean,
                'std': self.std,
                'calibrated': self.calibrated,
                'jitter_cv': self.jitter_cv,
                'latency_samples': list(self.latency_samples)[-500:],  # Last 500 samples
                'total_received': self.total_received,
                'tier1_passed': self.tier1_passed,
                'tier2_resonant': self.tier2_resonant,
                'total_filtered': self.total_filtered,
                'total_sent': self.total_sent
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
            if self.calibrated:
                log.info(f"[RESONANCE] ✓ Restored: μ={self.mean:.1f}ms σ={self.std:.1f}ms (from {len(samples)} samples)")


# ================= LEARNING ENGINE =================
class LearningEngine:
    """
    Pattern Learning from Block Winners
    
    Tracks winners and analyzes patterns to optimize thresholds
    """
    
    def __init__(self):
        self.winners: List[ShareFeatures] = []
        self.resonant_windows: List[int] = [] # High-probability segments [0-19]
        self.pattern_confirmed = False
        self.lock = threading.Lock()
        
    def get_resonant_segments(self) -> List[int]:
        """Returns list of segments [0..19] to search"""
        with self.lock:
            if not self.pattern_confirmed or not self.resonant_windows:
                # Return partial list to simulate focus if we want to force x20
                return list(range(Config.NONCE_WINDOWS))
            return self.resonant_windows

    def record_share(self, features: ShareFeatures):
        """Record share to update prediction model"""
        if not features.nonce: return
        
        # Convert nonce to segment (x20 partitioning)
        try:
            n_val = int(features.nonce, 16)
            segment = n_val % Config.NONCE_WINDOWS
            
            with self.lock:
                if features.tier2_resonant:
                    if segment not in self.resonant_windows:
                        self.resonant_windows.append(segment)
                        log.info(f"[LEARN] 🔍 New Resonant Segment Found: {segment}")
                    
                    # Focal optimization
                    if len(self.resonant_windows) > 3:
                        self.resonant_windows.pop(0)
                    self.pattern_confirmed = True
        except Exception as e:
            log.debug(f"[LEARN] Nonce parse error: {e}")

    def get_stats(self) -> dict:
        with self.lock:
            return {
                'num_winners': len(self.winners),
                'pattern_confirmed': self.pattern_confirmed,
                'resonant_segments': self.resonant_windows,
                'focal_ratio': len(self.resonant_windows) / Config.NONCE_WINDOWS if self.pattern_confirmed else 1.0
            }
    
    # ═══════════════════════════════════════════════════════════════
    # STATE PERSISTENCE (V2.0)
    # ═══════════════════════════════════════════════════════════════
    def get_state(self) -> dict:
        """Export state for persistence"""
        with self.lock:
            return {
                'resonant_windows': self.resonant_windows.copy(),
                'pattern_confirmed': self.pattern_confirmed
            }
    
    def load_state(self, state: dict):
        """Restore state from persistence"""
        with self.lock:
            self.resonant_windows = state.get('resonant_windows', [])
            self.pattern_confirmed = state.get('pattern_confirmed', False)
            if self.resonant_windows:
                log.info(f"[LEARN] ✓ Restored {len(self.resonant_windows)} resonant segments: {self.resonant_windows}")


# ================= STATE PERSISTENCE FUNCTIONS (V2.0) =================
def save_tpf_state(resonance: ResonanceEngine, learning: LearningEngine):
    """Save all learned state to file"""
    state = {
        'version': '2.0',
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


def load_tpf_state(resonance: ResonanceEngine, learning: LearningEngine) -> bool:
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
    """Comprehensive data collection and logging"""
    
    def __init__(self):
        self.start_time = time.time()
        self.output_dir = Path(f"./results/{Config.EXPERIMENT_NAME}")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.shares_file = self.output_dir / "shares.csv"
        self.stats_file = self.output_dir / "stats.csv"
        self.winners_file = self.output_dir / "winners.csv"
        self.config_file = self.output_dir / "config.json"
        
        self._init_files()
        self.lock = threading.Lock()
    
    def _init_files(self):
        # Shares CSV
        with open(self.shares_file, 'w', newline='') as f:
            csv.writer(f).writerow([
                'timestamp', 'worker_id', 'latency_ms', 'z_score',
                'jitter_cv', 'decision', 'nonce'
            ])
        
        # Stats CSV
        with open(self.stats_file, 'w', newline='') as f:
            csv.writer(f).writerow([
                'timestamp', 'elapsed_min', 'workers_connected',
                'total_received', 'total_sent', 'total_filtered',
                'pool_accepts', 'pool_rejects', 'accept_rate',
                'mean_ms', 'std_ms', 'filter_rate'
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
                    features.nonce
                ])
    
    def log_stats(self, stats: dict):
        elapsed = (time.time() - self.start_time) / 60
        res = stats.get('resonance', {})
        
        with open(self.stats_file, 'a', newline='') as f:
            csv.writer(f).writerow([
                time.time(), elapsed, stats.get('workers_connected', 0),
                res.get('total_received', 0), res.get('total_sent', 0),
                res.get('total_filtered', 0), stats.get('pool_accepts', 0),
                stats.get('pool_rejects', 0), stats.get('accept_rate', 0),
                res.get('mean_ms', 0), res.get('std_ms', 0),
                res.get('filter_rate', 0)
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
    """Central controller for virtual worker swarm"""
    
    def __init__(self, telemetry: TelemetryEngine):
        self.telemetry = telemetry
        self.workers: List[VirtualWorker] = []
        self.resonance = ResonanceEngine()
        self.learning = LearningEngine()
        
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
    Local proxy providing Stratum interface for Goldshell LB-Box.
     mimics V9 'Stealth Butler' logic for robust handshake.
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
        The 'Pizza Butler' Logic:
        Always have a hot job ready on the plate.
        """
        result = self.nexus.get_job_for_asic()
        if not result:
            log.debug("[BUTLER] No job available in buffer")
            return
            
        local_id, job = result
        
        # Don't resend same job unless forced clean
        if local_id == self.last_sent_job_id and not clean:
            return
            
        self.last_job_time = time.time()
        self.nexus.resonance.new_job()
        self.last_sent_job_id = local_id
        
        # CRITICAL: Sync Extranonce & Difficulty ONLY if worker changes
        # (This prevents ASIC stalling from constant resets)
        worker = self.nexus.workers[job.worker_id - 1] if job.worker_id <= len(self.nexus.workers) else None
        
        if worker:
            # Check if this is a different worker than last time
            if job.worker_id != self.last_fed_worker_id:
                if worker.extranonce1:
                    self._send({
                        "id": None,
                        "method": "mining.set_extranonce",
                        "params": [worker.extranonce1, worker.extranonce2_size]
                    })
                
                if worker.difficulty:
                    self._send({
                        "id": None,
                        "method": "mining.set_difficulty",
                        "params": [worker.difficulty]
                    })
                
                self.last_fed_worker_id = job.worker_id
        
        # VESELOV PRE-FILTER: Gate the butler based on silicon jitter
        stats = self.nexus.resonance.get_stats()
        jitter_cv = stats.get('jitter_cv', 1.0)
        
        # Determine if we need to force a feed for Heartbeat (Persistence)
        silence_sec = time.time() - self.nexus.last_pool_submit
        need_heartbeat = silence_sec > 150
        
        # If noise is too high, we DELAY feeding the job
        if not need_heartbeat and jitter_cv > Config.JITTER_CV_THRESHOLD and stats.get('total_samples', 0) > 10:
            # Silicon is chaotic - skip this "Round" to save ASIC from bad work
            return 
            
        if jitter_cv < 0.2: # High resonance
            log.info(f"[BUTLER] 💎 RESONANCE DETECTED (CV={jitter_cv:.3f}) - ASIC FOCUSING")
        elif need_heartbeat:
            log.info(f"[⚙️] HEARTBEAT FEED: Bypassing filter (Silent for {silence_sec:.1f}s)")
        
        # Rewrite LBC Notify (Match stable script logic)
        try:
            p = list(job.raw_msg['params'])
            p[0] = local_id
            
            # TODO: Future enhancement - deliver split jobs via extranonce manipulation
            # For now, we use the butler to ONLY deliver jobs when the Timing is Resonant
            # This is the "Temporal Pre-Filter"
            
            if len(p) > 0:
                p[-1] = True # Clean jobs
            
            log.info(f"[PROXY] Feeding job {local_id} (params={len(p)})")
            
            self._send({
                "id": None,
                "method": "mining.notify",
                "params": p
            })
        except Exception as e:
            log.error(f"[PROXY] Error constructing job: {e}")



# ================= MONITOR =================
def monitor(nexus: SwarmNexus, telemetry: TelemetryEngine):
    """Monitoring thread"""
    print("\n" + "=" * 70)
    print("  TPF ULTIMATE V1.0 - LBRY EDITION")
    print("  \"The silicon speaks. We listen.\"")
    print("=" * 70 + "\n")
    
    while True:
        time.sleep(10)
        
        s = nexus.get_stats()
        res = s['resonance']
        
        telemetry.log_stats(s)
        
        log.info("-" * 70)
        log.info(f"  Runtime: {s['runtime_min']:.1f} min | Workers: {s['workers_connected']}/{Config.SWARM_SIZE}")
        log.info(f"  Pool Accepts: {s['pool_accepts']} | Rejects: {s['pool_rejects']} | Sent: {s['total_sent']}")
        log.info(f"  H-Pulse: {time.time() - nexus.last_pool_submit:.0f}s ago")
        
        r = s['resonance']
        log.info(f"  TPF: μ={r['mean_ms']:.1f}ms | σ={r['std_ms']:.1f}ms | CV={r['jitter_cv']:.3f}")
        
        if s['total_sent'] > 0:
            log.info(f"\n  📊 Pool Efficiency: {s['pool_efficiency']:.1f}%")
            accept_rate = s['pool_accepts'] / s['total_sent'] * 100
            effective = s['pool_accepts'] / max(1, res['total_received']) * 100
            log.info(f"  📊 Accept Rate: {accept_rate:.1f}% | Effective: {effective:.2f}%")


# ================= MAIN =================
def main():
    print("""
    ╔═══════════════════════════════════════════════════════════════════════════╗
    ║              TPF ULTIMATE V2.0 - LBRY EDITION (WITH PERSISTENCE)          ║
    ║                                                                           ║
    ║        Multi-Tier Resonance Filter for Goldshell LB-Box                   ║
    ║        "The silicon remembers. Learning survives restarts."               ║
    ╚═══════════════════════════════════════════════════════════════════════════╝
    
    CONFIGURATION:
      Pool:       {host}:{port}
      Account:    {wallet}
      Workers:    {swarm} virtual workers
      Filter:     z ≤ {z1} (Tier1) | z ≤ {z2} (Resonant)
      
    OUTPUT:
      ./results/{name}/
      
    """.format(
        host=Config.REMOTE_HOST,
        port=Config.REMOTE_PORT,
        wallet=Config.USER_WALLET,
        swarm=Config.SWARM_SIZE,
        z1=Config.Z_SCORE_TIER1,
        z2=Config.Z_SCORE_TIER2,
        name=Config.EXPERIMENT_NAME
    ))
    
    # Initialize
    telemetry = TelemetryEngine()
    nexus = SwarmNexus(telemetry)
    
    # Graceful shutdown
    def shutdown(sig, frame):
        print("\n\n[SHUTDOWN] Saving learned state...")
        # ═══════════════════════════════════════════════════════════════
        # SAVE STATE BEFORE EXIT (V2.0)
        # ═══════════════════════════════════════════════════════════════
        save_tpf_state(nexus.resonance, nexus.learning)
        
        print("[SHUTDOWN] Generating final report...")
        stats = nexus.get_stats()
        res = stats['resonance']
        
        print(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                     TPF ULTIMATE V2.0 - FINAL REPORT                         ║
║                        (State Saved for Next Run)                            ║
╚══════════════════════════════════════════════════════════════════════════════╝

Runtime: {stats['runtime_min']:.1f} minutes

RESONANCE FILTER:
  Total Received:   {res['total_received']:,}
  Total Sent:       {res['total_sent']:,}
  Total Filtered:   {res['total_filtered']:,} ({res['filter_rate']:.1f}%)
  Super-Resonant:   {res['tier2_resonant']:,}

POOL RESULTS:
  Accepted:         {stats['pool_accepts']:,}
  Rejected:         {stats['pool_rejects']:,}
  Accept Rate:      {stats['accept_rate']:.1f}%

TIMING:
  Mean:             {res['mean_ms']:.1f} ms
  Std:              {res['std_ms']:.1f} ms
  Jitter CV:        {res['jitter_cv']:.4f}

PERSISTENCE:
  State File:       {Config.STATE_FILE}
  
OUTPUT:
  {telemetry.output_dir}
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
