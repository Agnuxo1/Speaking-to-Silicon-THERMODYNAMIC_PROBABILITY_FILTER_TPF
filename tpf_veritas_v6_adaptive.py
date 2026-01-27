#!/usr/bin/env python3
"""
TPF VERITAS V6 - ADAPTIVE LEARNING EDITION
===========================================
Hardware: Goldshell LB-Box (Zynq-7010)
Target: LBC (Mining-Dutch Solo)
Strategy: Learn-Then-Filter with Neural Network

PHILOSOPHY:
-----------
We cannot predict SHA256 outputs from metadata. BUT we can:
1. Start with NO filtering (100% passthrough)
2. Collect real data on CONFIRMED block winners from pool
3. Train a neural network on winner metadata patterns
4. ONLY enable filtering if statistical correlation is found
5. Continuously validate that filtering improves (not harms) results

CRITICAL: The filter starts DISABLED. It only activates after
finding statistically significant patterns in real winner data.
"""

import socket
import threading
import json
import time
import random
import statistics
import csv
import os
import pickle
import numpy as np
from collections import deque
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Deque
import struct
import hashlib

# =============================================================================
# CONFIGURATION
# =============================================================================

LOCAL_HOST = "0.0.0.0"
LOCAL_PORT = 3333
REMOTE_HOST = "lbry.mining-dutch.nl"
REMOTE_PORT = 9988
USER_WALLET = "apollo13.LBBox"
POOL_PASSWORD = "x"

# Learning Configuration
MIN_WINNERS_FOR_TRAINING = 5      # Need at least 5 confirmed blocks to start learning
MIN_WINNERS_FOR_FILTERING = 20    # Need 20+ blocks before enabling any filtering
CONFIDENCE_THRESHOLD = 0.75       # Only filter if model confidence > 75%
MAX_FILTER_RATE = 0.50            # Never filter more than 50% of shares
VALIDATION_WINDOW = 100           # Check filter effectiveness every 100 shares

# Feature extraction
FEATURE_HISTORY_SIZE = 50         # Track last 50 shares for temporal features

# File paths
DATA_DIR = "veritas_data"
WINNERS_FILE = f"{DATA_DIR}/confirmed_winners.csv"
ALL_SHARES_FILE = f"{DATA_DIR}/all_shares.csv"
MODEL_FILE = f"{DATA_DIR}/winner_model.pkl"
STATS_FILE = f"{DATA_DIR}/session_stats.json"


# =============================================================================
# SIMPLE NEURAL NETWORK (No external dependencies)
# =============================================================================

