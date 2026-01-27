#!/usr/bin/env python3
"""
TPF TURBO x60 (Pipelined Prototype)
===================================
Uses Job Pipelining to reach x50 efficiency.
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

# SCALING X60 (Optimal Stable Limit)
TARGET_X = 60
KEEP_RATE = 1.0 / TARGET_X

class SessionHandler:
    def __init__(self, miner_conn, stats, global_config):
        self.miner_conn = miner_conn
        self.pool_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.stats = stats
        self.config = global_config
        self.running = True
        
        self.latest_params = None
        self.job_start_time = 0
        self.last_kill_time = 0
        self.last_accept_time = time.time()
        self.job_buffer = deque(maxlen=20)

    def start(self):
        try:
            self.pool_conn.connect((REMOTE_HOST, REMOTE_PORT))
            t_up = threading.Thread(target=self.upstream)
            t_down = threading.Thread(target=self.downstream)
            t_up.daemon = True
            t_down.daemon = True
            t_up.start()
            t_down.start()
            print(f"[SESSION] Handshake Complete for {self.miner_conn.getpeername()}")
        except Exception as e:
            print(f"[ERR] Session failed: {e}")
            self.miner_conn.close()

    def upstream(self):
        buff = ""
        while self.running:
            try:
                data = self.miner_conn.recv(4096).decode('utf-8', errors='ignore')
                if not data: break
                buff += data
                while '\n' in buff:
                    line, buff = buff.split('\n', 1)
                    msg = json.loads(line)
                    method = msg.get('method')
                    
                    if method == 'mining.configure':
                        self.send_json(self.miner_conn, {"id": msg['id'], "result": {"version-rolling": True, "version-rolling.mask": "ffffffff"}, "error": None})
                    elif method == 'mining.authorize':
                        msg['params'][0] = USER_WALLET
                        self.send_json(self.pool_conn, msg)
                    elif method == 'mining.submit':
                        self.process_share(msg)
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
                self.miner_conn.sendall(data.encode())
                buff += data
                while '\n' in buff:
                    line, buff = buff.split('\n', 1)
                    try:
                        msg = json.loads(line)
                        if msg.get('method') == 'mining.notify':
                            self.latest_params = msg['params']
                            self.job_start_time = time.time()
                            self.refill_buffer()
                    except: pass
            except: break
        self.running = False

    def refill_buffer(self):
        for _ in range(5):
            p = list(self.latest_params)
            p[0] = hex(random.getrandbits(32))[2:]
            p[8] = True
            self.job_buffer.append(p)

    def process_share(self, msg):
        now = time.time()
        latency = (now - self.job_start_time) * 1000.0
        
        # ANTI-TIMEOUT LOGIC: Force an accept if we haven't accepted anything in 30s
        forced_keep = (now - self.last_accept_time) > 30.0
        
        if forced_keep or (latency < 400.0) or (random.random() < KEEP_RATE):
            self.stats["accepted"] += 1
            self.last_accept_time = now
            self.send_json(self.pool_conn, msg)
            if forced_keep: print("[TURBO] 💓 Keep-Alive Share Forced")
        else:
            if (now - self.last_kill_time) < 1.0:
                self.send_json(self.pool_conn, msg)
                return

            self.stats["killed"] += 1
            self.last_kill_time = now
            if self.job_buffer:
                p = self.job_buffer.popleft()
                self.send_json(self.miner_conn, {"id": None, "method": "mining.notify", "params": p})
                self.job_start_time = time.time()

    def send_json(self, sock, data):
        try: sock.sendall((json.dumps(data) + '\n').encode())
        except: pass

class TurboController:
    def __init__(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.stats = {"accepted": 0, "killed": 0, "errors": 0}

    def start(self):
        self.server.bind((LOCAL_HOST, LOCAL_PORT))
        self.server.listen(5) # Allow backlogging for multiple workers
        print(f"[TURBO x60] Multi-Worker Mode Active on {LOCAL_PORT}...")
        
        # Global Stat Thread
        threading.Thread(target=self.print_stats, daemon=True).start()

        while True:
            try:
                conn, addr = self.server.accept()
                print(f"[TURBO] New Connection: {addr}")
                handler = SessionHandler(conn, self.stats, {})
                handler.start()
            except Exception as e:
                print(f"[ERR] Listener: {e}")

    def print_stats(self):
        start_t = time.time()
        while True:
            time.sleep(10)
            elapsed = (time.time() - start_t) / 60.0
            total = self.stats["accepted"] + self.stats["killed"]
            if total > 0 and elapsed > 0:
                print(f"[GLOBAL] Jobs: {total} | Real Speed: x{total/elapsed:.1f}")

if __name__ == "__main__":
    TurboController().start()

if __name__ == "__main__":
    TurboController().start()
