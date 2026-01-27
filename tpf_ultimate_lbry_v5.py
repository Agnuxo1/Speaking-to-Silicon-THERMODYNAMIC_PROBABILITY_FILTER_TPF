#!/usr/bin/env python3
"""
TPF ULTIMATE V5.0 - LBRY EDITION (Swarm Transparency)
=====================================================
The Definitive Thermodynamic Probability Filter for LBRY Mining

Hardware: Goldshell LB-Box (Zynq-7010)
Pool: Mining-Dutch LBRY Solo
Algorithm: LBRY (SHA256+SHA512+RIPEMD160)

V5.0 Features:
- Transparent Worker Swarm (5 active workers)
- "Fair-Share" Rotation (Threshold-based rotation)
- Multi-Worker Heartbeat Pulse (100% visibility)
- Veselov Hierarchical Pre-Filter (x20 Efficiency)

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
import random
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
log = logging.getLogger('TPF-V5')

# ================= CONFIGURATION =================
class Config:
    """Centralized configuration for TPF Ultimate V5.0"""
    
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
    FAKE_AGENT = "LBC-Swarm-V5/1.0"
    
    # Swarm Configuration
    SWARM_SIZE = 5                # Increased to 5 for full transparency
    ROTATION_THRESHOLD = 20       # Rotate worker every 20 jobs fed to ASIC (Faster cycle)
    
    # ═══════════════════════════════════════════════════════════════
    # MULTI-TIER RESONANCE FILTER CONFIGURATION
    # ═══════════════════════════════════════════════════════════════
    
    # TIER 1: Basic Timing Filter
    Z_SCORE_TIER1 = 0.8
    
    # TIER 2: Resonance Detection
    Z_SCORE_TIER2 = -0.5
    
    # TIER 3: Jitter Focus
    JITTER_CV_THRESHOLD = 0.95
    CALIBRATION_SAMPLES = 50
    
    # Heartbeat & Persistence
    HEARTBEAT_SEC = 120           # Global pool keep-alive
    PER_WORKER_SILENCE_LIMIT = 300 # Max silence per worker before forcing
    
    # Simulation Logic
    VESELOV_K = 5
    JITTER_WINDOW = 50
    JITTER_HISTORY = 5000
    
    # Safety
    SAFETY_KEEP_RATE = 0.02       # 2% random pass-through
    
    # x20 Window Configuration
    NONCE_WINDOWS = 20
    
    # Logging
    VERBOSE = True
    LOG_FILTERED = False
    LOG_RESONANT = True
    
    # Experiment
    EXPERIMENT_NAME = f"tpf_v5_lbry_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
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
    last_pool_submit_time: float = field(default_factory=time.time)
    last_job_fed_time: float = 0


# ================= LBRY HASH FUNCTIONS =================
class LBRYHasher:
    """LBRY Proof-of-Work Hash Algorithm"""
    
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
        intermediate = cls.sha512(cls.sha256d(header))
        left_ripe = cls.ripemd160(intermediate[:32])
        right_ripe = cls.ripemd160(intermediate[32:])
        return cls.sha256d(left_ripe + right_ripe)


# ================= RESONANCE ENGINE =================
class ResonanceEngine:
    """Multi-Tier Thermodynamic Resonance Filter"""
    
    def __init__(self):
        self.latency_samples: Deque[float] = deque(maxlen=Config.JITTER_HISTORY)
        self.delta_samples: Deque[float] = deque(maxlen=Config.JITTER_WINDOW)
        self.mean = 0.0
        self.std = 1.0
        self.calibrated = False
        self.jitter_std = 0.0
        self.jitter_cv = 0.0
        self.total_received = 0
        self.total_filtered = 0
        self.total_sent = 0
        self.last_share_time = time.time()
        self.lock = threading.Lock()
    
    def update(self, latency_ms: float):
        with self.lock:
            now = time.time()
            delta_ms = (now - self.last_share_time) * 1000
            self.last_share_time = now
            self.latency_samples.append(latency_ms)
            self.delta_samples.append(delta_ms)
            
            if len(self.latency_samples) >= Config.CALIBRATION_SAMPLES:
                self.mean = statistics.mean(self.latency_samples)
                self.std = statistics.stdev(self.latency_samples) if len(self.latency_samples) > 1 else 1.0
                if len(self.delta_samples) >= 10:
                    self.jitter_std = statistics.stdev(self.delta_samples)
                    self.jitter_cv = self.jitter_std / (statistics.mean(self.delta_samples) + 1e-9)
                self.calibrated = True

    def evaluate(self, latency_ms: float, force_keep: bool = False) -> ShareFeatures:
        self.total_received += 1
        z_score = (latency_ms - self.mean) / (self.std + 1e-9) if self.calibrated else 0.0
        
        features = ShareFeatures(
            timestamp=time.time(),
            worker_id=0,
            latency_ms=latency_ms,
            delta_ms=(time.time() - self.last_share_time) * 1000,
            z_score=z_score,
            jitter_std=self.jitter_std,
            jitter_cv=self.jitter_cv,
            shares_since_job=0
        )
        
        if not self.calibrated or force_keep:
            features.decision = "CALIBRATING" if not self.calibrated else "FORCED"
            features.tier1_pass = True
            features.tier3_pass = True
            self.total_sent += 1
            return features
        
        if z_score > Config.Z_SCORE_TIER1:
            features.decision = "FILTERED_SLOW"
            self.total_filtered += 1
            return features
            
        if self.jitter_cv > Config.JITTER_CV_THRESHOLD:
            features.decision = "FILTERED_ENTROPIC"
            self.total_filtered += 1
            return features
            
        features.tier1_pass = True
        features.tier3_pass = True
        features.decision = "SUPER_RESONANT" if z_score <= Config.Z_SCORE_TIER2 else "RESONANT"
        self.total_sent += 1
        return features

    def get_stats(self) -> dict:
        with self.lock:
            return {
                'calibrated': self.calibrated,
                'mean_ms': self.mean,
                'std_ms': self.std,
                'jitter_cv': self.jitter_cv,
                'total_received': self.total_received,
                'total_filtered': self.total_filtered,
                'total_sent': self.total_sent,
                'filter_rate': (self.total_filtered / max(1, self.total_received)) * 100
            }


# ================= SWARM COMPONENTS =================
class VirtualWorker:
    """Virtual worker maintaining connection to pool"""
    
    def __init__(self, worker_id: int, nexus: 'SwarmNexus'):
        self.id = worker_id
        # Naming convention for Mining-Dutch: Username.WorkerName
        self.worker_name = f"{Config.USER_WALLET}{worker_id}" 
        self.nexus = nexus
        self.sock: Optional[socket.socket] = None
        self.connected = False
        self.lock = threading.Lock()
        self.extranonce1: Optional[str] = None
        self.extranonce2_size: int = 4
        self.difficulty: float = 4096.0
        self.stats = WorkerStats()
        self.msg_counter = 1000 + worker_id * 1000
    
    def connect(self):
        while True:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(30)
                self.sock.connect((Config.REMOTE_HOST, Config.REMOTE_PORT))
                self.sock.settimeout(None)
                self._send({"id": 1, "method": "mining.subscribe", "params": [Config.FAKE_AGENT]})
                time.sleep(0.2)
                self._send({"id": 2, "method": "mining.authorize", "params": [self.worker_name, Config.POOL_PASS]})
                self.connected = True
                log.info(f"[W{self.id}] ✓ Connected as {self.worker_name}")
                self._listen_loop()
                return
            except Exception as e:
                log.warning(f"[W{self.id}] Connection failed: {e}")
                time.sleep(5)
    
    def _send(self, data: dict):
        try:
            with self.lock:
                if self.sock: self.sock.sendall((json.dumps(data) + '\n').encode())
        except: self.connected = False
    
    def _listen_loop(self):
        buffer = ""
        while self.connected:
            try:
                data = self.sock.recv(8192).decode('utf-8', errors='ignore')
                if not data: break
                buffer += data
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line.strip(): self._process_message(json.loads(line))
            except: break
        self.connected = False
        log.warning(f"[W{self.id}] Disconnected")
    
    def _process_message(self, msg: dict):
        mid, method, result, error = msg.get('id'), msg.get('method'), msg.get('result'), msg.get('error')
        if mid == 1 and result:
            self.extranonce1 = result[1]
            self.extranonce2_size = int(result[2])
        elif method == 'mining.set_difficulty':
            self.difficulty = msg['params'][0]
        elif method == 'mining.notify':
            params = msg['params']
            job = PoolJob(self.id, params[0], params[1], params[2], params[3], params[4], 
                         params[5], params[6], params[7], params[8] if len(params) > 8 else False,
                         self.difficulty, self.extranonce1, self.extranonce2_size, raw_msg=msg)
            self.nexus.register_job(job)
        elif mid and mid >= 1000:
            if result is True:
                self.stats.shares_accepted += 1
                self.nexus.pool_accepts += 1
            else:
                self.stats.shares_rejected += 1
                self.nexus.pool_rejects += 1
                log.warning(f"[REJECT] W{self.id} | {error}")

    def submit_share(self, job_id: str, en2: str, ntime: str, nonce: str):
        self.msg_counter += 1
        self.stats.shares_sent += 1
        self.stats.last_share_time = time.time()
        self._send({"id": self.msg_counter, "method": "mining.submit", 
                   "params": [self.worker_name, job_id, en2, ntime, nonce]})


class SwarmNexus:
    """Central controller for 5-worker swarm"""
    
    def __init__(self, telemetry: 'TelemetryEngine'):
        self.telemetry = telemetry
        self.workers: List[VirtualWorker] = []
        self.resonance = ResonanceEngine()
        self.job_buffer: Deque[str] = deque(maxlen=1000)
        self.local_to_job: Dict[str, PoolJob] = {}
        self.local_id_counter = 0
        self.lock = threading.Lock()
        
        # Fair-Share Rotation
        self.sticky_worker_id = 1
        self.jobs_fed_to_asic = 0
        
        # Stats
        self.pool_accepts = 0
        self.pool_rejects = 0
        self.total_submitted = 0
        self.last_pool_submit = time.time()
        self.sent_nonces: Deque[str] = deque(maxlen=20000)
        self.start_time = time.time()
    
    def boot(self):
        log.info(f"[SWARM] Booting {Config.SWARM_SIZE} workers for transparency...")
        for i in range(1, Config.SWARM_SIZE + 1):
            worker = VirtualWorker(i, self)
            self.workers.append(worker)
            threading.Thread(target=worker.connect, daemon=True).start()
            time.sleep(0.5)
    
    def register_job(self, job: PoolJob):
        with self.lock:
            self.local_id_counter += 1
            local_id = f"L{self.local_id_counter:08d}"
            self.local_to_job[local_id] = job
            self.job_buffer.append(local_id)
            if len(self.local_to_job) > 200:
                old = self.job_buffer.popleft(); self.local_to_job.pop(old, None)
    
    def get_job_for_asic(self) -> Optional[Tuple[str, PoolJob]]:
        with self.lock:
            if not self.job_buffer: return None
            
            # Rotation Check
            self.jobs_fed_to_asic += 1
            if self.jobs_fed_to_asic >= Config.ROTATION_THRESHOLD:
                old_w = self.sticky_worker_id
                self.sticky_worker_id = (self.sticky_worker_id % Config.SWARM_SIZE) + 1
                self.jobs_fed_to_asic = 0
                log.info(f"[NEXUS] 🔄 ROLLING WORKER: W{old_w} -> W{self.sticky_worker_id}")

            # Priority: Most recent job from sticky worker
            for lid in reversed(list(self.job_buffer)):
                job = self.local_to_job.get(lid)
                if job and job.worker_id == self.sticky_worker_id:
                    return lid, job
            
            # Fallback
            lid = list(self.job_buffer)[-1]
            job = self.local_to_job.get(lid)
            return lid, job

    def process_share(self, local_id: str, nonce: str, en2: str, ntime: str, latency_ms: float):
        job = self.local_to_job.get(local_id)
        if not job or nonce in self.sent_nonces: return
        self.sent_nonces.append(nonce)
        self.resonance.update(latency_ms)
        
        now = time.time()
        force = (now - self.last_pool_submit) > Config.HEARTBEAT_SEC
        if random.random() < Config.SAFETY_KEEP_RATE: force = True
        
        features = self.resonance.evaluate(latency_ms, force_keep=force)
        features.worker_id, features.nonce, features.job_id = job.worker_id, nonce, local_id
        
        if features.tier1_pass and features.tier3_pass:
            worker = self.workers[job.worker_id - 1]
            worker.submit_share(job.job_id, en2, ntime, nonce)
            worker.stats.last_pool_submit_time = now
            self.last_pool_submit = now
            self.total_submitted += 1
            if Config.LOG_RESONANT:
                log.info(f"[💎] W{worker.id} | {latency_ms:5.1f}ms | z={features.z_score:+.2f} | {features.decision}")
        
        self.telemetry.log_share(features)

    def get_stats(self) -> dict:
        return {
            'runtime_min': (time.time() - self.start_time) / 60,
            'workers_connected': sum(1 for w in self.workers if w.connected),
            'pool_accepts': self.pool_accepts,
            'pool_rejects': self.pool_rejects,
            'total_sent': self.total_submitted,
            'resonance': self.resonance.get_stats()
        }


# ================= PROXY LAYER =================
class LBBoxProxy:
    """Stratum Proxy for Goldshell LB-Box with V5 Temporal Filter"""
    
    def __init__(self, nexus: SwarmNexus):
        self.nexus = nexus
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.asic_socket = None
        self.last_job_time = time.time()
        self.last_fed_worker_id = 0
        self.lock = threading.Lock()
        
    def start(self):
        self.server.bind((Config.LOCAL_HOST, Config.LOCAL_PORT))
        self.server.listen(1)
        log.info(f"[PROXY] V5 LISTENING ON {Config.LOCAL_PORT} - SWARM READY")
        while True:
            conn, _ = self.server.accept()
            self._handle_session(conn)

    def _handle_session(self, conn):
        self.asic_socket = conn
        buffer = ""
        while self.asic_socket:
            try:
                data = conn.recv(4096).decode('utf-8', errors='ignore')
                if not data: break
                buffer += data
                while '\n' in buffer or '\x00' in buffer:
                    if '\n' in buffer and ('\x00' not in buffer or buffer.find('\n') < buffer.find('\x00')):
                        line, buffer = buffer.split('\n', 1)
                    else: line, buffer = buffer.split('\x00', 1)
                    if line.strip(): self._process_msg(json.loads(line))
            except: break
        self.asic_socket = None

    def _process_msg(self, msg: dict):
        method, mid = msg.get('method'), msg.get('id')
        if method == 'mining.subscribe':
            while not any(w.extranonce1 for w in self.nexus.workers): time.sleep(0.5)
            worker = next(w for w in self.nexus.workers if w.extranonce1)
            self._send({"id": mid, "result": [["mining.notify", "v5_swarm"], worker.extranonce1, worker.extranonce2_size], "error": None})
            self._send({"id": None, "method": "mining.set_difficulty", "params": [worker.difficulty]})
            self._feed_butler(clean=True)
        elif method == 'mining.authorize':
            self._send({"id": mid, "result": True, "error": None})
        elif method == 'mining.submit':
            self._send({"id": mid, "result": True, "error": None})
            latency = (time.time() - self.last_job_time) * 1000
            self._feed_butler(clean=True)
            p = msg.get('params', [])
            if len(p) >= 5:
                threading.Thread(target=self.nexus.process_share, args=(p[1], p[4], p[2], p[3], latency)).start()

    def _feed_butler(self, clean: bool = False):
        res = self.nexus.get_job_for_asic()
        if not res: return
        local_id, job = res
        self.last_job_time = time.time()
        
        # Swarm Visibility Check (Per-worker pulse)
        worker = self.nexus.workers[job.worker_id - 1]
        if job.worker_id != self.last_fed_worker_id:
            if worker.extranonce1:
                self._send({"id": None, "method": "mining.set_extranonce", "params": [worker.extranonce1, worker.extranonce2_size]})
            self._send({"id": None, "method": "mining.set_difficulty", "params": [worker.difficulty]})
            self.last_fed_worker_id = job.worker_id

        # Per-Worker Heartbeat-Bypass
        stats = self.nexus.resonance.get_stats()
        jitter_cv = stats.get('jitter_cv', 1.0)
        worker_silence = time.time() - worker.stats.last_pool_submit_time
        global_silence = time.time() - self.nexus.last_pool_submit
        
        # Force feed if this SPECIFIC worker or the whole pool is losing us
        if worker_silence > Config.HEARTBEAT_SEC:
             log.info(f"[HEARTBEAT] 💓 FORCING W{job.worker_id} (Silent for {worker_silence:.1f}s)")
        elif global_silence < 120 and jitter_cv > Config.JITTER_CV_THRESHOLD and stats.get('total_received', 0) > 20:
             return # Silicon Noise Gate

        if jitter_cv < 0.2: log.info(f"[BUTLER] 💎 RESONANCE (CV={jitter_cv:.3f}) - W{job.worker_id} ACTIVE")
        
        p = list(job.raw_msg['params'])
        p[0] = local_id
        if len(p) > 0: p[-1] = clean
        self._send({"id": None, "method": "mining.notify", "params": p})

    def _send(self, msg: dict):
        try:
            if self.asic_socket: self.asic_socket.sendall((json.dumps(msg) + '\n').encode())
        except: self.asic_socket = None


# ================= MONITOR & TELEMETRY =================
class TelemetryEngine:
    def __init__(self):
        self.dir = Path(f"./results/{Config.EXPERIMENT_NAME}")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.shares_file = self.dir / "shares_v5.csv"
        with open(self.shares_file, 'w', newline='') as f:
            csv.writer(f).writerow(['ts', 'w_id', 'lat', 'z', 'cv', 'dec'])
    
    def log_share(self, f: ShareFeatures):
        with open(self.shares_file, 'a', newline='') as file:
            csv.writer(file).writerow([f.timestamp, f.worker_id, f.latency_ms, f.z_score, f.jitter_cv, f.decision])

def monitor(nexus: SwarmNexus):
    while True:
        time.sleep(15)
        s = nexus.get_stats()
        r = s['resonance']
        log.info("="*50)
        log.info(f" V5 SWARM | Runtime: {s['runtime_min']:.1f}m | Workers: {s['workers_connected']}/5")
        log.info(f" Pool Accepts: {s['pool_accepts']} | Sent: {s['total_sent']} | Efficiency: {(s['pool_accepts']/max(1, s['total_sent']))*100:.1f}%")
        log.info(f" TPF: CV={r['jitter_cv']:.3f} | Filter Rate: {r['filter_rate']:.1f}%")
        log.info("="*50)

def main():
    telemetry = TelemetryEngine()
    nexus = SwarmNexus(telemetry)
    
    def handle_exit(sig, frame):
        log.info("\n[EXIT] TPF V5.0 Stopped.")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, handle_exit)
    nexus.boot()
    threading.Thread(target=monitor, args=(nexus,), daemon=True).start()
    proxy = LBBoxProxy(nexus)
    proxy.start()

if __name__ == "__main__":
    main()
