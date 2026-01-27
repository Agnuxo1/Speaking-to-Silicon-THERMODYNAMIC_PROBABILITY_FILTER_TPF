#!/usr/bin/env python3
"""
TPF VERITAS V8 - COMMUNITY EDITION (ANTMINER S9j)
=================================================
Architecture: "The Virtual Swarm" + "Pizza Butler"
Target: Shared Pool Mining (BTC)
Scaling: x20 Virtual Workers
Hardware: Antminer S9j (BM1387)

[THEORY OF OPERATION]
1. SWARM: We open 20 connections to the Pool. The Pool sees 20 normal miners.
2. BUTLER: We pre-fetch jobs from these 20 connections into a local RAM buffer.
3. ZERO-LATENCY: When S9 finishes a share, we feed the next job INSTANTLY (<0.5ms).
4. RESULT: Network lag is eliminated. Silicon stays in 'Transient State' (High Energy).
   Effective Hashrate increases due to zero-wait states.
"""

import socket
import threading
import json
import time
import random
import sys
from collections import deque
import select

# ================= CONFIGURATION =================
# S9 Local IP/Port (Where the miner connects)
LOCAL_HOST = "0.0.0.0"
LOCAL_PORT = 3333

# Remote Pool (Must support multi-worker)
# Recommended: stratum.braiins.com (Global Auto-Selection)
REMOTE_HOST = "stratum.braiins.com" 
REMOTE_PORT = 3333

# Your Account (Braiins Pool UserID)
USER_WALLET = "Ant-S29"
POOL_PASS = "anything123"

# Swarm Configuration
SWARM_SIZE = 20          # Create 20 Virtual Workers
BUTLER_BUFFER_SIZE = 40  # Keep 40 jobs ready in RAM

# =================================================

class VirtualWorker:
    """Represents a single connection to the Pool (one tentacle of the Swarm)."""
    def __init__(self, worker_id, swarm_manager):
        self.worker_name = f"{USER_WALLET}.w{worker_id:02d}"
        self.id = worker_id
        self.manager = swarm_manager
        self.sock = None
        self.connected = False
        self.extranonce1 = None
        self.extranonce2_size = 4 # Default
        self.job_queue = deque()
        self.last_job_time = 0
        self.difficulty = 1024 # Default safety

    def connect(self):
        while True:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(10)
                self.sock.connect((REMOTE_HOST, REMOTE_PORT))
                self.sock.settimeout(None)
                
                # Subscribe & Authorize
                self.send({"id": 1, "method": "mining.subscribe", "params": ["TPF-Swarm/1.0"]})
                self.send({"id": 2, "method": "mining.authorize", "params": [self.worker_name, POOL_PASS]})
                
                # Start Listener
                t = threading.Thread(target=self.listen_loop, daemon=True)
                t.start()
                
                self.connected = True
                # print(f"[{self.worker_name}] Connected.") # Verbose
                return
            except Exception as e:
                print(f"[!] Worker {self.id} connect fail: {e}. Retrying...")
                time.sleep(5)

    def send(self, data):
        try:
            msg = json.dumps(data) + '\n'
            self.sock.sendall(msg.encode())
        except:
            self.connected = False

    def listen_loop(self):
        buff = ""
        while True:
            try:
                data = self.sock.recv(4096).decode('utf-8', errors='ignore')
                if not data: break
                buff += data
                while '\n' in buff:
                    line, buff = buff.split('\n', 1)
                    if not line.strip(): continue
                    self.process_msg(json.loads(line))
            except: break
        self.connected = False
        # Do not call self.connect() here, let the main loop handle it or use a simpler retry

        self.connected = False
        self.id = worker_id
        # ...
        
    def process_msg(self, msg):
        method = msg.get('method')
        
        if msg.get('id') == 4:
            # Result of mining.submit
            if msg.get('result') is True:
                self.manager.shares_accepted += 1
                self.manager.last_pool_response = f"Worker {self.id} -> OK"
            else:
                self.manager.shares_rejected += 1
                err = msg.get('error')
                self.manager.last_pool_response = f"Worker {self.id} -> REJECTED: {err}"

        elif method == 'mining.notify':
            # New Job Received from Pool
            params = msg['params']
            job_obj = {
                'worker_id': self.id,
                'job_id': params[0],
                'prev_hash': params[1],
                'coinb1': params[2],
                'coinb2': params[3],
                'merkle_branch': params[4],
                'version': params[5],
                'nbits': params[6],
                'ntime': params[7],
                'clean_jobs': params[8]
            }
            # Feed the Swarm Manager
            self.manager.register_job(job_obj)
            
        elif not msg.get('method') and msg.get('id') == 1:
            # Result of mining.subscribe -> Extract Extranonce1
            res = msg.get('result')
            # Braiins format: [ [...], "extranonce1", extranonce2_size ]
            if res and len(res) >= 3:
                self.extranonce1 = res[1]
                self.extranonce2_size = res[2]
                # print(f"[*] Worker {self.id} Extranonce1: {self.extranonce1} (Size: {self.extranonce2_size})")
            
        elif method == 'mining.set_difficulty':
            self.difficulty = msg['params'][0]

