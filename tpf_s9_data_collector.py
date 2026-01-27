#!/usr/bin/env python3
"""
TPF S9 DATA COLLECTOR (SYNTHETIC POOL MODE)
===========================================
Acts as a Stratum Server (Pool) for the Antminer S9.
Generates SYNTHETIC block headers at LOW DIFFICULTY to capture high-volume data.
Logs all header parameters + Timing Jitter for offline labeling.

Output: s9_training_data_raw.csv
"""

import socket
import json
import time
import csv
import os
import random
import threading
import struct
import binascii

# CONFIGURATION
LISTEN_IP = "0.0.0.0"
LISTEN_PORT = 3333
DIFFICULTY = 4  # Ultra-low difficulty for debugging
LOG_FILE = "s9_training_data_raw.csv"

def get_timestamp():
    return time.perf_counter()

class S9SyntheticPool:
    def __init__(self):
        self.sock = None
        self.conn = None
        self.running = True
        self.extranonce1 = "0000ffff"
        self.jobs = {}
        self.share_count = 0
        
        # CSV Init
        self.fieldnames = [
            "timestamp", "job_id", "jitter_ms",
            "version", "prevhash", "coinb1", "coinb2", 
            "extranonce1", "extranonce2", "merkle_branch", 
            "ntime", "nbits", "nonce"
        ]
        self._init_csv()
        
    def _init_csv(self):
        file_exists = os.path.isfile(LOG_FILE)
        with open(LOG_FILE, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.fieldnames)
            if not file_exists:
                writer.writeheader()

    def log_share(self, data):
        with open(LOG_FILE, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.fieldnames)
            writer.writerow(data)
            
    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((LISTEN_IP, LISTEN_PORT))
        self.sock.listen(1)
        print(f"[POOL] Listening on {LISTEN_IP}:{LISTEN_PORT} - Diff: {DIFFICULTY}")
        
        while self.running:
            print("[POOL] Waiting for S9...")
            self.conn, addr = self.sock.accept()
            print(f"[POOL] S9 Connected: {addr}")
            self.handle_client()

    def handle_client(self):
        self.conn.settimeout(None)
        buffer = ""
        last_job_time = 0
        
        try:
            while self.running:
                data = self.conn.recv(4096).decode('utf-8')
                if not data: break
                
                buffer += data
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if not line.strip(): continue
                    
                    try:
                        msg = json.loads(line)
                        method = msg.get('method')
                        msg_id = msg.get('id')
                        
                        # 1. SUBSCRIBE
                        if method == 'mining.subscribe':
                            print("[RECV] mining.subscribe")
                            # Result: [[ ["mining.set_difficulty", "subscription id 1"], ["mining.notify", "sub id 2"]], "extranonce1", extranonce2_size]
                            resp = {
                                "id": msg_id,
                                "result": [
                                    [["mining.set_difficulty", "1"], ["mining.notify", "2"]],
                                    self.extranonce1,
                                    4
                                ],
                                "error": None
                            }
                            self.send_json(resp)
                            
                        # 2. AUTHORIZE
                        elif method == 'mining.authorize':
                            print(f"[RECV] mining.authorize ({msg['params'][0]})")
                            resp = {"id": msg_id, "result": True, "error": None}
                            self.send_json(resp)
                            
                            # Start sending work immediately
                            self.send_difficulty(DIFFICULTY)
                            last_job_time = self.send_new_job()
                            
                        # 3. SUBMIT
                        elif method == 'mining.submit':
                            # params: ["worker_name", "job_id", "extranonce2", "ntime", "nonce"]
                            params = msg.get('params')
                            job_id = params[1]
                            arrival_time = get_timestamp()
                            
                            jitter = (arrival_time - last_job_time) * 1000
                            
                            # Process Share
                            self.process_share(params, jitter)
                            
                            # Ack
                            resp = {"id": msg_id, "result": True, "error": None}
                            self.send_json(resp)
                            
                            # Send NEW job periodically to keep Jitter clean?
                            # Or just let it mine? For TPF we want fresh "Starts" to measure Jitter from start.
                            # So every share -> New Job is good for training "Start Jitter".
                            last_job_time = self.send_new_job()
                            
                        # 4. Extranonce subscribe?
                        elif method == 'mining.extranonce.subscribe':
                            resp = {"id": msg_id, "result": True, "error": None}
                            self.send_json(resp)
                            
                    except json.JSONDecodeError:
                        print(f"[ERR] Bad JSON: {line}")
                        
        except Exception as e:
            print(f"[ERR] Connection lost: {e}")
        finally:
            if self.conn: self.conn.close()

    def send_json(self, data):
        line = json.dumps(data) + "\n"
        self.conn.sendall(line.encode())

    def send_difficulty(self, diff):
        msg = {
            "id": None,
            "method": "mining.set_difficulty",
            "params": [diff]
        }
        self.send_json(msg)

    def send_new_job(self):
        # Generate random job
        job_id = hex(random.randint(0, 999999))[2:]
        
        # Random Block Header Parts
        version = "20000000"
        prevhash = binascii.hexlify(os.urandom(32)).decode()
        coinb1 = binascii.hexlify(os.urandom(32)).decode()
        coinb2 = binascii.hexlify(os.urandom(32)).decode()
        merkle_branch = [] # Empty for simplicity (roots = coin)
        nbits = "1d00ffff" # Diff 1
        ntime = hex(int(time.time()))[2:]
        clean_jobs = True
        
        job = {
            "job_id": job_id,
            "version": version,
            "prevhash": prevhash,
            "coinb1": coinb1,
            "coinb2": coinb2,
            "merkle_branch": merkle_branch,
            "nbits": nbits,
            "ntime": ntime
        }
        self.jobs[job_id] = job
        
        # Send mining.notify
        # params: [job_id, prevhash, coinb1, coinb2, merkle_branch, version, nbits, ntime, clean_jobs]
        msg = {
            "id": None,
            "method": "mining.notify",
            "params": [
                job_id, prevhash, coinb1, coinb2, 
                merkle_branch, version, nbits, ntime, clean_jobs
            ]
        }
        self.send_json(msg)
        return get_timestamp()

    def process_share(self, params, jitter):
        # params: ["worker", "job_id", "extranonce2", "ntime", "nonce"]
        job_id = params[1]
        en2 = params[2]
        ntime = params[3]
        nonce = params[4]
        
        if job_id not in self.jobs:
            print(f"[WARN] Unknown Job ID: {job_id}")
            return
            
        job = self.jobs[job_id]
        
        # Log Logic
        self.share_count += 1
        print(f"[SHARE #{self.share_count}] Jitter: {jitter:.2f}ms | Nonce: {nonce}")
        
        row = {
            "timestamp": time.time(),
            "job_id": job_id,
            "jitter_ms": jitter,
            "version": job["version"],
            "prevhash": job["prevhash"],
            "coinb1": job["coinb1"],
            "coinb2": job["coinb2"],
            "extranonce1": self.extranonce1,
            "extranonce2": en2,
            "merkle_branch": json.dumps(job["merkle_branch"]),
            "ntime": ntime,
            "nbits": job["nbits"],
            "nonce": nonce
        }
        self.log_share(row)

if __name__ == "__main__":
    pool = S9SyntheticPool()
    pool.start()
