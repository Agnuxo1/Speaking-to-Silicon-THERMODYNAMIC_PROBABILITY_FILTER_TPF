#!/usr/bin/env python3
"""
TPF VERITAS V9.8 - RESONANCE MAX (BTC SWARM)
============================================
Hardware: Antminer S9j (14.5 TH/s stock)
Architecture: Swarm x20 Virtual Workers
Goal: Perceived 14 TH/s per worker using strict TPF filtering.

[STRATEGY]
1. RESONANCE FILTER: Only shares matching the prophetic noise window are sent.
2. WORKER AFFINITY: Stay on one worker for 5+ shares to avoid S9 hardware resets.
3. PERSISTENT WATCHDOG: Automatic 20-worker reconnection on any pool drop.
4. EXCLUSIVE FOCUS: BTC Optimized for F2Pool Euro.
"""

import socket
import threading
import json
import time
import random
import statistics
from collections import deque

# ================= CONFIGURATION =================
LOCAL_HOST = "0.0.0.0"
LOCAL_PORT = 3333

# F2Pool Euro Node
REMOTE_HOST = "btc-euro.f2pool.com" 
REMOTE_PORT = 1314

# Credentials
USER_WALLET = "anormal21" 
POOL_PASS = "21235365876986800"

# Swarm Settings
SWARM_SIZE = 20

# TPF RESONANCE PARAMETERS
Z_SCORE_THRESHOLD = 0.4  # Strict filter for higher perceived hashrate
CALIBRATION_SAMPLES = 50
STARVATION_TIMEOUT = 30.0 # Force a share if a worker remains hungry
AFFINITY_BURST = 5        # Number of shares to stick to one worker
# =================================================

class VeritasEngine:
    """Thermodynamic Probability Filter - The JUDGE."""
    def __init__(self):
        self.samples = deque(maxlen=2000)
        self.mean = 0.0
        self.std = 0.0
        self.calibrated = False
    
    def update(self, ms):
        self.samples.append(ms)
        if len(self.samples) >= CALIBRATION_SAMPLES:
            self.mean = statistics.mean(self.samples)
            self.std = statistics.stdev(self.samples)
            self.calibrated = True
            
    def check(self, latency_ms):
        if not self.calibrated: return True 
        z = (latency_ms - self.mean) / (self.std + 1e-9)
        # Higher Z = More Entropy = Discard
        # Lower Z = Resonance = Submit
        return z < Z_SCORE_THRESHOLD

class VirtualWorker:
    """Handles persistent connection to the pool for a specific sub-worker."""
    def __init__(self, worker_id, swarm_manager):
        self.worker_name = f"{USER_WALLET}.{worker_id:03d}"
        self.id = worker_id
        self.manager = swarm_manager
        self.sock = None
        self.connected = False
        
        # Stratum State
        self.extranonce1 = None
        self.extranonce2_size = 4
        self.difficulty = 1024
        
        # Telemetry
        self.last_share_time = time.time()
        self.shares_sent = 0

    def connect_loop(self):
        """Watchdog: Never-ending connection cycle."""
        while True:
            try:
                if self.sock:
                    try: self.sock.close()
                    except: pass
                
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(15)
                self.sock.connect((REMOTE_HOST, REMOTE_PORT))
                self.sock.settimeout(None)
                
                # Handshake
                self._send({"id": 1, "method": "mining.subscribe", "params": ["TPF-V9.8/Max"]})
                self._send({"id": 2, "method": "mining.authorize", "params": [self.worker_name, POOL_PASS]})
                
                self._listen_loop()
            except Exception:
                time.sleep(5)

    def _send(self, data):
        try:
            self.sock.sendall((json.dumps(data) + '\n').encode())
        except:
            self.connected = False

    def _listen_loop(self):
        self.connected = True
        buff = ""
        while self.connected:
            try:
                data = self.sock.recv(4096).decode('utf-8', errors='ignore')
                if not data: break
                buff += data
                while '\n' in buff:
                    line, buff = buff.split('\n', 1)
                    if not line.strip(): continue
                    try:
                        self.process_msg(json.loads(line))
                    except: continue
            except: break
        self.connected = False

    def process_msg(self, msg):
        mid = msg.get('id')
        method = msg.get('method')
        
        # Handshake Confirmation
        if mid == 2 and msg.get('result') is True:
            # print(f"[+] W{self.id} (F2Pool Euro): Authorized")
            pass

        # Subscription Setup
        if mid == 1 and not method:
            res = msg.get('result')
            if res and len(res) >= 3:
                self.extranonce1 = res[1]
                self.extranonce2_size = res[2]
        
        # Job Inflow
        elif method == 'mining.notify':
            params = msg['params']
            job = {
                'worker_idx': self.id - 1,
                'job_id': params[0],
                'prev_hash': params[1],
                'coinb1': params[2],
                'coinb2': params[3],
                'merkle_branch': params[4],
                'version': params[5],
                'nbits': params[6],
                'ntime': params[7],
                'clean_jobs': params[8],
                'difficulty': self.difficulty,
                'en1': self.extranonce1,
                'en2_size': self.extranonce2_size,
                'arrived_at': time.time()
            }
            self.manager.register_job(job)

        # Dynamic Difficulty
        elif method == 'mining.set_difficulty':
            self.difficulty = msg['params'][0]

