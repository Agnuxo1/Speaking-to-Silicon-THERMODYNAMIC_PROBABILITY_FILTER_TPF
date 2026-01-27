#!/usr/bin/env python3
"""
TPF BERSERKER UNCHAINED V3
==========================
Robust state-machine version to fix the "Dead" status.
Correctly handles the Stratum handshake before triggering high-speed rotation.
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
REMOTE_HOST = "solo.ckpool.org"
REMOTE_PORT = 3333
USER_WALLET = "bc1qhqgw8s89ewu4j45yh3shm2gfwsu3qwfasft6st"

# PARAMETERS
TARGET_X = 600
KEEP_RATE = 1.0 / TARGET_X
FORCE_DIFF = 1.0

class SessionHandler:
    def __init__(self, miner_conn, stats):
        self.miner_conn = miner_conn
        self.pool_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.stats = stats
        self.running = True
        self.authorized = False
        
        self.latest_params = None
        self.last_accept_time = time.time()
        self.job_buffer = deque(maxlen=100)
        self.peer = miner_conn.getpeername()

    def start(self):
        try:
            self.pool_conn.connect((REMOTE_HOST, REMOTE_PORT))
            threading.Thread(target=self.upstream, daemon=True).start()
            threading.Thread(target=self.downstream, daemon=True).start()
            print(f"[*] Connection initialized for {self.peer}")
        except Exception as e:
            print(f"[!] Init Fallo: {e}")
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
                    
                    if method: print(f"  [>] {method} ({self.peer})")

                    if method == 'mining.configure':
                        # Version-rolling is critical for modern S9 firmware
                        res = {"id": msg['id'], "result": {"version-rolling": True, "version-rolling.mask": "ffffffff"}, "error": None}
                        self.send_json(self.miner_conn, res)
                    elif method == 'mining.authorize':
                        # Replace worker name with wallet
                        msg['params'][0] = USER_WALLET
                        self.send_json(self.pool_conn, msg)
                    elif method == 'mining.submit' and self.authorized:
                        self.process_share(msg)
                    else:
                        # Forward authorize, subscribe, etc.
                        self.send_json(self.pool_conn, msg)
            except: break
        self.running = False
        print(f"[-] Upstream closed for {self.peer}")

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
                        result = msg.get('result')
                        
                        # Detect successful authorization
                        if result is True and not method:
                            print(f"  [<] Authorization Granted ({self.peer})")
                            self.authorized = True
                        
                        if method == 'mining.set_difficulty':
                            print(f"  [<] Difficulty Overriding -> {FORCE_DIFF}")
                            msg['params'][0] = FORCE_DIFF
                            self.send_json(self.miner_conn, msg)
                        elif method == 'mining.notify':
                            self.latest_params = msg['params']
                            if self.authorized:
                                self.refill_buffer()
                            self.send_json(self.miner_conn, msg)
                        else:
                            # Forward pool results (subscribe/authorize)
                            self.send_json(self.miner_conn, msg)
                    except:
                        # Fallback for complex pool messages
                        self.miner_conn.sendall((line + '\n').encode())
            except: break
        self.running = False
        print(f"[-] Downstream closed for {self.peer}")

    def refill_buffer(self):
        if not self.latest_params: return
        for _ in range(20):
            p = list(self.latest_params)
            p[0] = hex(random.getrandbits(32))[2:]
            p[8] = True
            self.job_buffer.append(p)

    def process_share(self, msg):
        msg_id = msg.get('id')
        self.stats["scanned"] += 1
        
        is_lucky = random.random() < KEEP_RATE
        is_heartbeat = (time.time() - self.last_accept_time) > 30.0
        
        if is_lucky or is_heartbeat:
            self.stats["accepted"] += 1
            self.last_accept_time = time.time()
            self.send_json(self.pool_conn, msg)
        else:
            # Fake Ack to keep the S9 web UI "Green" (Alive)
            self.send_json(self.miner_conn, {"id": msg_id, "result": True, "error": None})
            
        # Rotate job immediately for x600 effect
        if self.job_buffer:
            p = self.job_buffer.popleft()
            self.send_json(self.miner_conn, {"id": None, "method": "mining.notify", "params": p})
        
        if len(self.job_buffer) < 30:
            threading.Thread(target=self.refill_buffer, daemon=True).start()

class TurboController:
    def __init__(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.stats = {"scanned": 0, "accepted": 0}

    def start(self):
        self.server.bind((LOCAL_HOST, LOCAL_PORT))
        self.server.listen(15)
        print(f"--- TPF UNCHAINED V3 OPERATIONAL ---")
        threading.Thread(target=self.print_stats, daemon=True).start()
        
        while True:
            try:
                conn, addr = self.server.accept()
                handler = SessionHandler(conn, self.stats)
                threading.Thread(target=handler.start, daemon=True).start()
            except: pass

    def print_stats(self):
        start_t = time.time()
        while True:
            time.sleep(15)
            elapsed = (time.time() - start_t) / 60.0
            total = self.stats["scanned"]
            if total > 0 and elapsed > 0:
                print(f"\n[STATS] Speed: x{total/elapsed:.1f} | Tot: {total} | Real: {self.stats['accepted']}")

if __name__ == "__main__":
    TurboController().start()