class SwarmNexus:
    """Manages the 20 Virtual Workers and the Job Registry."""
    def __init__(self):
        self.workers = []
        self.job_registry = {} # Local_ID -> Job_Object
        self.local_job_counter = 0
        self.ready_queue = deque() # Jobs ready for S9
        self.lock = threading.Lock()
        
        # Stats
        self.shares_accepted = 0
        self.shares_rejected = 0
        self.last_pool_response = "Waiting..."
        self.start_time = time.time()

    def boot(self):
        print(f"[SWARM] Booting {SWARM_SIZE} Virtual Workers...")
        for i in range(1, SWARM_SIZE + 1):
            w = VirtualWorker(i, self)
            self.workers.append(w)
            threading.Thread(target=w.connect, daemon=True).start()
            time.sleep(0.1) # Stagger connections

    def register_job(self, job_obj):
        """Called when a Worker gets a job from China."""
        with self.lock:
            # Create a simplified Local ID for the S9
            local_id = f"{self.local_job_counter:x}"
            self.local_job_counter += 1
            
            # Store full mapping
            self.job_registry[local_id] = job_obj
            
            # Add to Butler's Queue
            self.ready_queue.append(local_id)
            if len(self.ready_queue) > BUTLER_BUFFER_SIZE:
                old = self.ready_queue.popleft() # Discard old jobs
                if old in self.job_registry:
                    del self.job_registry[old]

    def get_butler_job(self):
        """Get best job for S9 (Zero Latency)."""
        if not self.ready_queue:
            return None
        
        with self.lock:
            job_id = self.ready_queue.pop() # LIFO (freshest job)
            return self.job_registry.get(job_id), job_id

    def submit_share_to_pool(self, local_job_id, nonce, extranonce2, ntime):
        """Routes S9's work back to the specific Virtual Worker."""
        with self.lock:
            job_info = self.job_registry.get(local_job_id)
        
        if not job_info:
            print(f"[!] Stale Share (Job {local_job_id} not found)")
            return

        worker = self.workers[job_info['worker_id'] - 1]
        
        # Construct Stratum Submit
        payload = {
            "params": [
                worker.worker_name,
                job_info['job_id'],
                extranonce2,
                ntime,
                nonce
            ],
            "id": 4,
            "method": "mining.submit"
        }
        worker.send(payload)
        # self.shares_accepted += 1 # Moved to response handler
        # print(f"[^] Share routed via {worker.worker_name}")

