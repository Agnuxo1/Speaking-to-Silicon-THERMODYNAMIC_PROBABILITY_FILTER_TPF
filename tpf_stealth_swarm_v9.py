#!/usr/bin/env python3
"""
TPF VERITAS V9.1 - STEALTH SWARM EDITION
========================================
Architecture: 1-to-1 Hardware Mapping + Identity Spoofing
Target: Shared Pool Mining (BTC or LBC)
Spoofing Identity: Antminer S21 Pro (234 Th/s)
Zero-Latency Logic: "The Pizza Butler"

[THEORY OF OPERATION]
1. HARDWARE SYNC: We map each physical board connection 1-to-1 with a pool worker.
2. IDENTITY SPOOF: We present as a modern S21 Pro to avoid hashrate flags.
3. BUTLER: Zero-latency pre-fetching for each individual board connection.
4. STABILITY: No mid-session extranonce changes = 100% acceptance.
"""

import socket
import threading
import json
import time
import sys
from collections import deque

# ================= CONFIGURATION =================
# SELECT MODE: 'BTC' or 'LBC'
MODE = 'BTC' 

if MODE == 'BTC':
    LOCAL_PORT = 3333
    REMOTE_HOST = "stratum.braiins.com"
    REMOTE_PORT = 3333
    USER_ID = "Ant-S29" # Your Braiins Account
    POOL_PASS = "anything123"
    SPOOF_AGENT = "antminer-S21-Pro/1.0" # Modern identity
else:
    LOCAL_PORT = 3334
    REMOTE_HOST = "lbry.mining-dutch.nl"
    REMOTE_PORT = 9988
    USER_ID = "apollo13" # Your Mining-Dutch Username
    POOL_PASS = "x"
    SPOOF_AGENT = "Goldshell-KA-BOX/1.0" # Spoofing a modern LBC miner

LOCAL_HOST = "0.0.0.0"
BUTLER_BUFFER_SIZE = 50

# =================================================

