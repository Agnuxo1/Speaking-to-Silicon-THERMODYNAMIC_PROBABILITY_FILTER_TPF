#!/usr/bin/env python3
"""
TPF DRIVER (SWH EDITION)
========================
Thermodynamic Probability Filter - Hardware Driver
Device: Antminer S9 / Lucky Miner LV06
Protocol: Single-Word Handshake (SWH)

This driver connects to the ASIC and treats it as a peripheral device.
It exposes an API to request 'Entropy Samples' (Thermodynamic Inferences)
on demand, using the precise timing/bit-pattern protocol validated in Phase 17.
"""

import socket
import json
import time
import struct
import numpy as np
from dataclasses import dataclass

# =============================================================================
# LOW LEVEL STRATUM HELPERS
# =============================================================================
def create_coinbase_parts(signature=b'TPF_DRIVER_V1'):
    # Standard Coinbase Generation
    version = struct.pack('<I', 1)
    input_count = bytes([1])
    prev_tx = bytes(32)
    prev_index = bytes.fromhex('ffffffff')
    height_bytes = bytes([1, 1]) # Dummy height
    
    # Injection of TPF Signature
    prefix_data = b'/' + signature + b'/'
    script_prefix = height_bytes + prefix_data
    
    script_suffix = b'/ENTROPY_SAMPLE/' 
    script_len = len(script_prefix) + 8 + len(script_suffix) 
    
    sequence = bytes.fromhex('ffffffff')
    output_count = bytes([1])
    output_value = struct.pack('<Q', 0) # Zero value (Data Only)
    
    marker = b'THERMODYNAMIC'
    output_script = bytes([0x6a, len(marker)]) + marker
    output_script_len = bytes([len(output_script)])
    locktime = bytes(4)
    
    coinb1 = (version + input_count + prev_tx + prev_index + bytes([script_len]) + script_prefix)
    coinb2 = (script_suffix + sequence + output_count + output_value + output_script_len + output_script + locktime)
    
    return (coinb1.hex(), coinb2.hex())

def hex_to_bits(hex_str):
    try:
        val = int(hex_str, 16)
        bits = [int(x) for x in f"{val:032b}"]
        return np.array(bits, dtype=float)
    except:
        return np.zeros(32)

@dataclass
class TPFConfig:
    MINER_IP: str = "192.168.0.16" # S9 Default
    LOCAL_PORT: int = 3333
    TIMEOUT: float = 5.0 # Seconds (S9 is fast, 5s is plenty)
    DIFFICULTY: float = 128.0 # Base Difficulty for S9 (13.5 TH/s)

class TPFDriver:
    def __init__(self, config: TPFConfig):
        self.config = config
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", config.LOCAL_PORT))
        self.sock.listen(1)
        self.conn = None
        self.c1, self.c2 = create_coinbase_parts()
        self.job_counter = 0

    def wait_for_connection(self):
        """Blocks until Miner connects"""
        local_ip = socket.gethostbyname(socket.gethostname())
        print(f"[TPF] Driver listening on {local_ip}:{self.config.LOCAL_PORT}")
        print(f"--> Point your ASIC (Miner Configuration) to this IP!")
        
        self.conn, addr = self.sock.accept()
        print(f"[TPF] ASIC Connected: {addr}")
        self.conn.settimeout(None)
        
        # Handshake Loop
        buffer = ""
        while True:
            data = self.conn.recv(1024).decode('utf-8', errors='ignore')
            buffer += data
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                try:
                    msg = json.loads(line)
                    method = msg.get('method')
                    
                    if method == 'mining.subscribe':
                        self._send({"id": msg['id'], "result": [[["mining.set_difficulty", "1"], ["mining.notify", "1"]], "00000000", 4], "error": None})
                    
                    elif method == 'mining.configure':
                        self._send({"id": msg['id'], "result": {"version-rolling": True, "version-rolling.mask": "ffffffff"}, "error": None})
                    
                    elif method == 'mining.authorize':
                        self._send({"id": msg['id'], "result": True, "error": None})
                        print("[TPF] Handshake Complete. Device Ready.")
                        return # Operational
                        
                    elif method == 'mining.suggest_difficulty':
                        pass # Ignore
                except:
                    pass

    def _send(self, data):
        if self.conn:
            self.conn.sendall((json.dumps(data) + '\n').encode())

    def get_entropy_sample(self, input_val: float):
        """
        Sends a stimulus (input_val) and captures the precise thermodynamic response.
        Returns: {latency_ms, nonce_bits, difficulty_response}
        """
        self.job_counter += 1
        job_id = f"{self.job_counter:04x}"
        
        # Modulate Difficulty based on Input (TPF Logic)
        # Higher input -> Lower Difficulty sensitivity? This can be tuned.
        # For now, we use a simple inverse modulation used in resonant experiments.
        D = self.config.DIFFICULTY / (input_val + 0.1)
        
        # 1. Send Difficulty
        self._send({"id": None, "method": "mining.set_difficulty", "params": [D]})
        
        # 2. Send Job (Stimulus)
        ntime = hex(int(time.time()))[2:]
        params = [job_id, "00"*32, self.c1, self.c2, [], "20000000", "1d00ffff", ntime, True]
        t_sent = time.perf_counter()
        self._send({"id": None, "method": "mining.notify", "params": params})
        
        # 3. Wait for ONE Share (Response)
        self.conn.settimeout(0.1)
        start_wait = time.perf_counter()
        
        while time.perf_counter() - start_wait < self.config.TIMEOUT:
            try:
                data = self.conn.recv(4096).decode('utf-8', errors='ignore')
                for line in data.split('\n'):
                    if not line: continue
                    try:
                        msg = json.loads(line)
                        if msg.get('method') == 'mining.submit':
                            # Capture Receipt Time
                            t_recv = time.perf_counter()
                            
                            # Parse Payload
                            p = msg.get('params', [])
                            share_job = p[1]
                            nonce_hex = p[4]
                            
                            # ACK
                            self._send({"id": msg['id'], "result": True, "error": None})
                            
                            if share_job == job_id:
                                # SUCCESS: Valid Sample
                                latency = (t_recv - t_sent) * 1000.0
                                bits = hex_to_bits(nonce_hex)
                                return {
                                    "success": True,
                                    "latency_ms": latency,
                                    "nonce_bits": bits.tolist(),
                                    "input": input_val,
                                    "difficulty": D
                                }
                    except: pass
            except socket.timeout: continue
            except Exception as e:
                # print(e)
                break
        
        # Timeout / Failure
        return {
            "success": False,
            "latency_ms": self.config.TIMEOUT * 1000,
            "nonce_bits": [0]*32,
            "input": input_val,
            "difficulty": D
        }

    def close(self):
        if self.conn: self.conn.close()
        if self.sock: self.sock.close()

# TEST HARNESS
if __name__ == "__main__":
    # Example Usage
    conf = TPFConfig(LOCAL_PORT=3333, DIFFICULTY=128.0) # S9 Settings
    driver = TPFDriver(conf)
    
    try:
        driver.wait_for_connection()
        print("\n[TPF] Starting Sampling Loop...")
        
        for i in range(10):
            u = np.random.random()
            sample = driver.get_entropy_sample(u)
            status = "VALID" if sample['success'] else "TIMEOUT"
            print(f"Sample {i}: {status} | Latency: {sample['latency_ms']:.1f}ms | D: {int(sample['difficulty'])}")
            time.sleep(0.1) # Stability pause
            
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        driver.close()
