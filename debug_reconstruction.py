import csv
import binascii
import hashlib

def swap_endian_hex(hex_str):
    if len(hex_str) % 2 != 0: hex_str = '0' + hex_str
    b = binascii.unhexlify(hex_str)
    return b[::-1]

def dsha256(data):
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def merkle_root(coinb1, en1, en2, coinb2):
    # Coinbase = coinb1 + en1 + en2 + coinb2
    # In Stratum, these hex strings are just concatenated.
    # The result is the coinbase transaction (in bytes).
    # Then we SHA256(SHA256(coinbase)) to get the Merkle Root (for single txn block).
    
    cb_hex = coinb1 + en1 + en2 + coinb2
    cb_bin = binascii.unhexlify(cb_hex)
    mr = dsha256(cb_bin)
    return mr

with open("s9_training_data_raw.csv", 'r') as f:
    reader = csv.DictReader(f)
    row = next(reader) # Get first row
    
    print("RAW ROW:")
    for k,v in row.items():
        if k in ['version', 'prevhash', 'merkle_branch', 'ntime', 'nbits', 'nonce']:
            print(f"{k}: {v}")

    # Manual Reconstruction Debug
    ver = swap_endian_hex(row['version'])
    
    # TRY NO SWAP for PrevHash (Assume it was sent LE)
    prev = binascii.unhexlify(row['prevhash'])
    
    # Merkle Root
    mr_bin = merkle_root(row['coinb1'], row['extranonce1'], row['extranonce2'], row['coinb2'])
    
    # TRY NO SWAP for Time/Bits/Nonce? Usually these are BE in messages?
    # Stratum specs say:
    # Version: BE
    # PrevHash: LE
    # MerkleRoot: LE
    # Time: BE
    # nBits: LE
    # Nonce: BE
    
    # Previous attempt swapped everything.
    # Let's try: Swapping Version, Time, Nonce. Keeping PrevHash, Root, nBits as is.
    
    # Mr_bin is calculated from ingredients. dsha256 result is natural byte order.
    # If standard, that is BE? No, dsha256 result is just bytes.
    # Bitcoin Merkle Root field is LE.
    # So we should probably not touch mr_bin if dsha256 outputs what we think.
    # Wait, dsha256(coinbase) -> "Hash". Hash is usually displayed BE but stored LE.
    # If dsha256 returns bytes [0...31], is that LE or BE?
    # It is the "internal byte order".
    # Bitcoin Header uses "internal byte order" (LE).
    # So mr_bin is correct as is?
    
    time_b = swap_endian_hex(row['ntime'])
    bits_b = binascii.unhexlify(row['nbits']) # Trying NO SWAP
    nonce_b = swap_endian_hex(row['nonce'])
    
    header = ver + prev + mr_bin + time_b + bits_b + nonce_b
    print(f"Header ({len(header)}): {binascii.hexlify(header).decode()}")
    
    h = dsha256(header)
    print(f"Hash: {binascii.hexlify(h[::-1]).decode()}") # Display BE
    