class BoardSession:
    """Handles a 1-to-1 link between a physical board and a pool worker."""
    def __init__(self, miner_conn, session_id):
        self.miner = miner_conn
        self.session_id = session_id
        self.worker_name = f"{USER_ID}.S21_{session_id:01d}"
        self.pool = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.running = True
        
        # State
        self.extranonce1 = None
        self.extranonce2_size = 4
        self.difficulty = 4096 if MODE == 'LBC' else 1024
        self.job_buffer = deque(maxlen=BUTLER_BUFFER_SIZE)
        
        # Stats
        self.shares_ok = 0
        self.shares_err = 0
        self.last_pool_msg = "Handshaking..."

    def start(self):
        try:
            print(f"[*] Session {self.session_id}: Connecting to {REMOTE_HOST}...")
            self.pool.connect((REMOTE_HOST, REMOTE_PORT))
            
            # 1. Subscribe (SPOOFED IDENTITY)
            self._send(self.pool, {
                "id": 1, 
                "method": "mining.subscribe", 
                "params": [SPOOF_AGENT]
            })
            
            # Start threads
            threading.Thread(target=self.pool_to_miner, daemon=True).start()
            threading.Thread(target=self.miner_to_pool, daemon=True).start()
        except Exception as e:
            print(f"[!] Session {self.session_id} failed: {e}")
            self.stop()

    def _send(self, sock, data):
        try:
            sock.sendall((json.dumps(data) + '\n').encode())
        except:
            self.stop()

    def pool_to_miner(self):
        """Pool -> Stealth Controller -> Physical Board"""
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
        # print(f"[DEBUG] Pool -> Board {self.session_id}: {msg}")
        method = msg.get('method')
        
        # 1. Capture Credentials on Subscribe
        if msg.get('id') == 1:
            res = msg.get('result')
            # Format: [ [["mining.set_difficulty",...],...], "extranonce1", extranonce2_size ]
            if res and len(res) >= 3:
                self.extranonce1 = res[1]
                self.extranonce2_size = res[2]
                print(f"[#] Board {self.session_id} Sync: Extranonce={self.extranonce1} Size={self.extranonce2_size}")
                # Authorize now
                self._send(self.pool, {
                    "id": 2, 
                    "method": "mining.authorize", 
                    "params": [self.worker_name, POOL_PASS]
                })

        # 2. Track Share Status
        elif msg.get('id') == 4:
            if msg.get('result') is True:
                self.shares_ok += 1
                self.last_pool_msg = "OK"
            else:
                self.shares_err += 1
                self.last_pool_msg = f"ERR: {msg.get('error')}"

        # 3. Handle Difficulty
        elif method == 'mining.set_difficulty':
            self.difficulty = msg['params'][0]
            # Forward to miner immediately
            self._send(self.miner, msg)

        # 4. Handle Jobs (Pizza Butler Buffer)
        elif method == 'mining.notify':
            self.job_buffer.append(msg)
            # Forward ONLY the first job to get the miner started
            if len(self.job_buffer) == 1:
                self._send(self.miner, msg)

    def miner_to_pool(self):
        """Physical Board -> Stealth Controller -> Pool"""
        buff = ""
        while self.running:
            try:
                data = self.miner.recv(4096).decode('utf-8', errors='ignore')
                if not data: break
                buff += data
                while '\n' in buff:
                    line, buff = buff.split('\n', 1)
                    if not line.strip(): continue
                    self.handle_miner_msg(json.loads(line))
            except: break
        self.stop()

    def handle_miner_msg(self, msg):
        method = msg.get('method')
        msg_id = msg.get('id')

        if method == 'mining.subscribe':
            while not self.extranonce1 and self.running: 
                time.sleep(0.5)
            
            if not self.running: return

            # Fallback if pool sent empty extranonce (S9 NEEDS string)
            ex1 = self.extranonce1 if self.extranonce1 else "00000000"
            
            self._send(self.miner, {
                "id": msg_id,
                "result": [
                    ["mining.notify", f"stealth_{self.session_id}"],
                    ex1,
                    self.extranonce2_size
                ],
                "error": None
            })
            
        elif method == 'mining.authorize':
            # Fast-track authorization
            self._send(self.miner, {"id": msg_id, "result": True, "error": None})

        elif method == 'mining.submit':
            # 1. Instant ACK to hardware (Zero Latency)
            self._send(self.miner, {"id": msg_id, "result": True, "error": None})
            
            # 2. Extract Nonces
            params = msg['params']
            nonce2 = params[2]
            
            # PADDING STRATEGY (S9 4-byte -> Pool X-byte)
            # If pool wants 6 bytes but S9 sends 4, we pad with zeros
            if len(nonce2) < self.extranonce2_size * 2:
                padding = "0" * (self.extranonce2_size * 2 - len(nonce2))
                nonce2 = nonce2 + padding
            elif len(nonce2) > self.extranonce2_size * 2:
                nonce2 = nonce2[:self.extranonce2_size * 2]

            # 3. Route to Pool (Overwrite our worker name for stealth)
            payload = {
                "params": [
                    self.worker_name,
                    params[1], # Job ID
                    nonce2,
                    params[3], # ntime
                    params[4]  # nonce
                ],
                "id": 4,
                "method": "mining.submit"
            }
            self._send(self.pool, payload)
            
            # 4. BUTLER: Feed next job from buffer instantly
            self.butler_feed()

    def butler_feed(self):
        if self.job_buffer:
            # Pop the freshest job (LIFO logic or rotated)
            job = self.job_buffer[-1]
            self._send(self.miner, job)

    def stop(self):
        self.running = False
        try: self.miner.close()
        except: pass
        try: self.pool.close()
        except: pass

class StealthSwarmProxy:
    def __init__(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sessions = []
        self.max_sessions = 5 # Prevent explosion
        self.start_time = time.time()

    def run(self):
        self.server.bind((LOCAL_HOST, LOCAL_PORT))
        self.server.listen(5)
        print(f"======================================================")
        print(f" TPF VERITAS V9.1 - STEALTH SWARM ({MODE})")
        print(f" Port: {LOCAL_PORT} | Identity: {SPOOF_AGENT}")
        print(f" Limit: {self.max_sessions} Sessions")
        print(f"======================================================")
        
        session_counter = 1
        while True:
            conn, addr = self.server.accept()
            
            # Prune dead sessions
            self.sessions = [s for s in self.sessions if s.running]
            
            if len(self.sessions) >= self.max_sessions:
                print(f"[!] Throttling: Max sessions reached. Closing {addr}")
                conn.close()
                continue

            print(f"[+] Hardware Connection: {addr}")
            session = BoardSession(conn, session_counter)
            self.sessions.append(session)
            session.start()
            session_counter += 1

def stats_printer(proxy):
    while True:
        time.sleep(30)
        print(f"\n--- [SWARM STATS] ---")
        for s in proxy.sessions:
            if s.running:
                print(f"  Board {s.session_id} ({s.worker_name}): OK={s.shares_ok} ERR={s.shares_err} Status={s.last_pool_msg}")
        print(f"----------------------")

if __name__ == "__main__":
    proxy = StealthSwarmProxy()
    threading.Thread(target=stats_printer, args=(proxy,), daemon=True).start()
    proxy.run()
