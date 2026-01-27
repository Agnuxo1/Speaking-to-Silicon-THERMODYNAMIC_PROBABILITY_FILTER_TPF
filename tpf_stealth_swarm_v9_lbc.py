#!/usr/bin/env python3
"""
TPF VERITAS V9.4 - MULTI-SESSION STEALTH BUTLER (LBC)
=====================================================
Target: Goldshell LB-Box (Zynq-7010)
Strategy: 
 1. Multi-Session Mapping (One pool connection per board)
 2. Identity Spoofing (Goldshell-KA-BOX)
 3. TPF "Pizza Butler" (Zero-Latency Job Feed)
 4. Robust Handshake (Support mining.configure & FIXED Nesting)
"""

import socket
import threading
import json
import time
import statistics
from collections import deque

# ================= CONFIGURATION =================
REMOTE_HOST = "lbry.mining-dutch.nl"
REMOTE_PORT = 9988
USER_WALLET = "apollo13.LBBox"
POOL_PASS = "x"

LOCAL_HOST = "0.0.0.0"
LOCAL_PORT = 3334

FAKE_AGENT = "Goldshell-KA-BOX/2.1.0" 

# TPF PARAMETERS
REJECT_THRESHOLD_Z = 0.8
KEEP_ALIVE_SEC = 45       
# =================================================

class VeritasEngine:
    def __init__(self):
        self.samples = deque(maxlen=200)
        self.mean = 0.0
        self.std = 0.0
        self.calibrated = False
        
    def update(self, latency_ms):
        self.samples.append(latency_ms)
        if len(self.samples) >= 50:
            self.mean = statistics.mean(self.samples)
            self.std = statistics.stdev(self.samples)
            self.calibrated = True
            
    def check_quality(self, latency_ms):
        if not self.calibrated: return "KEEP"
        z_score = (latency_ms - self.mean) / (self.std + 1e-9)
        if z_score > REJECT_THRESHOLD_Z: return "KILL"
        return "KEEP"

class BoardSession:
    def __init__(self, miner_sock, session_id):
        self.miner = miner_sock
        self.session_id = session_id
        self.pool = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.running = True
        self.engine = VeritasEngine()
        
        # State
        self.extranonce1 = None
        self.extranonce2_size = 4
        self.job_buffer = deque(maxlen=50)
        self.last_job_time = time.time()
        self.last_submit_time = time.time()
        
        # Stats
        self.shares_ok = 0
        self.shares_filtered = 0
        self.share_id_counter = 1000

    def start(self):
        try:
            self.pool.connect((REMOTE_HOST, REMOTE_PORT))
            # Handshake with Pool
            self._send(self.pool, {"id": 1, "method": "mining.subscribe", "params": [FAKE_AGENT]})
            
            # Start Threads
            threading.Thread(target=self.upstream, daemon=True).start()
            threading.Thread(target=self.downstream, daemon=True).start()
            print(f"[*] Board {self.session_id} handshake initiated.")
        except Exception as e:
            print(f"[!] Board {self.session_id} failed: {e}")
            self.stop()

    def _send(self, sock, data):
        try: sock.sendall((json.dumps(data) + '\n').encode())
        except: self.stop()

    def downstream(self):
        """Pool -> Proxy -> ASIC"""
        buff = ""
        while self.running:
            try:
                data = self.pool.recv(4096).decode('utf-8', errors='ignore')
                if not data: break
                buff += data
                while '\n' in buff:
                    line, buff = buff.split('\n', 1)
                    if not line.strip(): continue
                    self.handle_pool_msg(json.loads(line))
            except: break
        self.stop()

    def handle_pool_msg(self, msg):
        # print(f"[POOL -> PROXY] {msg}")
        mid = msg.get('id')
        method = msg.get('method')

        if mid == 1:
            res = msg.get('result')
            if res:
                self.extranonce1 = res[1]
                self.extranonce2_size = res[2]
                self._send(self.pool, {"id": 2, "method": "mining.authorize", "params": [USER_WALLET, POOL_PASS]})

        elif method == 'mining.notify':
            self.job_buffer.append(msg)
            if len(self.job_buffer) == 1:
                self._send(self.miner, msg)

        elif method == 'mining.set_difficulty':
            self._send(self.miner, msg)

        elif mid == 4:
            if msg.get('result') is True:
                self.shares_ok += 1

    def upstream(self):
        """ASIC -> Proxy -> Pool"""
        buff = ""
        while self.running:
            try:
                data = self.miner.recv(4096).decode('utf-8', errors='ignore')
                if not data: break
                buff += data
                while '\n' in buff or '\x00' in buff:
                    # Handle both \n and \x00 as delimiters (Robustness for Goldshell)
                    if '\n' in buff:
                        line, buff = buff.split('\n', 1)
                    else:
                        line, buff = buff.split('\x00', 1)
                    
                    if not line.strip(): continue
                    self.handle_miner_msg(json.loads(line))
            except: break
        self.stop()

    def handle_miner_msg(self, msg):
        # print(f"[ASIC -> PROXY] {msg}")
        method = msg.get('method')
        mid = msg.get('id')

        if method == 'mining.configure':
            self._send(self.miner, {
                "id": mid, 
                "result": {"version-rolling": True, "version-rolling.mask": "1fffe000"}, 
                "error": None
            })

        elif method == 'mining.subscribe':
            while self.extranonce1 is None and self.running: time.sleep(0.1)
            if not self.running: return
            self._send(self.miner, {
                "id": mid,
                "result": [[["mining.notify", self.extranonce1]], self.extranonce1, self.extranonce2_size],
                "error": None
            })

        elif method == 'mining.authorize':
            self._send(self.miner, {"id": mid, "result": True, "error": None})

        elif method == 'mining.submit':
            now = time.time()
            latency = (now - self.last_job_time) * 1000
            self.engine.update(latency)
            
            decision = self.engine.check_quality(latency)
            if (now - self.last_submit_time) > KEEP_ALIVE_SEC: decision = "KEEP"

            if decision == "KEEP":
                msg['id'] = self.share_id_counter
                self.share_id_counter += 1
                self._send(self.pool, msg)
                self.last_submit_time = now
            else:
                self.shares_filtered += 1

            self._send(self.miner, {"id": mid, "result": True, "error": None})
            self.feed_butler()

    def feed_butler(self):
        if self.job_buffer:
            job = self.job_buffer[-1]
            job['params'][8] = True 
            self._send(self.miner, job)
            self.last_job_time = time.time()

    def stop(self):
        self.running = False
        try: self.miner.close()
        except: pass
        try: self.pool.close()
        except: pass

class StealthButlerServer:
    def __init__(self):
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sessions = []

    def run(self):
        self.srv.bind((LOCAL_HOST, LOCAL_PORT))
        self.srv.listen(5)
        print(f"======================================================")
        print(f" TPF VERITAS V9.4 - MULTI-BOARD STEALTH (LBC)")
        print(f" Port: {LOCAL_PORT} | Identity: {FAKE_AGENT}")
        print(f"======================================================")

        session_id = 1
        while True:
            try:
                conn, addr = self.srv.accept()
                print(f"[+] Connection from {addr} (Board {session_id})")
                session = BoardSession(conn, session_id)
                self.sessions.append(session)
                session.start()
                session_id += 1
            except Exception as e:
                print(f"[ERR] {e}")

if __name__ == "__main__":
    server = StealthButlerServer()
    server.run()
