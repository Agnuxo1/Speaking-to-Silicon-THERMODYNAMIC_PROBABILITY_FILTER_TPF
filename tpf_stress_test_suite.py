#!/usr/bin/env python3
"""
TPF STRESS TEST SUITE (x100 - x400)
===================================
Finds the maximum physical speed of the S9 external bridge.
"""

import socket
import threading
import json
import time
import random

# CONFIG
LOCAL_HOST = "0.0.0.0"
LOCAL_PORT = 3333
REMOTE_HOST = "solo.ckpool.org"
REMOTE_PORT = 3333
USER_WALLET = "bc1qhqgw8s89ewu4j45yh3shm2gfwsu3qwfasft6st"

class StressTestController:
    def __init__(self, scaling_factor):
        self.scaling = scaling_factor
        self.keep_rate = 1.0 / scaling_factor
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.running = True
        self.session_active = False
        
        self.current_job_id = None
        self.latest_params = None
        self.job_start_time = 0
        
        self.stats = {
            "accepted": 0,
            "killed": 0,
            "errors": 0,
            "shares_received": 0
        }

    def run_60s_test(self):
        self.server.bind((LOCAL_HOST, LOCAL_PORT))
        self.server.listen(1)
        print(f"\n[TEST STAGE] === TARGET: x{self.scaling} (Keep Rate: {self.keep_rate*100:.3f}%) ===")
        print(f"[TEST STAGE] Waiting for S9 to connect on {LOCAL_PORT}...")
        
        self.server.settimeout(30) # Wait 30s for connection
        try:
            miner_conn, addr = self.server.accept()
            print(f"[TEST STAGE] S9 Connected: {addr}")
            self.session_active = True
        except socket.timeout:
            print("[ERR] S9 did not connect in time.")
            self.server.close()
            return None

        pool_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            pool_conn.connect((REMOTE_HOST, REMOTE_PORT))
        except:
            miner_conn.close()
            self.server.close()
            return None

        # Start Proxy Threads
        t_up = threading.Thread(target=self.upstream, args=(miner_conn, pool_conn))
        t_down = threading.Thread(target=self.downstream, args=(pool_conn, miner_conn))
        t_up.start()
        t_down.start()

        # Monitoring
        start_time = time.time()
        while time.time() - start_time < 60:
            time.sleep(5)
            elapsed = time.time() - start_time
            print(f"  [{elapsed:.0f}s] Speed: x{self.get_current_speed(elapsed):.1f} | Success: {self.get_success_rate():.1f}%")

        # Cleanup
        self.running = False
        miner_conn.close()
        pool_conn.close()
        self.server.close()
        
        return self.get_report(60)

    def upstream(self, miner, pool):
        buff = ""
        while self.running:
            try:
                data = miner.recv(4096).decode('utf-8', errors='ignore')
                if not data: break
                buff += data
                while '\n' in buff:
                    line, buff = buff.split('\n', 1)
                    if not line.strip(): continue
                    msg = json.loads(line)
                    method = msg.get('method')
                    
                    if method == 'mining.configure':
                        miner.sendall((json.dumps({"id": msg['id'], "result": {"version-rolling": True, "version-rolling.mask": "ffffffff"}, "error": None}) + '\n').encode())
                    elif method == 'mining.suggest_difficulty':
                        miner.sendall((json.dumps({"id": msg['id'], "result": True, "error": None}) + '\n').encode())
                    elif method == 'mining.authorize':
                        msg['params'][0] = USER_WALLET
                        pool.sendall((json.dumps(msg) + '\n').encode())
                    elif method == 'mining.submit':
                        self.stats["shares_received"] += 1
                        self.analyze_and_route(msg, miner, pool)
                    else:
                        pool.sendall((line + '\n').encode())
            except: self.stats["errors"] += 1; break

    def downstream(self, pool, miner):
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

    def analyze_and_route(self, msg, miner, pool):
        now = time.time()
        latency = (now - self.job_start_time) * 1000.0
        
        # Berserker Selection
        is_lucky = latency < 500.0
        is_selected = random.random() < self.keep_rate
        
        if is_lucky or is_selected:
            self.stats["accepted"] += 1
            pool.sendall((json.dumps(msg) + '\n').encode())
        else:
            self.stats["killed"] += 1
            # Issue KILL (New Job)
            if self.latest_params:
                params = list(self.latest_params)
                params[0] = str(random.getrandbits(32))
                params[8] = True
                kill_msg = {"id": None, "method": "mining.notify", "params": params}
                miner.sendall((json.dumps(kill_msg) + '\n').encode())

    def get_current_speed(self, elapsed):
        total = self.stats["accepted"] + self.stats["killed"]
        return total / (elapsed / 60.0 + 1e-9)

    def get_success_rate(self):
        total = self.stats["accepted"] + self.stats["killed"] + self.stats["errors"]
        if total == 0: return 100.0
        return (1.0 - (self.stats["errors"] / total)) * 100.0

    def get_report(self, elapsed):
        total = self.stats["accepted"] + self.stats["killed"]
        return {
            "scaling": self.scaling,
            "real_speed": total / (elapsed / 60.0),
            "success_rate": self.get_success_rate(),
            "kills": self.stats["killed"],
            "shares": self.stats["shares_received"]
        }

if __name__ == "__main__":
    results = []
    for scale in [100, 200, 300, 400]:
        tester = StressTestController(scale)
        report = tester.run_60s_test()
        if report:
            results.append(report)
            print(f"STAGE COMPLETE: Speed x{report['real_speed']:.1f} | Success {report['success_rate']:.2f}%")
        else:
            print("STAGE FAILED (No Connection)")
        time.sleep(2) # Cooldown
    
    print("\n\n" + "="*40)
    print("FINAL STRESS TEST SUMMARY")
    print("="*40)
    for r in results:
        print(f"Target x{r['scaling']}: Real x{r['real_speed']:.1f} | Kills: {r['kills']} | Error: {100-r['success_rate']:.2f}%")
    print("="*40)