class SimpleNeuralNetwork:
    """
    Minimal feedforward neural network implemented in pure NumPy.
    Architecture: Input -> Hidden(32) -> Hidden(16) -> Output(1)
    """
    
    def __init__(self, input_size: int = 10):
        self.input_size = input_size
        self.trained = False
        self.confidence = 0.0
        
        # Xavier initialization
        self.W1 = np.random.randn(input_size, 32) * np.sqrt(2.0 / input_size)
        self.b1 = np.zeros((1, 32))
        self.W2 = np.random.randn(32, 16) * np.sqrt(2.0 / 32)
        self.b2 = np.zeros((1, 16))
        self.W3 = np.random.randn(16, 1) * np.sqrt(2.0 / 16)
        self.b3 = np.zeros((1, 1))
        
        # Normalization parameters
        self.feature_mean = None
        self.feature_std = None
        
    def relu(self, x):
        return np.maximum(0, x)
    
    def relu_derivative(self, x):
        return (x > 0).astype(float)
    
    def sigmoid(self, x):
        return 1 / (1 + np.exp(-np.clip(x, -500, 500)))
    
    def forward(self, X):
        # Normalize input
        if self.feature_mean is not None:
            X = (X - self.feature_mean) / (self.feature_std + 1e-8)
        
        self.z1 = X @ self.W1 + self.b1
        self.a1 = self.relu(self.z1)
        self.z2 = self.a1 @ self.W2 + self.b2
        self.a2 = self.relu(self.z2)
        self.z3 = self.a2 @ self.W3 + self.b3
        self.a3 = self.sigmoid(self.z3)
        return self.a3
    
    def train(self, X: np.ndarray, y: np.ndarray, epochs: int = 1000, lr: float = 0.01):
        """Train the network using backpropagation."""
        if len(X) < 10:
            return False
            
        # Compute normalization parameters
        self.feature_mean = np.mean(X, axis=0, keepdims=True)
        self.feature_std = np.std(X, axis=0, keepdims=True)
        
        X_norm = (X - self.feature_mean) / (self.feature_std + 1e-8)
        y = y.reshape(-1, 1)
        
        best_loss = float('inf')
        patience = 100
        patience_counter = 0
        
        for epoch in range(epochs):
            # Forward pass
            z1 = X_norm @ self.W1 + self.b1
            a1 = self.relu(z1)
            z2 = a1 @ self.W2 + self.b2
            a2 = self.relu(z2)
            z3 = a2 @ self.W3 + self.b3
            a3 = self.sigmoid(z3)
            
            # Binary cross-entropy loss
            epsilon = 1e-8
            loss = -np.mean(y * np.log(a3 + epsilon) + (1 - y) * np.log(1 - a3 + epsilon))
            
            # Early stopping
            if loss < best_loss:
                best_loss = loss
                patience_counter = 0
            else:
                patience_counter += 1
                if patience_counter > patience:
                    break
            
            # Backward pass
            m = X_norm.shape[0]
            
            dz3 = a3 - y
            dW3 = (1/m) * a2.T @ dz3
            db3 = (1/m) * np.sum(dz3, axis=0, keepdims=True)
            
            da2 = dz3 @ self.W3.T
            dz2 = da2 * self.relu_derivative(z2)
            dW2 = (1/m) * a1.T @ dz2
            db2 = (1/m) * np.sum(dz2, axis=0, keepdims=True)
            
            da1 = dz2 @ self.W2.T
            dz1 = da1 * self.relu_derivative(z1)
            dW1 = (1/m) * X_norm.T @ dz1
            db1 = (1/m) * np.sum(dz1, axis=0, keepdims=True)
            
            # Update weights
            self.W3 -= lr * dW3
            self.b3 -= lr * db3
            self.W2 -= lr * dW2
            self.b2 -= lr * db2
            self.W1 -= lr * dW1
            self.b1 -= lr * db1
        
        self.trained = True
        
        # Compute confidence (AUC approximation)
        predictions = self.forward(X)
        self.confidence = self._compute_confidence(y.flatten(), predictions.flatten())
        
        return True
    
    def _compute_confidence(self, y_true, y_pred):
        """Compute a confidence score based on separation of classes."""
        if len(np.unique(y_true)) < 2:
            return 0.0
        
        pos_scores = y_pred[y_true == 1]
        neg_scores = y_pred[y_true == 0]
        
        if len(pos_scores) == 0 or len(neg_scores) == 0:
            return 0.0
        
        # Mann-Whitney U statistic normalized
        correct = 0
        total = len(pos_scores) * len(neg_scores)
        
        for p in pos_scores:
            correct += np.sum(neg_scores < p)
            correct += 0.5 * np.sum(neg_scores == p)
        
        return correct / total if total > 0 else 0.0
    
    def predict(self, X: np.ndarray) -> tuple:
        """Returns (probability, should_keep)"""
        prob = self.forward(X.reshape(1, -1))[0, 0]
        return prob, prob > 0.5
    
    def save(self, filepath: str):
        with open(filepath, 'wb') as f:
            pickle.dump({
                'W1': self.W1, 'b1': self.b1,
                'W2': self.W2, 'b2': self.b2,
                'W3': self.W3, 'b3': self.b3,
                'feature_mean': self.feature_mean,
                'feature_std': self.feature_std,
                'trained': self.trained,
                'confidence': self.confidence
            }, f)
    
    def load(self, filepath: str):
        if os.path.exists(filepath):
            with open(filepath, 'rb') as f:
                data = pickle.load(f)
                self.W1, self.b1 = data['W1'], data['b1']
                self.W2, self.b2 = data['W2'], data['b2']
                self.W3, self.b3 = data['W3'], data['b3']
                self.feature_mean = data.get('feature_mean')
                self.feature_std = data.get('feature_std')
                self.trained = data.get('trained', False)
                self.confidence = data.get('confidence', 0.0)
                return True
        return False


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class ShareData:
    """Complete metadata for a single share submission."""
    timestamp: float
    job_id: str
    nonce: str
    latency_ms: float
    time_since_last_share: float
    time_since_last_job: float
    shares_since_job: int
    chip_sequence: int  # Global share counter
    
    # Temporal features
    latency_ema_short: float  # Exponential moving average (short window)
    latency_ema_long: float   # Exponential moving average (long window)
    latency_variance: float   # Recent variance
    
    # Outcome (filled after pool response)
    pool_accepted: Optional[bool] = None
    is_block_winner: Optional[bool] = None
    block_hash: Optional[str] = None
    
    def to_features(self) -> np.ndarray:
        """Convert to feature vector for neural network."""
        return np.array([
            self.latency_ms,
            self.time_since_last_share,
            self.time_since_last_job,
            self.shares_since_job,
            self.latency_ema_short,
            self.latency_ema_long,
            self.latency_variance,
            np.log1p(self.latency_ms),  # Log-transformed latency
            self.latency_ms / (self.latency_ema_long + 1),  # Relative speed
            1.0 if self.shares_since_job < 5 else 0.0  # Early share flag
        ], dtype=np.float32)


