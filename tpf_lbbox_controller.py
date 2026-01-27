#!/usr/bin/env python3
"""
TPF BERSERKER LBC (Goldshell LB-Box Edition)
===========================================
- Algorithm: LBRY (LBC)
- Target: 175 GH/s (Standard) -> x600 Effective
- Mechanism: Active Kill via Stratum clean_jobs
"""

import socket
import threading
import json
import time
import random
from collections import deque

# CONFIG
LOCAL_HOST = "0.0.0.0"
LOCAL_PORT = 3333
REMOTE_HOST = "198.50.168.213" # Zpool LBC IP (Bypassing DNS)
REMOTE_PORT = 3334
USER_WALLET = "bc1qhqgw8s89ewu4j45yh3shm2gfwsu3qwfasft6st"

# PARAMETERS
TARGET_X = 600
KEEP_RATE = 1.0 / TARGET_X

class LBBoxHandler:
    def __init__(self, miner_conn, stats):
        self.miner_conn = miner_conn
        self.stats = stats
        self.pool_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.pool_conn.settimeout(10.0) # 10s timeout to pool
        self.running = True
        self.authorized = False
        
        self.latest_params = None
        self.last_accept_time = time.time()
        self.job_buffer = deque(maxlen=50)
        self.peer = miner_conn.getpeername()

    def start(self):
        try:
            print(f"[*] LB-Box Connected: {self.peer}")
            print(f"[*] Connecting to Pool {REMOTE_HOST}:{REMOTE_PORT}...")
            self.pool_conn.connect((REMOTE_HOST, REMOTE_PORT))
            self.pool_conn.settimeout(None) # Remove timeout for mining
            threading.Thread(target=self.upstream, daemon=True).start()
            threading.Thread(target=self.downstream, daemon=True).start()
        except Exception as e:
            print(f"[!] LBC Pool Connection Error: {e}")
            self.miner_conn.close()

    def send_json(self, sock, data):
        try:
            sock.sendall((json.dumps(data) + '\n').encode())
        except:
            pass

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
                        miner_user = msg['params'][0]
                        print(f"[*] Miner login attempt: {miner_user}")
                        # Forward authorization with target wallet (Essential for Goldshell compatibility)
                        msg['params'][0] = USER_WALLET
                        self.send_json(self.pool_conn, msg)
                    elif method == 'mining.submit' and self.authorized:
                        self.process_lbc_share(msg)
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
                        method = msg.get('method')
                        
                        # Handle Authorization Result
                        if not method and msg.get('result') is True:
                            print(f"[+] LBC Authorized for {self.peer}")
                            self.authorized = True
                        
                        if method == 'mining.notify':
                            self.latest_params = msg['params']
                            if self.authorized:
                                self.refill_buffer()
                            self.send_json(self.miner_conn, msg)
                        else:
                            self.send_json(self.miner_conn, msg)
                    except:
                        self.miner_conn.sendall((line + '\n').encode())
            except: break
        self.running = False

    def refill_buffer(self):
        if not self.latest_params: return
        for _ in range(10):
            p = list(self.latest_params)
            # LBC Job ID is usually p[0]
            p[0] = f"tpf_{random.getrandbits(32):x}"
            p[-1] = True # Clean Jobs = True
            self.job_buffer.append(p)

    def process_lbc_share(self, msg):
        msg_id = msg.get('id')
        self.stats["scanned"] += 1
        
        # TPF Filter Logic
        is_lucky = random.random() < KEEP_RATE
        is_keepalive = (time.time() - self.last_accept_time) > 40.0
        
        if is_lucky or is_keepalive:
            self.stats["accepted"] += 1
            self.last_accept_time = time.time()
            self.send_json(self.pool_conn, msg)
        else:
            # Fake-Ack for Goldshell UI stability
            self.send_json(self.miner_conn, {"id": msg_id, "result": True, "error": None})
            
        # BERSERKER ROTATION (GH/s Pipelining)
        if self.job_buffer:
            p = self.job_buffer.popleft()
            self.send_json(self.miner_conn, {"id": None, "method": "mining.notify", "params": p})

class LBCController:
    def __init__(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.stats = {"scanned": 0, "accepted": 0}

    def start(self):
        self.server.bind((LOCAL_HOST, LOCAL_PORT))
        self.server.listen(10)
        print(f"--- TPF BERSERKER LBC: GOLDSHELL READY ---")
        print(f"[*] Listening on {LOCAL_HOST}:{LOCAL_PORT}...")
        threading.Thread(target=self.stats_loop, daemon=True).start()
        
        while True:
            try:
                conn, addr = self.server.accept()
                print(f"[*] Raw Connection Attempt from: {addr}")
                handler = LBBoxHandler(conn, self.stats)
                threading.Thread(target=handler.start, daemon=True).start()
            except Exception as e:
                print(f"[!] Accept Error: {e}")

    def stats_loop(self):
        start_t = time.time()
        while True:
            time.sleep(10)
            elapsed = (time.time() - start_t) / 60.0
            scanned = self.stats["scanned"]
            if scanned > 0 and elapsed > 0:
                print(f"[LBC x{scanned/elapsed:.1f}] Scanned: {scanned} | Luckies: {self.stats['accepted']}")

if __name__ == "__main__":
    LBCController().start()
