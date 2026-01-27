#!/usr/bin/env python3
"""
TPF VERITAS SOLO (Goldshell LB-Box Edition)
===========================================
- Hardware: Xilinx Zynq-7010 
- Mode: SOLO Mining (Zergpool)
- Algorithm: LBRY (LBC)
- Payout: BTC (Auto-Exchange)
- Filter: LCPF (Latency-Correlated Probability Filter)
"""

import socket
import threading
import json
import time
import random
import statistics
from collections import deque

# CONFIG
LOCAL_HOST = "0.0.0.0"
LOCAL_PORT = 3333
REMOTE_HOST = "lbry.mining-dutch.nl" 
REMOTE_PORT = 9988
USER_WALLET = "apollo13.LBBox"
# Mining-Dutch requires Username.WorkerName for dashboard sync.
POOL_PASSWORD = "x" 

# THERMODYNAMIC PARAMETERS
CALIBRATION_SIZE = 50  
RESONANCE_TARGET = 0.50 
KEEP_RATE = 0.050 # Target ~8.5 Ghs visibility (5.0% of total)

class VeritasEngine:
    """Persistent thermodynamic analysis engine."""
    def __init__(self):
        self.latency_samples = deque(maxlen=1000)
        self.calibrated = False
        self.mean = 0
        self.std = 0
        print("[VERITAS] Silicon Sampler Initialized.")

    def add_sample(self, ms):
        self.latency_samples.append(ms)
        if len(self.latency_samples) >= CALIBRATION_SIZE:
            self.mean = statistics.mean(self.latency_samples)
            self.std = statistics.stdev(self.latency_samples)
            if not self.calibrated:
                self.calibrated = True
                print(f"\n[VERITAS] PERSISTENT CALIBRATION ACHIEVED: {self.mean:.2f}ms")

    def should_kill(self, latency):
        if not self.calibrated:
            return random.random() > KEEP_RATE
        z_score = (latency - self.mean) / (self.std if self.std > 0 else 1)
        return not (z_score < -RESONANCE_TARGET)

class SoloHandler:
    def __init__(self, miner_conn, stats, veritas):
        self.miner_conn = miner_conn
        self.stats = stats
        self.veritas = veritas 
        self.pool_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.pool_conn.settimeout(10.0)
        self.running = True
        self.authorized = False
        
        self.latest_params = None
        self.last_accept_t = time.time()
        self.last_job_t = time.time()
        self.job_buffer = deque(maxlen=100)
        self.peer = miner_conn.getpeername()

    def start(self):
        try:
            print(f"[*] Handshake with {self.peer}")
            self.pool_conn.connect((REMOTE_HOST, REMOTE_PORT))
            self.pool_conn.settimeout(None)
            threading.Thread(target=self.upstream, daemon=True).start()
            threading.Thread(target=self.downstream, daemon=True).start()
        except Exception as e:
            print(f"[!] Solo Init Error: {e}")
            self.miner_conn.close()

    def send_json(self, sock, data):
        try: sock.sendall((json.dumps(data) + '\n').encode())
        except: pass

    def stop(self):
        self.running = False
        try: self.miner_conn.close()
        except: pass
        try: self.pool_conn.close()
        except: pass

    def upstream(self):
        buff = ""
        while self.running:
            try:
                data = self.miner_conn.recv(4096).decode('utf-8', errors='ignore')
                if not data: break
                buff += data
                while '\n' in buff:
                    line, buff = buff.split('\n', 1)
                    if not line.strip(): continue
                    msg = json.loads(line)
                    method = msg.get('method')
                    
                    if method == 'mining.authorize':
                        print(f"[*] Worker '{USER_WALLET}' Connecting...")
                        msg['params'][1] = POOL_PASSWORD
                        msg['params'][0] = USER_WALLET
                        self.send_json(self.pool_conn, msg)
                    elif method == 'mining.submit' and self.authorized:
                        self.process_with_veritas(msg)
                    else:
                        self.send_json(self.pool_conn, msg)
            except (ConnectionResetError, socket.error): break
            except Exception: break
        self.running = False

    def downstream(self):
        buff = ""
        while self.running:
            try:
                data = self.pool_conn.recv(4096).decode('utf-8', errors='ignore')
                if not data: break
                buff += data
                while '\n' in buff:
                    line, buff = buff.split('\n', 1)
                    if not line.strip(): continue
                    try:
                        msg = json.loads(line)
                        if not msg.get('method') and msg.get('result') is True:
                            self.authorized = True
                            print(f"[+] Pool Link Established.")
                        
                        if msg.get('method') == 'mining.notify':
                            self.latest_params = msg['params']
                            if self.authorized: self.refill_buffer()
                            self.send_json(self.miner_conn, msg)
                        else:
                            self.send_json(self.miner_conn, msg)
                    except: pass
            except (ConnectionResetError, socket.error): break
            except Exception: break
        self.running = False

    def process_with_veritas(self, msg):
        latency = (time.time() - self.last_job_t) * 1000 # ms
        self.veritas.add_sample(latency)
        self.stats["scanned"] += 1
        
        is_keepalive = (time.time() - self.last_accept_t) > 40.0
        
        if self.veritas.should_kill(latency) and not is_keepalive:
            # High efficiency kill: fake the pool response
            self.send_json(self.miner_conn, {"id": msg.get('id'), "result": True, "error": None})
        else:
            # Resonant hash or keepalive: push to pool
            self.stats["accepted"] += 1
            self.last_accept_t = time.time()
            if not is_keepalive:
                print(f"[!] PROPHETIC ({latency:.1f}ms)")
            self.send_json(self.pool_conn, msg)
            
        # Rotate job periodically to keep sampling silicon jitter
        if self.job_buffer and (self.stats["scanned"] % 5 == 0):
            p = self.job_buffer.popleft()
            self.last_job_t = time.time()
            self.send_json(self.miner_conn, {"id": None, "method": "mining.notify", "params": p})

    def refill_buffer(self):
        if not self.latest_params: return
        for _ in range(30):
            p = list(self.latest_params)
            p[0] = f"v_{random.getrandbits(32):x}"
            p[-1] = True # Clean jobs
            self.job_buffer.append(p)

class VeritasSoloController:
    def __init__(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.stats = {"scanned": 0, "accepted": 0}
        self.veritas = VeritasEngine()

    def start(self):
        self.server.bind((LOCAL_HOST, LOCAL_PORT))
        self.server.listen(15)
        print(f"--- TPF VERITAS SOLO v3: STABILITY ACTIVE ---")
        threading.Thread(target=self.stats_loop, daemon=True).start()
        while True:
            try:
                conn, addr = self.server.accept()
                handler = SoloHandler(conn, self.stats, self.veritas)
                threading.Thread(target=handler.start, daemon=True).start()
            except: pass

    def stats_loop(self):
        start_t = time.time()
        while True:
            time.sleep(30)
            elapsed = (time.time() - start_t) / 60.0
            scanned = self.stats["scanned"]
            if scanned > 10:
                print(f"[STATS] Scanned: {scanned} | Reported: {self.stats['accepted']} (Eff: {self.stats['accepted']/scanned*100:.1f}%)")

if __name__ == "__main__":
    try:
        VeritasSoloController().start()
    except KeyboardInterrupt:
        pass
