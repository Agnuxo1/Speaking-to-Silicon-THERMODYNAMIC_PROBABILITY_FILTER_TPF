#!/usr/bin/env python3
import socket
import threading
import json
import time
import sys

# CONFIGURATION
LOCAL_PORT = 8888
REMOTE_HOST = "lbry.mining-dutch.nl"
REMOTE_PORT = 9988

def start_proxy():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(("0.0.0.0", LOCAL_PORT))
        server.listen(5)
        print(f"[*] LBC Vanilla Proxy listening on 0.0.0.0:{LOCAL_PORT}")
        print(f"[*] Point ASIC to: stratum+tcp://192.168.0.11:{LOCAL_PORT}")
    except Exception as e:
        print(f"[!] Bind failed: {e}")
        sys.exit(1)
    
    while True:
        try:
            conn, addr = server.accept()
            print(f"[*] ASIC connected from {addr}")
            threading.Thread(target=handle_asic, args=(conn,), daemon=True).start()
        except Exception as e:
            print(f"[!] Accept error: {e}")

def handle_asic(asic_sock):
    try:
        pool_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        pool_sock.settimeout(10)
        pool_sock.connect((REMOTE_HOST, REMOTE_PORT))
        pool_sock.settimeout(None)
        print("[+] Connected to Pool")
    except Exception as e:
        print(f"[!] Pool connection failed: {e}")
        asic_sock.close()
        return

    # Thread: Pool -> ASIC
    def pool_to_asic():
        buffer = ""
        try:
            while True:
                data = pool_sock.recv(8192).decode('utf-8', errors='ignore')
                if not data: break
                buffer += data
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line.strip():
                        print(f" [POOL -> ASIC] {line}")
                        asic_sock.sendall((line + '\n').encode())
        except Exception as e:
            print(f"[-] Pool relay error: {e}")
        finally:
            print("[-] Pool disconnected")
            try: asic_sock.close()
            except: pass

    threading.Thread(target=pool_to_asic, daemon=True).start()

    # Thread: ASIC -> Pool
    buffer = ""
    try:
        while True:
            data = asic_sock.recv(8192).decode('utf-8', errors='ignore')
            if not data: break
            buffer += data
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                if line.strip():
                    print(f" [ASIC -> POOL] {line}")
                    pool_sock.sendall((line + '\n').encode())
    except Exception as e:
        print(f"[-] ASIC relay error: {e}")
    finally:
        print("[-] ASIC disconnected")
        try: pool_sock.close()
        except: pass

if __name__ == "__main__":
    try:
        start_proxy()
    except KeyboardInterrupt:
        print("\n[!] Shutting down...")
        sys.exit(0)
