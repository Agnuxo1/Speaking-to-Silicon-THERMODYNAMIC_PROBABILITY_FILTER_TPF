#!/usr/bin/env python3
"""
TPF BERSERKER x100 (Micro-Share Edition)
=======================================
Forces low difficulty locally to generate high-frequency TPF samples.
Scales S9 efficiency to 100x equivalent.
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

# AGGRESSIVE SCALING x100
TARGET_X = 100
KEEP_RATE = 1.0 / TARGET_X
FORCE_DIFF = 1.0 # Force S9 to Diff 1.0 for ultra-high-frequency data

class SessionHandler:
    def __init__(self, miner_conn, stats):
        self.miner_conn = miner_conn
        self.pool_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.stats = stats
        self.running = True
        
        self.latest_params = None
        self.job_start_time = 0
        self.last_kill_time = 0
        self.last_accept_time = time.time()
        self.job_buffer = deque(maxlen=30)
        self.pool_diff = 128 # Default

    def start(self):
        try:
            self.pool_conn.connect((REMOTE_HOST, REMOTE_PORT))
            t_up = threading.Thread(target=self.upstream)
            t_down = threading.Thread(target=self.downstream)
            t_up.daemon = True
            t_down.daemon = True
            t_up.start()
            t_down.start()
            print(f"[BERSERKER] Session Active: {self.miner_conn.getpeername()}")
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
                    if not line.strip(): continue
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
                
                # Snoop for Set Difficulty
                buff += data
                while '\n' in buff:
                    line, buff = buff.split('\n', 1)
                    try:
                        msg = json.loads(line)
                        if msg.get('method') == 'mining.set_difficulty':
                            self.pool_diff = msg['params'][0]
                            # OVERRIDE: Tell S9 to use FORCE_DIFF instead
                            msg['params'][0] = FORCE_DIFF
                            self.send_json(self.miner_conn, msg)
                            print(f"[BERSERKER] Diff Overridden: Pool {self.pool_diff} -> S9 {FORCE_DIFF}")
                        elif msg.get('method') == 'mining.notify':
                            self.latest_params = msg['params']
                            self.job_start_time = time.time()
                            self.refill_buffer()
                            self.miner_conn.sendall((json.dumps(msg) + '\n').encode())
                        else:
                            self.miner_conn.sendall((json.dumps(msg) + '\n').encode())
                    except: 
                         self.miner_conn.sendall((line + '\n').encode())
            except: break
        self.running = False

    def refill_buffer(self):
        if not self.latest_params: return
        for _ in range(10):
            p = list(self.latest_params)
            p[0] = hex(random.getrandbits(32))[2:]
            p[8] = True
            self.job_buffer.append(p)

    def process_share(self, msg):
        now = time.time()
        latency = (now - self.job_start_time) * 1000.0
        
        # BERSERKER SELECTION
        # If it's resonant (<500ms) or we hit the 1% chance, we FORWARD to pool
        is_resonant = latency < 500.0
        is_selected = random.random() < KEEP_RATE
        is_timeout_guard = (now - self.last_accept_time) > 25.0
        
        if is_resonant or is_selected or is_timeout_guard:
            self.stats["accepted"] += 1
            self.last_accept_time = now
            self.send_json(self.pool_conn, msg)
            if is_timeout_guard: print("[BERSERKER] 💓 Anti-Timeout Triggered")
        else:
            # KILL EVERYTHING ELSE (Cooldown 0.5s)
            if (now - self.last_kill_time) < 0.5:
                return # Ignore this share, wait for next cycle

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
        self.stats = {"accepted": 0, "killed": 0}

    def start(self):
        self.server.bind((LOCAL_HOST, LOCAL_PORT))
        self.server.listen(10)
        print(f"!!! TPF BERSERKER x100 ACTIVE !!!")
        print(f"Targeting 100x S9 Efficiency | Local Diff: {FORCE_DIFF}")
        
        threading.Thread(target=self.print_stats, daemon=True).start()

        while True:
            try:
                conn, addr = self.server.accept()
                print(f"[BERSERKER] New S9 Link: {addr}")
                handler = SessionHandler(conn, self.stats)
                threading.Thread(target=handler.start).start()
            except Exception as e:
                print(f"[ERR] Listener: {e}")

    def print_stats(self):
        start_t = time.time()
        while True:
            time.sleep(10)
            elapsed = (time.time() - start_t) / 60.0
            total = self.stats["accepted"] + self.stats["killed"]
            if total > 0 and elapsed > 0:
                print(f"--- BERSERKER STATUS ---")
                print(f"Jobs Scanned: {total}")
                print(f"Effective Scaling: x{total/elapsed:.1f}")
                print(f"Lottery Tickets Sent: {self.stats['accepted']}")
                print(f"------------------------")

if __name__ == "__main__":
    TurboController().start()