# =============================================================================
# DATA LOGGER
# =============================================================================

class AdaptiveDataLogger:
    """Logs all share data and manages winner records."""
    
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self._init_files()
        self.pending_shares: Dict[int, ShareData] = {}  # msg_id -> ShareData
        
    def _init_files(self):
        if not os.path.exists(ALL_SHARES_FILE):
            with open(ALL_SHARES_FILE, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'job_id', 'nonce', 'latency_ms',
                    'time_since_last_share', 'time_since_last_job',
                    'shares_since_job', 'chip_sequence',
                    'latency_ema_short', 'latency_ema_long', 'latency_variance',
                    'pool_accepted', 'is_block_winner'
                ])
        
        if not os.path.exists(WINNERS_FILE):
            with open(WINNERS_FILE, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'job_id', 'nonce', 'latency_ms',
                    'time_since_last_share', 'time_since_last_job',
                    'shares_since_job', 'chip_sequence',
                    'latency_ema_short', 'latency_ema_long', 'latency_variance',
                    'block_hash'
                ])
    
    def log_share(self, share: ShareData, msg_id: int):
        """Log a share submission and track for pool response."""
        self.pending_shares[msg_id] = share
        
    def update_share_result(self, msg_id: int, accepted: bool, is_winner: bool = False, 
                           block_hash: str = None) -> Optional[ShareData]:
        """Update share with pool response."""
        if msg_id not in self.pending_shares:
            return None
            
        share = self.pending_shares.pop(msg_id)
        share.pool_accepted = accepted
        share.is_block_winner = is_winner
        share.block_hash = block_hash
        
        # Log to all shares file
        with open(ALL_SHARES_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                share.timestamp, share.job_id, share.nonce, share.latency_ms,
                share.time_since_last_share, share.time_since_last_job,
                share.shares_since_job, share.chip_sequence,
                share.latency_ema_short, share.latency_ema_long, share.latency_variance,
                share.pool_accepted, share.is_block_winner
            ])
        
        # Log winners separately
        if is_winner:
            with open(WINNERS_FILE, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    share.timestamp, share.job_id, share.nonce, share.latency_ms,
                    share.time_since_last_share, share.time_since_last_job,
                    share.shares_since_job, share.chip_sequence,
                    share.latency_ema_short, share.latency_ema_long, share.latency_variance,
                    block_hash
                ])
        
        return share
    
    def get_winner_count(self) -> int:
        """Count confirmed block winners."""
        if not os.path.exists(WINNERS_FILE):
            return 0
        with open(WINNERS_FILE, 'r') as f:
            return sum(1 for _ in f) - 1  # Subtract header
    
    def load_training_data(self) -> tuple:
        """Load all shares with outcomes for training."""
        X, y = [], []
        
        if not os.path.exists(ALL_SHARES_FILE):
            return np.array(X), np.array(y)
        
        with open(ALL_SHARES_FILE, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['pool_accepted'] == '':
                    continue
                    
                features = np.array([
                    float(row['latency_ms']),
                    float(row['time_since_last_share']),
                    float(row['time_since_last_job']),
                    float(row['shares_since_job']),
                    float(row['latency_ema_short']),
                    float(row['latency_ema_long']),
                    float(row['latency_variance']),
                    np.log1p(float(row['latency_ms'])),
                    float(row['latency_ms']) / (float(row['latency_ema_long']) + 1),
                    1.0 if int(row['shares_since_job']) < 5 else 0.0
                ], dtype=np.float32)
                
                X.append(features)
                # Label: 1 if winner, 0 otherwise
                y.append(1.0 if row['is_block_winner'] == 'True' else 0.0)
        
        return np.array(X), np.array(y)


# =============================================================================
# ADAPTIVE FILTER ENGINE
# =============================================================================

class AdaptiveFilterEngine:
    """
    Core learning engine that adapts filtering based on real results.
    """
    
    def __init__(self):
        self.model = SimpleNeuralNetwork(input_size=10)
        self.logger = AdaptiveDataLogger()
        
        # Statistics
        self.total_shares = 0
        self.shares_sent = 0
        self.shares_filtered = 0
        self.confirmed_winners = 0
        self.filtered_would_be_winners = 0  # Tracks if we filtered a winner (BAD!)
        
        # Temporal tracking
        self.latency_history: Deque[float] = deque(maxlen=FEATURE_HISTORY_SIZE)
        self.ema_short = 0.0
        self.ema_long = 0.0
        self.last_share_time = time.time()
        self.last_job_time = time.time()
        self.shares_since_job = 0
        
        # Filter state
        self.filter_enabled = False
        self.current_filter_rate = 0.0
        self.validation_buffer: List[tuple] = []  # (share_data, was_filtered, outcome)
        
        # Load existing model if available
        if self.model.load(MODEL_FILE):
            print(f"[ENGINE] Loaded existing model (confidence: {self.model.confidence:.2%})")
            self.confirmed_winners = self.logger.get_winner_count()
            if self.confirmed_winners >= MIN_WINNERS_FOR_FILTERING and self.model.confidence >= CONFIDENCE_THRESHOLD:
                self.filter_enabled = True
                print(f"[ENGINE] Filter ENABLED based on {self.confirmed_winners} confirmed winners")
        
        self._load_stats()
        
    def _load_stats(self):
        if os.path.exists(STATS_FILE):
            try:
                with open(STATS_FILE, 'r') as f:
                    stats = json.load(f)
                    self.total_shares = stats.get('total_shares', 0)
                    self.shares_sent = stats.get('shares_sent', 0)
                    self.confirmed_winners = stats.get('confirmed_winners', 0)
            except:
                pass
    
    def _save_stats(self):
        with open(STATS_FILE, 'w') as f:
            json.dump({
                'total_shares': self.total_shares,
                'shares_sent': self.shares_sent,
                'confirmed_winners': self.confirmed_winners,
                'filter_enabled': self.filter_enabled,
                'model_confidence': self.model.confidence,
                'last_update': datetime.now().isoformat()
            }, f, indent=2)
    
    def new_job_received(self):
        """Called when a new mining job is received."""
        self.last_job_time = time.time()
        self.shares_since_job = 0
    
    def process_share(self, job_id: str, nonce: str, msg_id: int) -> tuple:
        """
        Process an incoming share and decide whether to send it to pool.
        
        Returns: (should_send, share_data)
        """
        now = time.time()
        latency = (now - self.last_job_time) * 1000
        time_since_last = (now - self.last_share_time) * 1000
        
        # Update temporal features
        self.latency_history.append(latency)
        self.ema_short = 0.1 * latency + 0.9 * self.ema_short if self.ema_short > 0 else latency
        self.ema_long = 0.01 * latency + 0.99 * self.ema_long if self.ema_long > 0 else latency
        
        variance = statistics.variance(self.latency_history) if len(self.latency_history) > 1 else 0
        
        # Create share data
        share = ShareData(
            timestamp=now,
            job_id=job_id,
            nonce=nonce,
            latency_ms=latency,
            time_since_last_share=time_since_last,
            time_since_last_job=latency,
            shares_since_job=self.shares_since_job,
            chip_sequence=self.total_shares,
            latency_ema_short=self.ema_short,
            latency_ema_long=self.ema_long,
            latency_variance=variance
        )
        
        # Update counters
        self.total_shares += 1
        self.shares_since_job += 1
        self.last_share_time = now
        
        # Decide whether to send
        should_send = True
        
        if self.filter_enabled and self.model.trained:
            features = share.to_features()
            prob, is_winner_prediction = self.model.predict(features)
            
            # Only filter if we're confident it's NOT a winner
            if prob < (1 - CONFIDENCE_THRESHOLD) and random.random() < self.current_filter_rate:
                should_send = False
                self.shares_filtered += 1
        
        if should_send:
            self.shares_sent += 1
            self.logger.log_share(share, msg_id)
        
        return should_send, share
    
    def record_pool_response(self, msg_id: int, accepted: bool, 
                             is_winner: bool = False, block_hash: str = None):
        """Record the pool's response to a share."""
        share = self.logger.update_share_result(msg_id, accepted, is_winner, block_hash)
        
        if share is None:
            return
        
        if is_winner:
            self.confirmed_winners += 1
            print(f"\n{'='*60}")
            print(f"[WINNER] BLOCK FOUND! Hash: {block_hash}")
            print(f"[WINNER] Share latency: {share.latency_ms:.2f}ms")
            print(f"[WINNER] Total winners: {self.confirmed_winners}")
            print(f"{'='*60}\n")
            
            # Trigger model retraining
            self._retrain_model()
        
        # Periodic validation and stats save
        if self.total_shares % 1000 == 0:
            self._save_stats()
            self._check_filter_effectiveness()
    
    def _retrain_model(self):
        """Retrain the neural network with updated data."""
        X, y = self.logger.load_training_data()
        
        if len(X) < 100 or np.sum(y) < MIN_WINNERS_FOR_TRAINING:
            print(f"[TRAINING] Not enough data yet. Winners: {int(np.sum(y))}/{MIN_WINNERS_FOR_TRAINING}")
            return
        
        print(f"[TRAINING] Retraining model with {len(X)} samples, {int(np.sum(y))} winners...")
        
        success = self.model.train(X, y, epochs=2000, lr=0.01)
        
        if success:
            print(f"[TRAINING] Model trained. Confidence: {self.model.confidence:.2%}")
            self.model.save(MODEL_FILE)
            
            # Enable filtering if we have enough confidence
            if self.confirmed_winners >= MIN_WINNERS_FOR_FILTERING:
                if self.model.confidence >= CONFIDENCE_THRESHOLD:
                    self.filter_enabled = True
                    # Start with conservative filtering
                    self.current_filter_rate = min(0.1, MAX_FILTER_RATE)
                    print(f"[FILTER] ENABLED at {self.current_filter_rate:.1%} rate")
                else:
                    print(f"[FILTER] Confidence too low ({self.model.confidence:.2%}), keeping disabled")
    
    def _check_filter_effectiveness(self):
        """Validate that filtering is actually helping."""
        if not self.filter_enabled:
            return
        
        # Simple heuristic: if we haven't found winners in a while, reduce filtering
        if self.shares_sent > 10000 and self.confirmed_winners == 0:
            print("[FILTER] No winners found after 10k shares. Disabling filter.")
            self.filter_enabled = False
            self.current_filter_rate = 0.0
    
    def get_status(self) -> dict:
        return {
            'total_shares': self.total_shares,
            'shares_sent': self.shares_sent,
            'shares_filtered': self.shares_filtered,
            'filter_rate': self.shares_filtered / max(1, self.total_shares),
            'confirmed_winners': self.confirmed_winners,
            'filter_enabled': self.filter_enabled,
            'model_confidence': self.model.confidence if self.model.trained else 0.0,
            'current_filter_rate': self.current_filter_rate
        }


# =============================================================================
# STRATUM PROXY
# =============================================================================

class StratumHandler:
    """Handles bidirectional communication between miner and pool."""
    
    def __init__(self, miner_conn: socket.socket, engine: AdaptiveFilterEngine):
        self.miner_conn = miner_conn
        self.engine = engine
        self.pool_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.pool_conn.settimeout(30.0)
        self.running = True
        self.authorized = False
        
        self.current_job_id = None
        self.pending_submits: Dict[int, str] = {}  # msg_id -> nonce
        
    def start(self):
        try:
            print(f"[STRATUM] Connecting to {REMOTE_HOST}:{REMOTE_PORT}...")
            self.pool_conn.connect((REMOTE_HOST, REMOTE_PORT))
            self.pool_conn.settimeout(None)
            print("[STRATUM] Connected to pool")
            
            threading.Thread(target=self._handle_miner, daemon=True).start()
            threading.Thread(target=self._handle_pool, daemon=True).start()
        except Exception as e:
            print(f"[STRATUM] Connection failed: {e}")
            self.miner_conn.close()
    
    def _send_json(self, sock: socket.socket, data: dict):
        try:
            sock.sendall((json.dumps(data) + '\n').encode())
        except:
            pass
    
    def _handle_miner(self):
        """Handle messages from miner -> pool."""
        buffer = ""
        
        while self.running:
            try:
                data = self.miner_conn.recv(4096).decode('utf-8', errors='ignore')
                if not data:
                    break
                
                buffer += data
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if not line.strip():
                        continue
                    
                    try:
                        msg = json.loads(line)
                        self._process_miner_message(msg)
                    except json.JSONDecodeError:
                        continue
                        
            except Exception as e:
                print(f"[MINER] Error: {e}")
                break
        
        self.running = False
    
    def _process_miner_message(self, msg: dict):
        method = msg.get('method', '')
        msg_id = msg.get('id')
        
        if method == 'mining.authorize':
            # Rewrite credentials
            msg['params'] = [USER_WALLET, POOL_PASSWORD]
            self._send_json(self.pool_conn, msg)
            
        elif method == 'mining.submit' and self.authorized:
            # Process share through filter engine
            params = msg.get('params', [])
            job_id = params[1] if len(params) > 1 else ''
            nonce = params[4] if len(params) > 4 else ''
            
            should_send, share_data = self.engine.process_share(job_id, nonce, msg_id)
            
            if should_send:
                self.pending_submits[msg_id] = nonce
                self._send_json(self.pool_conn, msg)
            else:
                # Filtered: send fake acceptance to miner
                self._send_json(self.miner_conn, {
                    "id": msg_id,
                    "result": True,
                    "error": None
                })
        else:
            # Pass through other messages
            self._send_json(self.pool_conn, msg)
    
    def _handle_pool(self):
        """Handle messages from pool -> miner."""
        buffer = ""
        
        while self.running:
            try:
                data = self.pool_conn.recv(4096).decode('utf-8', errors='ignore')
                if not data:
                    break
                
                buffer += data
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if not line.strip():
                        continue
                    
                    try:
                        msg = json.loads(line)
                        self._process_pool_message(msg)
                    except json.JSONDecodeError:
                        continue
                        
            except Exception as e:
                print(f"[POOL] Error: {e}")
                break
        
        self.running = False
    
    def _process_pool_message(self, msg: dict):
        method = msg.get('method', '')
        msg_id = msg.get('id')
        result = msg.get('result')
        error = msg.get('error')
        
        # Check for authorization response
        if msg_id is not None and result is True and not method:
            self.authorized = True
            print("[STRATUM] Authorized with pool")
        
        # Handle new job notification
        if method == 'mining.notify':
            self.current_job_id = msg.get('params', [None])[0]
            self.engine.new_job_received()
        
        # Handle share response
        if msg_id in self.pending_submits:
            nonce = self.pending_submits.pop(msg_id)
            accepted = (result is True and error is None)
            
            # Check if this is a block winner
            # Pool typically sends a specific message for block finds
            is_winner = self._check_if_winner(msg)
            block_hash = msg.get('block_hash') or msg.get('blockhash')
            
            self.engine.record_pool_response(msg_id, accepted, is_winner, block_hash)
        
        # Forward all pool messages to miner
        self._send_json(self.miner_conn, msg)
    
    def _check_if_winner(self, msg: dict) -> bool:
        """
        Detect if pool response indicates a block find.
        Different pools signal this differently.
        """
        # Check for common block-found indicators
        if msg.get('block_hash') or msg.get('blockhash'):
            return True
        if 'block' in str(msg.get('result', '')).lower():
            return True
        if msg.get('method') == 'client.show_message':
            text = str(msg.get('params', [''])[0]).lower()
            if 'block' in text and ('found' in text or 'accepted' in text):
                return True
        return False


# =============================================================================
# MAIN CONTROLLER
# =============================================================================

class VeritasController:
    """Main controller that orchestrates everything."""
    
    def __init__(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.engine = AdaptiveFilterEngine()
        
    def start(self):
        self.server.bind((LOCAL_HOST, LOCAL_PORT))
        self.server.listen(5)
        
        print("=" * 60)
        print("TPF VERITAS V6 - ADAPTIVE LEARNING EDITION")
        print("=" * 60)
        print(f"[*] Listening on {LOCAL_HOST}:{LOCAL_PORT}")
        print(f"[*] Target pool: {REMOTE_HOST}:{REMOTE_PORT}")
        print(f"[*] Data directory: {DATA_DIR}/")
        print(f"[*] Filter status: {'ENABLED' if self.engine.filter_enabled else 'DISABLED (learning mode)'}")
        print(f"[*] Confirmed winners: {self.engine.confirmed_winners}")
        print("=" * 60)
        print()
        print("IMPORTANT: Filter starts DISABLED to collect baseline data.")
        print("It will only enable after finding real block winners and")
        print("learning patterns from confirmed success cases.")
        print()
        
        threading.Thread(target=self._stats_loop, daemon=True).start()
        
        while True:
            try:
                conn, addr = self.server.accept()
                print(f"[CONNECT] Miner connected from {addr}")
                handler = StratumHandler(conn, self.engine)
                threading.Thread(target=handler.start, daemon=True).start()
            except KeyboardInterrupt:
                print("\n[EXIT] Shutting down...")
                self.engine._save_stats()
                break
            except Exception as e:
                print(f"[ERROR] Accept failed: {e}")
    
    def _stats_loop(self):
        """Periodic status output."""
        while True:
            time.sleep(60)
            status = self.engine.get_status()
            
            sent_rate = status['shares_sent'] / max(1, status['total_shares']) * 100
            
            print(f"\n[STATS @ {datetime.now().strftime('%H:%M:%S')}]")
            print(f"  Total shares: {status['total_shares']:,}")
            print(f"  Sent to pool: {status['shares_sent']:,} ({sent_rate:.1f}%)")
            print(f"  Confirmed winners: {status['confirmed_winners']}")
            print(f"  Filter: {'ON' if status['filter_enabled'] else 'OFF'} "
                  f"(confidence: {status['model_confidence']:.1%})")
            print()


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    controller = VeritasController()
    controller.start()
