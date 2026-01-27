#!/usr/bin/env python3
"""
TPF EXTERNAL CONTROLLER v2 (Robust Handshake Edition)
=====================================================
Fixes "Dead" Miner status by handling Version-Rolling locally.

Traffic Flow:
[S9] -> (Parse) -> [Logic] -> [Pool]
[Pool] -> (Pass) -> [S9]
"""

import socket
import threading
import json
import time
import queue
import select

# CONFIG
LOCAL_HOST = "0.0.0.0"
LOCAL_PORT = 3333
REMOTE_HOST = "solo.ckpool.org"
REMOTE_PORT = 3333
USER_WALLET = "bc1qhqgw8s89ewu4j45yh3shm2gfwsu3qwfasft6st"

# STRESS TEST PARAMS
STRESS_MODE = True
TARGET_SCALING = 300 # Try x300
KEEP_RATE = 1.0 / TARGET_SCALING

class TPFController:
    def __init__(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.running = True
        self.current_job_id = None
        self.job_start_time = 0
        self.latest_params = None
        self.stats = {
            "accepted": 0, 
            "killed": 0, 
            "errors": 0,
            "start_time": time.time()
        }

    def start(self):
        self.server.bind((LOCAL_HOST, LOCAL_PORT))
        self.server.listen(1)
        print(f"[TPF-STRESS] Target Speed: x{TARGET_SCALING}")
        print(f"[TPF-STRESS] Keep Rate: {KEEP_RATE*100:.3f}%")
        print(f"[TPF-STRESS] Listening on {LOCAL_PORT}...")
        
        while self.running:
            try:
                conn, addr = self.server.accept()
                print(f"[TPF] Miner Connected: {addr}")
                t = threading.Thread(target=self.handle_session, args=(conn,))
                t.daemon = True
                t.start()
            except Exception as e:
                print(f"[ERR] Listener: {e}")

    def handle_session(self, miner_conn):
        pool_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            pool_conn.connect((REMOTE_HOST, REMOTE_PORT))
        except:
            miner_conn.close()
            return

        t_upstream = threading.Thread(target=self.upstream_loop, args=(miner_conn, pool_conn))
        t_downstream = threading.Thread(target=self.downstream_loop, args=(pool_conn, miner_conn))
        
        t_upstream.start()
        t_downstream.start()
        
        # Monitor Loop for 60 seconds
        start_test = time.time()
        while time.time() - start_test < 60:
            time.sleep(1)
            elapsed = time.time() - start_test
            total = self.stats["accepted"] + self.stats["killed"]
            if total > 0:
                print(f"[STRESS {elapsed:.0f}s] Jobs: {total} | Kills: {self.stats['killed']} | Errors: {self.stats['errors']}")
        
        print("\n--- TEST COMPLETE ---")
        self.print_results()
        self.running = False # Exit after test

    def upstream_loop(self, miner, pool):
        buff = ""
        while self.running:
            try:
                data = miner.recv(4096).decode('utf-8', errors='ignore')
                if not data: break
                
                buff += data
                while '\n' in buff:
                    line, buff = buff.split('\n', 1)
                    if not line.strip(): continue
                    try:
                        msg = json.loads(line)
                        method = msg.get('method')
                        
                        if method == 'mining.configure':
                            self.send_json(miner, {"id": msg['id'], "result": {"version-rolling": True, "version-rolling.mask": "ffffffff"}, "error": None})
                            continue
                        if method == 'mining.suggest_difficulty':
                             self.send_json(miner, {"id": msg['id'], "result": True, "error": None})
                             continue 
                        if method == 'mining.authorize':
                            msg['params'][0] = USER_WALLET
                            self.send_json(pool, msg)
                            continue
                        if method == 'mining.submit':
                             self.analyze_share(msg, miner)
                             self.send_json(pool, msg)
                             continue
                        self.send_json(pool, msg)
                    except:
                        pool.sendall((line + '\n').encode())
            except: 
                self.stats["errors"] += 1
                break

    def downstream_loop(self, pool, miner):
        buff = ""
        while self.running:
            try:
                data = pool.recv(4096).decode('utf-8', errors='ignore')
                if not data: break
                miner.sendall(data.encode())
                buff += data
                while '\n' in buff:
                    line, buff = buff.split('\n', 1)
                    try:
                        msg = json.loads(line)
                        if msg.get('method') == 'mining.notify':
                            self.current_job_id = msg['params'][0]
                            self.latest_params = msg['params']
                            self.job_start_time = time.time()
                    except: pass
            except: break

    def send_json(self, sock, data):
        try:
            sock.sendall((json.dumps(data) + '\n').encode())
        except: self.stats["errors"] += 1

    def analyze_share(self, msg, miner_conn):
        now = time.time()
        latency_ms = (now - self.job_start_time) * 1000.0
        
        # AGGRESSIVE SCALING LOGIC
        # 1. Very Fast Acceptance (< 500ms)
        is_lucky = latency_ms < 500.0 
        
        # 2. Strict Probabilistic Gate
        selection_roll = random.random() < KEEP_RATE
        
        if is_lucky or selection_roll:
            self.stats["accepted"] += 1
        else:
            self.trigger_kill(miner_conn)

    def trigger_kill(self, miner_conn):
        if not self.latest_params: return
        fake_id = str(random.getrandbits(32))
        params = list(self.latest_params)
        params[0] = fake_id
        params[8] = True 
        try:
            self.send_json(miner_conn, {"id": None, "method": "mining.notify", "params": params})
            self.stats["killed"] += 1
        except: self.stats["errors"] += 1

    def print_results(self):
        elapsed = time.time() - self.stats["start_time"]
        total = self.stats["accepted"] + self.stats["killed"]
        print(f"Final Scaling: x{total / (elapsed/60.0 + 1e-9):.1f}")
        print(f"Success Rate: {(1 - self.stats['errors']/(total+1e-9))*100:.2f}%")

if __name__ == "__main__":
    ctrl = TPFController()
    ctrl.start()

if __name__ == "__main__":
    while True:
        try:
            ctrl = TPFController()
            ctrl.start()
        except KeyboardInterrupt: break
        except: time.sleep(1)