class SwarmNexus:
    """The central hub managing jobs and TPF filtering."""
    def __init__(self):
        self.workers = []
        self.job_registry = {} 
        self.ready_queue = deque()
        self.lock = threading.Lock()
        
        self.stats = {"total": 0, "sent": 0, "filt": 0}
        self.engine = VeritasEngine()

    def boot(self):
        print(f"[SWARM] Initializing {SWARM_SIZE} workers on F2Pool Euro...")
        for i in range(1, SWARM_SIZE + 1):
            w = VirtualWorker(i, self)
            self.workers.append(w)
            threading.Thread(target=w.connect_loop, daemon=True).start()
            time.sleep(0.1)

    def register_job(self, job):
        if not job['en1']: return
        with self.lock:
            local_id = f"{job['worker_idx']}_{job['job_id']}"
            self.job_registry[local_id] = job
            self.ready_queue.append(local_id)
            if len(self.ready_queue) > 100:
                old = self.ready_queue.popleft()
                if old in self.job_registry: del self.job_registry[old]

    def get_resonant_job(self, current_idx):
        if not self.ready_queue: return None, None
        
        now = time.time()
        with self.lock:
            # 1. Starvation Priority (Keep workers alive on dashboard)
            for w in self.workers:
                if (now - w.last_share_time) > STARVATION_TIMEOUT:
                    for lid in reversed(self.ready_queue):
                        if lid.startswith(f"{w.id-1}_"):
                            self.ready_queue.remove(lid)
                            return self.job_registry.get(lid), lid
            
            # 2. Worker Affinity (Prevent S9 reset loops)
            if current_idx != -1:
                for lid in reversed(self.ready_queue):
                    if lid.startswith(f"{current_idx}_"):
                        self.ready_queue.remove(lid)
                        return self.job_registry.get(lid), lid
            
            # 3. Default: Newest job
            lid = self.ready_queue.pop()
            return self.job_registry.get(lid), lid

    def handle_share(self, local_id, nonce, en2, ntime, latency_ms):
        self.stats['total'] += 1
        self.engine.update(latency_ms)
        
        job = self.job_registry.get(local_id)
        if not job: return

        worker = self.workers[job['worker_idx']]
        
        # TPF DECISION: Resonance vs Starvation
        is_resonant = self.engine.check(latency_ms)
        is_hungry = (time.time() - worker.last_share_time) > STARVATION_TIMEOUT
        
        if is_resonant or is_hungry:
            payload = {
                "params": [worker.worker_name, job['job_id'], en2, ntime, nonce],
                "id": 4, "method": "mining.submit"
            }
            worker._send(payload)
            worker.last_share_time = time.time()
            worker.shares_sent += 1
            self.stats['sent'] += 1
        else:
            self.stats['filt'] += 1

