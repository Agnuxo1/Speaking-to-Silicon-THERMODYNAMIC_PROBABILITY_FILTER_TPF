#!/usr/bin/env python3
"""
TPF S9 LABELER
==============
Reads s9_training_data_raw.csv
Reconstructs Block Headers.
Calculates Double-SHA256 Hash.
Labels data for TPF training.

Output: tpf_s9_labeled.csv
"""

import csv
import hashlib
import binascii
import struct
import math

INPUT_FILE = "s9_training_data_raw.csv"
OUTPUT_FILE = "tpf_s9_labeled.csv"

def swap_endian_hex(hex_str):
    """Swaps endianness of a hex string (e.g., for versions, times, nonces)"""
    # Split into bytes, reverse, join
    b = binascii.unhexlify(hex_str)
    return binascii.hexlify(b[::-1]).decode()

def dsha256(data_bytes):
    return hashlib.sha256(hashlib.sha256(data_bytes).digest()).digest()

def merkle_root(coinb1, en1, en2, coinb2, branches):
    """
    Calculates Merkle Root.
    Coinbase = coinb1 + en1 + en2 + coinb2
    Root = dsha256(coinbase) (if no branches)
    """
    coinbase_hex = coinb1 + en1 + en2 + coinb2
    coinbase_bin = binascii.unhexlify(coinbase_hex)
    root = dsha256(coinbase_bin)
    
    # Process branches (Merkle Path)
    # branches is list of hex strings (32 bytes each)
    # Typically S9 receives little endian or big endian? 
    # Stratum standard: branches are LE (sent as is).
    # Hash(Root + Branch) or Hash(Branch + Root)?
    # For simplified sim, we have no branches.
    return root

def swap_endian_hex(hex_str: str) -> bytes:
    """Decodes hex and reverses bytes (Little Endian <-> Big Endian)."""
    try:
        # Standardize: make even length
        if len(hex_str) % 2 != 0: hex_str = '0' + hex_str
        b = binascii.unhexlify(hex_str)
        return b[::-1]
    except:
        return b'\x00' * (len(hex_str)//2)

def reconstruct_header(row):
    """
    Reconstructs 80-byte Block Header.
    Standard Bitcoin Header (Little Endian):
    [4B Version] [32B PrevHash] [32B MerkleRoot] [4B Time] [4B nBits] [4B Nonce]
    
    Stratum Params:
    - version: Hex string (usually BE when sent in notify?) 
    - prevhash: Hex string (usually LE in notify?)
    - ntime: Hex string (BE in submit)
    - nbits: Hex string (LE in notify?)
    - nonce: Hex string (BE in submit)
    """
    
    # Stratum V1 Spec:
    # prevhash (32B) - Little Endian (as sent in notify)
    # version (4B) - Big Endian (needs swap)
    # nbits (4B) - Little Endian (as sent in notify)
    # ntime (4B) - Big Endian (as sent in submit/notify) -> needs swap
    # nonce (4B) - Big Endian (as sent in submit) -> needs swap
    
    # 1. Version
    # My collector sent "20000000" (BE of 0x20000000). LE is 00 00 00 20.
    v_bin = swap_endian_hex(row['version'])
    
    # 2. PrevHash
    # TRY NO SWAP for PrevHash (Assume it was sent LE in my collector)
    # In my collector: prevhash = binascii.hexlify(os.urandom(32)).decode()
    # It is just 32 random bytes. 
    # Whether we treat it as LE or BE doesn't matter for validity as long as we use the SAME bytes for hashing.
    # The ASIC receives the bytes in the order sent.
    # The ASIC hashes them.
    # So we should just use unhexlify(prevhash) directly if we sent it directly.
    p_bin = binascii.unhexlify(row['prevhash'])
    
    # 3. Merkle Root
    # dsha256 outputs bytes. We use them directly.
    mr_bin = merkle_root(row['coinb1'], row['extranonce1'], row['extranonce2'], row['coinb2'], [])
    
    # 4. Time
    t_bin = swap_endian_hex(row['ntime'])
    
    # 5. nBits
    # "1d00ffff". Header expects LE. 
    # If sent as "1d00ffff", swap -> "ffff001d". 
    b_bin = swap_endian_hex(row['nbits'])
    
    # 6. Nonce
    n_bin = swap_endian_hex(row['nonce'])
    
    header = v_bin + p_bin + mr_bin + t_bin + b_bin + n_bin
    
    # Debug lengths
    if len(header) != 80:
        # Pad or truncate if needed (shouldn't happen if hex is correct length)
        # PrevHash might be missing 0s if binascii stripped?
        pass

    return header

def calculate_difficulty(hash_bytes):
    # Hash is 32 bytes.
    # Target(1) = 0x00000000FFFF....
    # Diff = MaxTarget / HashValue
    # MaxTarget ~ 2^224 - 1 (approx for Diff 1)
    
    # Hash as integer (Big Endian of the RESULTING hash)
    # The output of dsha256 is the hash.
    # To interpret as number, we interpret as LE then swap? Or BE?
    # Bitcoin Block Hash is displayed as BE, but stored LE.
    # Let's interpret as BE integer to compare with Difficulty 1 (00000000FFFF...)
    
    # Reverse to get BE (standard display format)
    hash_be = hash_bytes[::-1]
    val = int(binascii.hexlify(hash_be), 16)
    
    max_target = 0xFFFF0000000000000000000000000000000000000000000000000000
    
    if val == 0: return 0
    diff = max_target / val
    return diff

def main():
    print(f"Reading {INPUT_FILE}...")
    headers_seen = 0
    labeled_rows = []
    
    try:
        with open(INPUT_FILE, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    header = reconstruct_header(row)
                    if len(header) != 80:
                        continue
                        
                    block_hash = dsha256(header)
                    difficulty = calculate_difficulty(block_hash)
                    
                    # Labels
                    # Label 1: "High Quality" (e.g. Diff > 1024)
                    # Label 0: "Low Quality" (Diff < 1024)
                    # The S9 mines > 256. 
                    # So we split the dataset.
                    
                    label = 1 if difficulty > 1024 else 0
                    
                    labeled_rows.append({
                        "timestamp": row['timestamp'],
                        "jitter_ms": row['jitter_ms'],
                        "nonce": row['nonce'],
                        "found_difficulty": difficulty,
                        "label": label
                    })
                    
                    headers_seen += 1
                    
                except Exception as e:
                    pass
                    
    except FileNotFound:
        print("Waiting for data...")
        return

    print(f"Processed {headers_seen} shares.")
    print(f"Saving {len(labeled_rows)} labeled samples to {OUTPUT_FILE}...")
    
    with open(OUTPUT_FILE, 'w', newline='') as f:
        fieldnames = ["timestamp", "jitter_ms", "nonce", "found_difficulty", "label"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(labeled_rows)
        
    # Analyze Balance
    pos = sum(1 for r in labeled_rows if r['label'] == 1)
    print(f"Balance: {pos} Good Shares ({pos/len(labeled_rows)*100 if len(labeled_rows)>0 else 0:.1f}%)")

if __name__ == "__main__":
    main()