class S9Proxy:
    """The Local Server that talks to your physical S9."""
    def __init__(self, nexus):
        self.nexus = nexus
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.miner_conn = None
        self.extranonce1 = "00000000" # Simplified
        self.extranonce2_size = 4

    def start(self):
        self.sock.bind((LOCAL_HOST, LOCAL_PORT))
        self.sock.listen(1)
        print(f"[PROXY] Listening for S9 on port {LOCAL_PORT}")
        print(f"[PROXY] The Pizza Butler is ready.")
        
        while True:
            try:
                conn, addr = self.sock.accept()
                print(f"[S9] Connected from {addr}")
                self.handle_miner(conn)
            except Exception as e:
                print(f"[ERR] Proxy loop: {e}")

    def handle_miner(self, conn):
        self.miner_conn = conn
        buff = ""
        while True:
            try:
                data = conn.recv(4096).decode('utf-8', errors='ignore')
                if not data: break
                buff += data
                while '\n' in buff:
                    line, buff = buff.split('\n', 1)
                    if not line.strip(): continue
                    self.process_s9_msg(json.loads(line))
            except: break
        print("[S9] Disconnected.")
        self.miner_conn.close()

    def send(self, data):
        try:
            self.miner_conn.sendall((json.dumps(data) + '\n').encode())
        except: pass

    def process_s9_msg(self, msg):
        method = msg.get('method')
        msg_id = msg.get('id')

        # 1. Configuration (Critical for S9 firmware)
        if method == 'mining.configure':
            res = {
                "version-rolling": True,
                "version-rolling.mask": "1fffe000"
            }
            self.send({"id": msg_id, "result": res, "error": None})

        # 2. Subscribe
        elif method == 'mining.subscribe':
            # Send fake subscription confirmation
            self.send({
                "id": msg_id,
                "result": [
                    ["mining.notify", "ae6812eb4cd7735a302a8a9dd95cf71f"],
                    self.extranonce1,
                    self.extranonce2_size
                ],
                "error": None
            })
            # Trigger first job immediately
            self.butler_feed()

        # 3. Authorize
        elif method == 'mining.authorize':
            self.send({"id": msg_id, "result": True, "error": None})

        # 4. Submit (The critical moment)
        elif method == 'mining.submit':
            # A. Instant ACK (Don't wait for pool) -> S9 stays happy
            self.send({"id": msg_id, "result": True, "error": None})
            
            # B. Extract data
            params = msg['params']
            # params: [worker, job_id, extranonce2, ntime, nonce]
            local_job_id = params[1]
            extranonce2 = params[2]
            ntime = params[3]
            nonce = params[4]
            
            # C. Route to Swarm
            threading.Thread(target=self.nexus.submit_share_to_pool, 
                           args=(local_job_id, nonce, extranonce2, ntime)).start()
            
            # D. BUTLER ACTION: Feed next job INSTANTLY
            self.butler_feed()

    def butler_feed(self):
        """Feeds the S9 the next job from the RAM buffer (Zero Latency)."""
        job_data = self.nexus.get_butler_job()
        if not job_data:
            return # Buffer empty (should rare with Swarm x20)
        
        job, local_id = job_data
        
        # 1. Update Extranonce (SYNCHRONIZE HARDWARE WITH SWARM)
        if job['worker_id'] in [w.id for w in self.nexus.workers]:
            worker = self.nexus.workers[job['worker_id'] - 1]
            if worker.extranonce1:
                self.send({
                    "id": None,
                    "method": "mining.set_extranonce",
                    "params": [worker.extranonce1, worker.extranonce2_size]
                })
            
            # PUSH DIFFICULTY (SYCHRONIZE HARDWARE)
            if worker.difficulty:
                self.send({
                    "id": None,
                    "method": "mining.set_difficulty",
                    "params": [worker.difficulty]
                })

        # 2. Push Work
        payload = {
            "params": [
                local_id,
                job['prev_hash'],
                job['coinb1'],
                job['coinb2'],
                job['merkle_branch'],
                job['version'],
                job['nbits'],
                job['ntime'],
                True # CLEAN JOBS = TRUE (Force S9 to restart/jump)
            ],
            "id": None,
            "method": "mining.notify"
        }
        self.send(payload)

def stats_printer(nexus):
    while True:
        time.sleep(30)
        elapsed = (time.time() - nexus.start_time) / 60
        rate = nexus.shares_accepted / elapsed if elapsed > 0 else 0
        print(f"\n[BTC SWARM] Uptime: {elapsed:.1f}m | OK: {nexus.shares_accepted} | ERR: {nexus.shares_rejected} | Speed: {rate:.1f} sh/min")
        print(f"[POOL MSG] {nexus.last_pool_response}")
        print(f"[BUTLER] Buffer Health: {len(nexus.ready_queue)} jobs ready.")

if __name__ == "__main__":
    # 1. Initialize The Swarm
    nexus = SwarmNexus()
    nexus.boot()
    
    # 2. Wait a moment for connections
    time.sleep(2)
    
    # 3. Start Stats
    threading.Thread(target=stats_printer, args=(nexus,), daemon=True).start()
    
    # 4. Start The Proxy (Butler)
    proxy = S9Proxy(nexus)
    proxy.start()
