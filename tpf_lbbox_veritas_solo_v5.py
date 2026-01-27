#!/usr/bin/env python3
"""
TPF VERITAS SOLO V5 (Data Logger Edition)
=========================================
- Hardware: Goldshell LB-Box (Zynq-7010)
- Target: LBC (Mining-Dutch)
- Strategy: Soft-Filtering + CSV Logging
- Goal: Fix the 99% rejection rate & Capture Data
"""

import socket
import threading
import json
import time
import random
import statistics
import csv
import os
from collections import deque

# CONFIG
LOCAL_HOST = "0.0.0.0"
LOCAL_PORT = 3333
REMOTE_HOST = "lbry.mining-dutch.nl" 
REMOTE_PORT = 9988
USER_WALLET = "apollo13.LBBox"
POOL_PASSWORD = "x" 

# THERMODYNAMIC PARAMETERS (RELAXED FOR LBC)
CALIBRATION_SIZE = 100
# Z-Score Threshold: 
# 0.0 = Average speed. 
# 1.0 = Allow slightly slower than average. 
# We set 1.0 to accept ~84% of shares, rejecting only slow outliers (tail lag).
REJECT_THRESHOLD = 1.0 
KEEP_RATE = 0.10 # Safety Keep Rate

class VeritasLogger:
    def __init__(self, filename="veritas_lbc_data.csv"):
        self.filename = filename
        self.headers = ["Timestamp", "Latency_ms", "Z_Score", "Verdict"]
        if not os.path.exists(self.filename):
            with open(self.filename, mode='w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(self.headers)
    
    def log(self, latency, z_score, verdict):
        try:
            with open(self.filename, mode='a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([f"{time.time():.2f}", f"{latency:.3f}", f"{z_score:.3f}", verdict])
        except: pass

class VeritasEngine:
    def __init__(self):
        self.latency_samples = deque(maxlen=5000)
        self.calibrated = False
        self.mean = 0
        self.std = 1
        print("[VERITAS] Engine Initialized.")

    def add_sample(self, ms):
        self.latency_samples.append(ms)
        if len(self.latency_samples) >= CALIBRATION_SIZE:
            self.mean = statistics.mean(self.latency_samples)
            self.std = statistics.stdev(self.latency_samples)
            if not self.calibrated:
                self.calibrated = True
                print(f"[VERITAS] CALIBRATED BASELINE: {self.mean:.2f}ms (sigma={self.std:.2f})")

    def analyze(self, latency):
        if not self.calibrated:
            return 0.0, False # Warming up
            
        z_score = (latency - self.mean) / (self.std if self.std > 0 else 1)
        
        # LOGIC: We kill ONLY if it's significantly slower than average (High Positive Z)
        # Low Z (Negative) means Fast/Resonant -> KEEP
        # High Z (Positive) means Slow/Lag -> KILL
        should_kill = z_score > REJECT_THRESHOLD
        
        return z_score, should_kill

class SoloHandler:
    def __init__(self, miner_conn, stats, veritas, logger):
        self.miner_conn = miner_conn
        self.stats = stats
        self.veritas = veritas 
        self.logger = logger
        self.pool_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.pool_conn.settimeout(15.0)
        self.running = True
        self.authorized = False
        
        self.latest_params = None
        self.last_accept_t = time.time()
        self.last_job_t = time.time()
        self.job_buffer = deque(maxlen=100)

    def start(self):
        try:
            self.pool_conn.connect((REMOTE_HOST, REMOTE_PORT))
            self.pool_conn.settimeout(None)
            threading.Thread(target=self.upstream, daemon=True).start()
            threading.Thread(target=self.downstream, daemon=True).start()
        except:
            self.miner_conn.close()

    def send_json(self, sock, data):
        try: sock.sendall((json.dumps(data) + '\n').encode())
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
                        msg['params'][1] = POOL_PASSWORD
                        msg['params'][0] = USER_WALLET
                        self.send_json(self.pool_conn, msg)
                    elif method == 'mining.submit' and self.authorized:
                        self.process_with_veritas(msg)
                    else:
                        self.send_json(self.pool_conn, msg)
            except: break
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
                        
                        if msg.get('method') == 'mining.notify':
                            self.latest_params = msg['params']
                            if self.authorized: self.refill_buffer()
                            self.send_json(self.miner_conn, msg)
                        else:
                            self.send_json(self.miner_conn, msg)
                    except: pass
            except: break
        self.running = False

    def process_with_veritas(self, msg):
        latency = (time.time() - self.last_job_t) * 1000 # ms
        self.veritas.add_sample(latency)
        self.stats["scanned"] += 1
        
        z_score, kill_signal = self.veritas.analyze(latency)
        is_keepalive = (time.time() - self.last_accept_t) > 30.0
        
        # CSV LOGGING
        verdict = "KILL" if (kill_signal and not is_keepalive) else "KEEP"
        self.logger.log(latency, z_score, verdict)
        
        if verdict == "KILL":
            # REJECT: Fake Ack (Reset Chip)
            self.send_json(self.miner_conn, {"id": msg.get('id'), "result": True, "error": None})
        else:
            # ACCEPT: Send to Pool
            self.stats["accepted"] += 1
            self.last_accept_t = time.time()
            self.send_json(self.pool_conn, msg)
            
        # FORCE ROTATION (Berserker Effect)
        # We rotate every 2 shares to keep the chip jumping, but we allow more shares to pass.
        if self.job_buffer and (self.stats["scanned"] % 2 == 0):
            p = self.job_buffer.popleft()
            self.last_job_t = time.time()
            self.send_json(self.miner_conn, {"id": None, "method": "mining.notify", "params": p})

    def refill_buffer(self):
        if not self.latest_params: return
        for _ in range(50):
            p = list(self.latest_params)
            p[0] = f"v5_{random.getrandbits(32):x}"
            p[-1] = True 
            self.job_buffer.append(p)

class VeritasSoloController:
    def __init__(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.stats = {"scanned": 0, "accepted": 0}
        self.veritas = VeritasEngine()
        self.logger = VeritasLogger()

    def start(self):
        self.server.bind((LOCAL_HOST, LOCAL_PORT))
        self.server.listen(15)
        print(f"--- TPF VERITAS V5: DATA COLLECTION MODE ---")
        print(f"[*] Logging to veritas_lbc_data.csv")
        threading.Thread(target=self.stats_loop, daemon=True).start()
        while True:
            try:
                conn, addr = self.server.accept()
                handler = SoloHandler(conn, self.stats, self.veritas, self.logger)
                threading.Thread(target=handler.start, daemon=True).start()
            except: pass

    def stats_loop(self):
        start_t = time.time()
        while True:
            time.sleep(30)
            elapsed = (time.time() - start_t) / 60.0
            scanned = self.stats["scanned"]
            if scanned > 0:
                rate = self.stats['accepted']/scanned*100
                print(f"[STATS] Total: {scanned} | Sent to Pool: {self.stats['accepted']} ({rate:.1f}%)")

if __name__ == "__main__":
    VeritasSoloController().start()