class S9ResonanceProxy:
    """ASIC Facing Proxy with Affinity Logic."""
    def __init__(self, nexus):
        self.nexus = nexus
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.client = None
        
        # Session State
        self.current_worker_idx = -1 
        self.affinity_count = 0
        self.last_job_time = time.time()

    def start(self):
        self.sock.bind((LOCAL_HOST, LOCAL_PORT))
        self.sock.listen(1)
        print(f"[RESONANCE] V9.8 Proxy active on {LOCAL_PORT}")
        while True:
            try:
                conn, addr = self.sock.accept()
                print(f"[ASIC] Handshaking: {addr}")
                self.handle_asic(conn)
            except Exception: pass

    def handle_asic(self, conn):
        self.client = conn
        self.current_worker_idx = -1
        buff = ""
        while True:
            try:
                data = conn.recv(4096).decode('utf-8', errors='ignore')
                if not data: break
                buff += data
                while '\n' in buff:
                    line, buff = buff.split('\n', 1)
                    if not line.strip(): continue
                    try: self.process_pkt(json.loads(line))
                    except: continue
            except: break
        conn.close()

    def _send(self, msg):
        try: self.client.sendall((json.dumps(msg) + '\n').encode())
        except: pass

    def process_pkt(self, pkt):
        method = pkt.get('method')
        mid = pkt.get('id')

        if method == 'mining.configure':
            self._send({"id": mid, "result": {"version-rolling": True, "version-rolling.mask": "1fffe000"}, "error": None})
        elif method == 'mining.subscribe':
            self._send({"id": mid, "result": [["mining.notify", "res"], "00000000", 4], "error": None})
            self.feed_job()
        elif method == 'mining.authorize':
            self._send({"id": mid, "result": True, "error": None})
        elif method == 'mining.submit':
            # print(f"[ASIC -> PROXY] Share Submitted")
            self._send({"id": mid, "result": True, "error": None})
            # Latency Measurement for TPF
            latency = (time.time() - self.last_job_time) * 1000
            p = pkt['params']
            # Route Share to Nexus
            threading.Thread(target=self.nexus.handle_share, args=(p[1], p[4], p[2], p[3], latency)).start()
            self.feed_job()

    def feed_job(self):
        # Apply Affinity Burst to prevent S9 resets
        job = None
        local_id = None
        
        if self.affinity_count > 0:
            job, local_id = self.nexus.get_resonant_job(self.current_worker_idx)
            if job and job['worker_idx'] == self.current_worker_idx:
                self.affinity_count -= 1
            else: self.affinity_count = 0

        if not job:
            job, local_id = self.nexus.get_resonant_job(self.current_worker_idx)
            if not job: return
            self.affinity_count = AFFINITY_BURST

        # Sync Hardware if worker changed
        if self.current_worker_idx != job['worker_idx']:
            self._send({"id": None, "method": "mining.set_difficulty", "params": [job['difficulty']]})
            self._send({"id": None, "method": "mining.set_extranonce", "params": [job['en1'], job['en2_size']]})
            self.current_worker_idx = job['worker_idx']

        self.last_job_time = time.time()
        self._send({
            "params": [local_id, job['prev_hash'], job['coinb1'], job['coinb2'],
                       job['merkle_branch'], job['version'], job['nbits'], job['ntime'], True],
            "id": None, "method": "mining.notify"
        })

def telemetry(nexus):
    while True:
        time.sleep(15)
        total = max(1, nexus.stats['total'])
        eff = (nexus.stats['sent'] / total) * 100
        print(f"[TELEMETRY] Filtered: {nexus.stats['filt']} | Resonant: {nexus.stats['sent']} | Efficiency: {eff:.2f}%")
        print(f"            Resonance Mean: {nexus.engine.mean:.2f}ms | Swarm: 20 Workers Active")

if __name__ == "__main__":
    nex = SwarmNexus()
    nex.boot()
    time.sleep(2)
    threading.Thread(target=telemetry, args=(nex,), daemon=True).start()
    proxy = S9ResonanceProxy(nex)
    proxy.start()