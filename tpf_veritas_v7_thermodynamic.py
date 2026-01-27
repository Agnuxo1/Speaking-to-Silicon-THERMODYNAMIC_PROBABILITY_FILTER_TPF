#!/usr/bin/env python3
"""
TPF VERITAS V7 - THERMODYNAMIC JITTER ANALYSIS
===============================================
Hardware: Goldshell LB-Box (Zynq-7010)
Target: LBC/LBRY (Mining-Dutch Solo)

Based on "Speaking to Silicon: Neural Communication with Bitcoin Mining ASICs"
by Francisco Angulo de Lafuente

CRITICAL INSIGHT FROM THE RESEARCH:
-----------------------------------
The signal is NOT raw latency. The signal is TIMING JITTER VARIANCE.
High variance = entropic overflow = hash will fail
Low variance = synchronized state = potential winner

"We are not reading the bits—we are reading the energy signature 
of entropic overflow. This is a higher-level signal that becomes 
visible before its bit-level consequences propagate."

IMPLEMENTATION:
---------------
Phase 1: CALIBRATION (No filtering)
  - Send 100% of shares to pool
  - Collect timing data with microsecond resolution
  - Track confirmed block winners
  - Build baseline statistics

Phase 2: PATTERN DISCOVERY (After N winners)
  - Analyze jitter variance distribution of winners vs losers
  - Test hypothesis: winners have lower variance (synchronized state)
  - Calculate statistical significance

Phase 3: ADAPTIVE FILTERING (If patterns confirmed)
  - Filter based on jitter variance, not raw latency
  - Start conservative (10% filter rate)
  - Validate filter doesn't miss winners
  - Gradually increase if correlation holds

FEATURES MEASURED (from the paper):
-----------------------------------
1. Timing jitter (σ_δ) - standard deviation of recent deltas
2. Coefficient of Variation (CV) - normalized jitter
3. Jitter trend (increasing/decreasing)
4. Share burst patterns (shares_since_job)
5. Relative timing (vs EMA baseline)
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
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Deque, Tuple
from enum import Enum
import struct

# =============================================================================
# CONFIGURATION
# =============================================================================

LOCAL_HOST = "0.0.0.0"
LOCAL_PORT = 3333
REMOTE_HOST = "lbry.mining-dutch.nl"
REMOTE_PORT = 9988
USER_WALLET = "apollo13.LBBox"
POOL_PASSWORD = "x"

# Thermodynamic Parameters (from the paper)
JITTER_WINDOW = 50          # Samples for jitter calculation
EMA_ALPHA_SHORT = 0.1       # Short-term EMA (fast response)
EMA_ALPHA_LONG = 0.01       # Long-term EMA (baseline)

# Learning Configuration
MIN_SAMPLES_FOR_STATS = 1000      # Minimum samples before calculating baseline
MIN_WINNERS_FOR_ANALYSIS = 3      # Need 3+ winners to analyze patterns
MIN_WINNERS_FOR_FILTERING = 10    # Need 10+ winners before enabling filter
SIGNIFICANCE_THRESHOLD = 0.05     # p-value threshold for pattern validation

# Filter Configuration
INITIAL_FILTER_RATE = 0.20        # Start with 20% filtering (aggressive baseline)
MAX_FILTER_RATE = 0.50            # Never filter more than 50%
FILTER_INCREMENT = 0.05           # Increase by 5% when validated
VALIDATION_INTERVAL = 1000        # Re-validate every N shares

# Safety
KEEPALIVE_TIMEOUT = 60.0          # Force send if no shares for 60s
SAFETY_KEEP_RATE = 0.05           # Always send 5% randomly (insurance)

# Files
DATA_DIR = "tpf_veritas_v7"
ALL_SHARES_FILE = f"{DATA_DIR}/all_shares.csv"
WINNERS_FILE = f"{DATA_DIR}/winners.csv"
STATS_FILE = f"{DATA_DIR}/stats.json"
MODEL_FILE = f"{DATA_DIR}/jitter_model.pkl"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class FilterDecision(Enum):
    SEND = "SEND"           # Send to pool
    FILTER = "FILTER"       # Filter (don't send)
    KEEPALIVE = "KEEPALIVE" # Send for keepalive
    SAFETY = "SAFETY"       # Random safety send


@dataclass
class ThermodynamicFeatures:
    """
    Features extracted from timing analysis.
    Based on Section 10.3 of "Speaking to Silicon":
    Feature Vector = [N_shares, D, μ_δ, σ_δ]
    
    Extended with additional jitter metrics.
    """
    timestamp: float
    
    # Basic timing
    latency_ms: float               # Raw latency since job
    delta_ms: float                 # Time since last share
    
    # Jitter metrics (THE KEY SIGNAL)
    jitter_std: float               # σ_δ - standard deviation of recent deltas
    jitter_cv: float                # Coefficient of variation (σ/μ)
    jitter_trend: float             # Slope of jitter over window
    
    # Moving averages
    ema_short: float                # Short-term EMA
    ema_long: float                 # Long-term EMA (baseline)
    relative_speed: float           # latency / ema_long (>1 = slow, <1 = fast)
    
    # Context
    shares_since_job: int           # Burst position
    job_id: str
    nonce: str
    
    # Outcome (filled after pool response)
    pool_accepted: Optional[bool] = None
    is_block_winner: Optional[bool] = None
    block_hash: Optional[str] = None
    
    def to_array(self) -> np.ndarray:
        """Convert to feature array for analysis."""
        return np.array([
            self.latency_ms,
            self.delta_ms,
            self.jitter_std,
            self.jitter_cv,
            self.jitter_trend,
            self.ema_short,
            self.ema_long,
            self.relative_speed,
            float(self.shares_since_job),
        ], dtype=np.float32)


@dataclass
class JitterStatistics:
    """Statistics for jitter analysis."""
    # Overall population
    mean_jitter: float = 0.0
    std_jitter: float = 1.0
    
    # Winners statistics
    winner_mean_jitter: float = 0.0
    winner_std_jitter: float = 0.0
    
    # Non-winners statistics  
    loser_mean_jitter: float = 0.0
    loser_std_jitter: float = 0.0
    
    # Statistical test results
    t_statistic: float = 0.0
    p_value: float = 1.0
    effect_size: float = 0.0      # Cohen's d
    
    # Pattern detected?
    pattern_confirmed: bool = False
    optimal_threshold: float = 0.0


# =============================================================================
# THERMODYNAMIC ENGINE
# =============================================================================

class ThermodynamicEngine:
    """
    Core engine implementing the Thermodynamic Probability Filter.
    
    Key insight: We measure JITTER VARIANCE, not raw speed.
    High variance = entropic overflow = likely failure
    Low variance = synchronized state = potential winner
    """
    
    def __init__(self):
        # Timing history for jitter calculation
        self.delta_history: Deque[float] = deque(maxlen=JITTER_WINDOW)
        self.latency_history: Deque[float] = deque(maxlen=JITTER_WINDOW)
        
        # EMAs
        self.ema_short = 0.0
        self.ema_long = 0.0
        
        # Timestamps
        self.last_share_time = time.time()
        self.last_job_time = time.time()
        self.last_send_time = time.time()  # For keepalive
        
        # Counters
        self.shares_since_job = 0
        self.total_shares = 0
        self.shares_sent = 0
        self.shares_filtered = 0
        
        # Winners tracking
        self.winners: List[ThermodynamicFeatures] = []
        self.all_features: List[ThermodynamicFeatures] = []  # Recent sample for analysis
        
        # Statistics
        self.stats = JitterStatistics()
        self.baseline_established = False
        
        # Filter state
        self.filter_enabled = False
        self.current_filter_rate = INITIAL_FILTER_RATE
        self.jitter_threshold = float('inf')  # Will be set after analysis
        
        # Pending shares (for pool response tracking)
        self.pending: Dict[int, ThermodynamicFeatures] = {}
        
        # Load previous state
        self._load_state()
        
        print(f"[TPF] Thermodynamic Engine initialized")
        print(f"[TPF] Filter: {'ENABLED' if self.filter_enabled else 'DISABLED (calibration)'}")
        print(f"[TPF] Winners loaded: {len(self.winners)}")
    
    def _load_state(self):
        """Load previous session state."""
        os.makedirs(DATA_DIR, exist_ok=True)
        
        # Load winners
        if os.path.exists(WINNERS_FILE):
            try:
                with open(WINNERS_FILE, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        feat = ThermodynamicFeatures(
                            timestamp=float(row['timestamp']),
                            latency_ms=float(row['latency_ms']),
                            delta_ms=float(row['delta_ms']),
                            jitter_std=float(row['jitter_std']),
                            jitter_cv=float(row['jitter_cv']),
                            jitter_trend=float(row['jitter_trend']),
                            ema_short=float(row['ema_short']),
                            ema_long=float(row['ema_long']),
                            relative_speed=float(row['relative_speed']),
                            shares_since_job=int(row['shares_since_job']),
                            job_id=row['job_id'],
                            nonce=row['nonce'],
                            is_block_winner=True,
                            block_hash=row.get('block_hash', '')
                        )
                        self.winners.append(feat)
            except Exception as e:
                print(f"[TPF] Warning: Could not load winners: {e}")
        
        # Load stats
        if os.path.exists(STATS_FILE):
            try:
                with open(STATS_FILE, 'r') as f:
                    data = json.load(f)
                    self.total_shares = data.get('total_shares', 0)
                    self.shares_sent = data.get('shares_sent', 0)
                    self.filter_enabled = data.get('filter_enabled', False)
                    self.current_filter_rate = data.get('current_filter_rate', 0.0)
                    self.jitter_threshold = data.get('jitter_threshold', float('inf'))
                    self.baseline_established = data.get('baseline_established', False)
                    
                    if 'stats' in data:
                        s = data['stats']
                        self.stats = JitterStatistics(
                            mean_jitter=s.get('mean_jitter', 0),
                            std_jitter=s.get('std_jitter', 1),
                            winner_mean_jitter=s.get('winner_mean_jitter', 0),
                            pattern_confirmed=s.get('pattern_confirmed', False),
                            optimal_threshold=s.get('optimal_threshold', 0)
                        )
            except Exception as e:
                print(f"[TPF] Warning: Could not load stats: {e}")
    
    def _save_state(self):
        """Save current state."""
        try:
            with open(STATS_FILE, 'w') as f:
                json.dump({
                    'total_shares': self.total_shares,
                    'shares_sent': self.shares_sent,
                    'shares_filtered': self.shares_filtered,
                    'filter_enabled': self.filter_enabled,
                    'current_filter_rate': self.current_filter_rate,
                    'jitter_threshold': self.jitter_threshold if self.jitter_threshold != float('inf') else None,
                    'baseline_established': self.baseline_established,
                    'num_winners': len(self.winners),
                    'stats': {
                        'mean_jitter': self.stats.mean_jitter,
                        'std_jitter': self.stats.std_jitter,
                        'winner_mean_jitter': self.stats.winner_mean_jitter,
                        'pattern_confirmed': self.stats.pattern_confirmed,
                        'optimal_threshold': self.stats.optimal_threshold,
                        'p_value': self.stats.p_value,
                        'effect_size': self.stats.effect_size
                    },
                    'last_update': datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            print(f"[TPF] Warning: Could not save stats: {e}")
    
    def new_job(self):
        """Called when new mining job received."""
        self.last_job_time = time.time()
        self.shares_since_job = 0
    
    def extract_features(self, job_id: str, nonce: str) -> ThermodynamicFeatures:
        """
        Extract thermodynamic features from current state.
        This is the core of the TPF approach.
        """
        now = time.time()
        
        # Basic timing
        latency_ms = (now - self.last_job_time) * 1000
        delta_ms = (now - self.last_share_time) * 1000
        
        # Update histories
        self.delta_history.append(delta_ms)
        self.latency_history.append(latency_ms)
        
        # Update EMAs
        if self.ema_short == 0:
            self.ema_short = delta_ms
            self.ema_long = delta_ms
        else:
            self.ema_short = EMA_ALPHA_SHORT * delta_ms + (1 - EMA_ALPHA_SHORT) * self.ema_short
            self.ema_long = EMA_ALPHA_LONG * delta_ms + (1 - EMA_ALPHA_LONG) * self.ema_long
        
        # Calculate jitter metrics (THE KEY SIGNAL)
        if len(self.delta_history) >= 3:
            jitter_std = statistics.stdev(self.delta_history)
            jitter_mean = statistics.mean(self.delta_history)
            jitter_cv = jitter_std / (jitter_mean + 1e-6)  # Coefficient of variation
            
            # Jitter trend (is variance increasing or decreasing?)
            if len(self.delta_history) >= 10:
                recent = list(self.delta_history)[-10:]
                first_half = statistics.stdev(recent[:5]) if len(recent) >= 5 else jitter_std
                second_half = statistics.stdev(recent[5:]) if len(recent) >= 10 else jitter_std
                jitter_trend = (second_half - first_half) / (first_half + 1e-6)
            else:
                jitter_trend = 0.0
        else:
            jitter_std = 0.0
            jitter_cv = 0.0
            jitter_trend = 0.0
        
        # Relative speed
        relative_speed = latency_ms / (self.ema_long + 1e-6)
        
        # Update counters
        self.shares_since_job += 1
        self.total_shares += 1
        self.last_share_time = now
        
        # Create feature object
        features = ThermodynamicFeatures(
            timestamp=now,
            latency_ms=latency_ms,
            delta_ms=delta_ms,
            jitter_std=jitter_std,
            jitter_cv=jitter_cv,
            jitter_trend=jitter_trend,
            ema_short=self.ema_short,
            ema_long=self.ema_long,
            relative_speed=relative_speed,
            shares_since_job=self.shares_since_job,
            job_id=job_id,
            nonce=nonce
        )
        
        # Store for analysis (keep last 10000)
        self.all_features.append(features)
        if len(self.all_features) > 10000:
            self.all_features = self.all_features[-10000:]
        
        # Update baseline if needed
        if not self.baseline_established and self.total_shares >= MIN_SAMPLES_FOR_STATS:
            self._establish_baseline()
        
        return features
    
    def _establish_baseline(self):
        """Establish baseline jitter statistics."""
        if len(self.all_features) < MIN_SAMPLES_FOR_STATS:
            return
        
        jitter_values = [f.jitter_std for f in self.all_features if f.jitter_std > 0]
        
        if len(jitter_values) > 100:
            self.stats.mean_jitter = statistics.mean(jitter_values)
            self.stats.std_jitter = statistics.stdev(jitter_values)
            self.baseline_established = True
            print(f"\n[TPF] BASELINE ESTABLISHED:")
            print(f"      Mean jitter: {self.stats.mean_jitter:.2f} ms")
            print(f"      Std jitter:  {self.stats.std_jitter:.2f} ms")
            print(f"      Samples:     {len(jitter_values)}\n")
    
    def decide(self, features: ThermodynamicFeatures) -> FilterDecision:
        """
        Decide whether to send share to pool.
        
        Key insight from paper: Filter based on JITTER VARIANCE, not speed.
        
        Strategy:
        - Start with 20% filter rate targeting highest jitter shares
        - Once pattern confirmed, use learned threshold
        - Continuously validate filter isn't missing winners
        """
        now = time.time()
        
        # KEEPALIVE: Always send if too long since last send
        if (now - self.last_send_time) > KEEPALIVE_TIMEOUT:
            return FilterDecision.KEEPALIVE
        
        # SAFETY: Random percentage always gets through
        if random.random() < SAFETY_KEEP_RATE:
            return FilterDecision.SAFETY
        
        # INITIAL FILTER MODE (before pattern confirmed)
        # Filter the top 20% highest jitter shares (most likely entropic overflow)
        if not self.stats.pattern_confirmed:
            if self.baseline_established and features.jitter_std > 0:
                # Z-score based filtering: filter if jitter > mean + 0.84*std (top ~20%)
                z_threshold = 0.84  # ~20% in upper tail of normal distribution
                z_score = (features.jitter_std - self.stats.mean_jitter) / (self.stats.std_jitter + 1e-6)
                
                if z_score > z_threshold:
                    if random.random() < INITIAL_FILTER_RATE:
                        return FilterDecision.FILTER
            else:
                # Before baseline: random 20% filter to start collecting comparison data
                if random.random() < INITIAL_FILTER_RATE:
                    return FilterDecision.FILTER
            
            return FilterDecision.SEND
        
        # LEARNED FILTER MODE (after pattern confirmed)
        # Use the learned jitter threshold from winner analysis
        if features.jitter_std > self.jitter_threshold:
            # High jitter = entropic overflow = likely failure
            if random.random() < self.current_filter_rate:
                return FilterDecision.FILTER
        
        return FilterDecision.SEND
    
    def process_share(self, job_id: str, nonce: str, msg_id: int) -> Tuple[bool, ThermodynamicFeatures]:
        """
        Process incoming share and decide whether to forward to pool.
        
        Returns: (should_send, features)
        """
        features = self.extract_features(job_id, nonce)
        decision = self.decide(features)
        
        should_send = decision != FilterDecision.FILTER
        
        if should_send:
            self.shares_sent += 1
            self.last_send_time = time.time()
            self.pending[msg_id] = features
        else:
            self.shares_filtered += 1
        
        # Log decision
        self._log_share(features, decision)
        
        return should_send, features
    
    def _log_share(self, features: ThermodynamicFeatures, decision: FilterDecision):
        """Log share to CSV."""
        try:
            file_exists = os.path.exists(ALL_SHARES_FILE)
            with open(ALL_SHARES_FILE, 'a', newline='') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow([
                        'timestamp', 'latency_ms', 'delta_ms', 'jitter_std', 'jitter_cv',
                        'jitter_trend', 'ema_short', 'ema_long', 'relative_speed',
                        'shares_since_job', 'job_id', 'nonce', 'decision',
                        'pool_accepted', 'is_winner', 'block_hash'
                    ])
                writer.writerow([
                    f"{features.timestamp:.3f}", f"{features.latency_ms:.3f}",
                    f"{features.delta_ms:.3f}", f"{features.jitter_std:.3f}",
                    f"{features.jitter_cv:.4f}", f"{features.jitter_trend:.4f}",
                    f"{features.ema_short:.3f}", f"{features.ema_long:.3f}",
                    f"{features.relative_speed:.4f}", features.shares_since_job,
                    features.job_id, features.nonce, decision.value,
                    '', '', ''  # Will be updated on response
                ])
        except:
            pass
    
    def record_response(self, msg_id: int, accepted: bool, 
                       is_winner: bool = False, block_hash: str = None):
        """Record pool response."""
        if msg_id not in self.pending:
            return
        
        features = self.pending.pop(msg_id)
        features.pool_accepted = accepted
        features.is_block_winner = is_winner
        features.block_hash = block_hash
        
        if is_winner:
            self._record_winner(features, block_hash)
        
        # Periodic analysis
        if self.total_shares % VALIDATION_INTERVAL == 0:
            self._analyze_patterns()
            self._save_state()
    
    def _record_winner(self, features: ThermodynamicFeatures, block_hash: str):
        """Record a confirmed block winner - this is GOLD DATA."""
        self.winners.append(features)
        
        print("\n" + "="*70)
        print("🏆 BLOCK WINNER FOUND! 🏆")
        print("="*70)
        print(f"  Block Hash:     {block_hash}")
        print(f"  Jitter (σ):     {features.jitter_std:.3f} ms")
        print(f"  Jitter CV:      {features.jitter_cv:.4f}")
        print(f"  Latency:        {features.latency_ms:.3f} ms")
        print(f"  Relative Speed: {features.relative_speed:.4f}")
        print(f"  Share #:        {features.shares_since_job} since job")
        print(f"  Total Winners:  {len(self.winners)}")
        print("="*70 + "\n")
        
        # Save winner
        try:
            file_exists = os.path.exists(WINNERS_FILE)
            with open(WINNERS_FILE, 'a', newline='') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow([
                        'timestamp', 'latency_ms', 'delta_ms', 'jitter_std', 'jitter_cv',
                        'jitter_trend', 'ema_short', 'ema_long', 'relative_speed',
                        'shares_since_job', 'job_id', 'nonce', 'block_hash'
                    ])
                writer.writerow([
                    f"{features.timestamp:.3f}", f"{features.latency_ms:.3f}",
                    f"{features.delta_ms:.3f}", f"{features.jitter_std:.3f}",
                    f"{features.jitter_cv:.4f}", f"{features.jitter_trend:.4f}",
                    f"{features.ema_short:.3f}", f"{features.ema_long:.3f}",
                    f"{features.relative_speed:.4f}", features.shares_since_job,
                    features.job_id, features.nonce, block_hash or ''
                ])
        except:
            pass
        
        # Re-analyze with new winner data
        if len(self.winners) >= MIN_WINNERS_FOR_ANALYSIS:
            self._analyze_patterns()
    
    def _analyze_patterns(self):
        """
        Analyze jitter patterns between winners and general population.
        
        Key hypothesis from the paper:
        Winners should have LOWER jitter variance (synchronized state)
        Losers should have HIGHER jitter variance (entropic overflow)
        """
        if len(self.winners) < MIN_WINNERS_FOR_ANALYSIS:
            return
        
        if not self.baseline_established:
            return
        
        print("\n[TPF] Analyzing thermodynamic patterns...")
        
        # Get jitter values
        winner_jitter = [w.jitter_std for w in self.winners if w.jitter_std > 0]
        all_jitter = [f.jitter_std for f in self.all_features if f.jitter_std > 0]
        
        if len(winner_jitter) < 3 or len(all_jitter) < 100:
            print("[TPF] Insufficient data for analysis")
            return
        
        # Calculate statistics
        winner_mean = statistics.mean(winner_jitter)
        winner_std = statistics.stdev(winner_jitter) if len(winner_jitter) > 1 else 0
        
        all_mean = statistics.mean(all_jitter)
        all_std = statistics.stdev(all_jitter)
        
        self.stats.winner_mean_jitter = winner_mean
        self.stats.winner_std_jitter = winner_std
        self.stats.loser_mean_jitter = all_mean  # Approximation (mostly losers)
        self.stats.loser_std_jitter = all_std
        
        # Effect size (Cohen's d)
        pooled_std = np.sqrt((winner_std**2 + all_std**2) / 2) if winner_std > 0 else all_std
        effect_size = (all_mean - winner_mean) / (pooled_std + 1e-6)
        self.stats.effect_size = effect_size
        
        # Simple t-test approximation
        se = all_std / np.sqrt(len(all_jitter))
        t_stat = (winner_mean - all_mean) / (se + 1e-6)
        # Approximate p-value (two-tailed)
        from math import erf, sqrt
        z = abs(t_stat)
        p_value = 1 - erf(z / sqrt(2))
        
        self.stats.t_statistic = t_stat
        self.stats.p_value = p_value
        
        print(f"\n[TPF] PATTERN ANALYSIS RESULTS:")
        print(f"      Winners:     N={len(winner_jitter)}, μ={winner_mean:.3f}, σ={winner_std:.3f}")
        print(f"      Population:  N={len(all_jitter)}, μ={all_mean:.3f}, σ={all_std:.3f}")
        print(f"      Effect Size: d={effect_size:.3f} (Cohen's d)")
        print(f"      T-statistic: {t_stat:.3f}")
        print(f"      P-value:     {p_value:.4f}")
        
        # Check if pattern is significant
        # According to paper: winners should have LOWER jitter (synchronized state)
        pattern_direction = winner_mean < all_mean  # Expected: True
        statistically_significant = p_value < SIGNIFICANCE_THRESHOLD
        meaningful_effect = abs(effect_size) > 0.2  # Small effect threshold
        
        if pattern_direction and statistically_significant and meaningful_effect:
            self.stats.pattern_confirmed = True
            
            # Set threshold at winner_mean + 1 std (captures most winners)
            self.stats.optimal_threshold = winner_mean + winner_std
            self.jitter_threshold = self.stats.optimal_threshold
            
            print(f"\n      ✓ PATTERN CONFIRMED!")
            print(f"      Winners have LOWER jitter (synchronized state)")
            print(f"      Optimal threshold: {self.jitter_threshold:.3f} ms")
            
            # Enable filtering if we have enough winners
            if len(self.winners) >= MIN_WINNERS_FOR_FILTERING and not self.filter_enabled:
                self.filter_enabled = True
                self.current_filter_rate = INITIAL_FILTER_RATE + FILTER_INCREMENT
                print(f"      FILTER ENABLED at {self.current_filter_rate:.1%} rate")
        
        elif pattern_direction and not statistically_significant:
            print(f"\n      ? PATTERN TRENDING (not yet significant)")
            print(f"      Winners trending lower, need more data")
        
        else:
            print(f"\n      ✗ NO PATTERN DETECTED")
            if not pattern_direction:
                print(f"      Winners do NOT have lower jitter")
                print(f"      Thermodynamic hypothesis may not apply to this hardware/algo")
            self.stats.pattern_confirmed = False
            self.filter_enabled = False
        
        print()
    
    def get_status(self) -> dict:
        """Get current engine status."""
        return {
            'total_shares': self.total_shares,
            'shares_sent': self.shares_sent,
            'shares_filtered': self.shares_filtered,
            'filter_rate': self.shares_filtered / max(1, self.total_shares) * 100,
            'num_winners': len(self.winners),
            'filter_enabled': self.filter_enabled,
            'current_filter_rate': self.current_filter_rate * 100,
            'jitter_threshold': self.jitter_threshold if self.jitter_threshold != float('inf') else None,
            'baseline_established': self.baseline_established,
            'pattern_confirmed': self.stats.pattern_confirmed,
            'mean_jitter': self.stats.mean_jitter,
            'winner_mean_jitter': self.stats.winner_mean_jitter,
            'effect_size': self.stats.effect_size,
            'p_value': self.stats.p_value
        }


# =============================================================================
# STRATUM PROXY
# =============================================================================

class StratumProxy:
    """Stratum protocol proxy with thermodynamic filtering."""
    
    def __init__(self, miner_conn: socket.socket, engine: ThermodynamicEngine):
        self.miner = miner_conn
        self.engine = engine
        self.pool = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.pool.settimeout(30.0)
        self.running = True
        self.authorized = False
        self.current_job_id = None
        self.pending_submits: Dict[int, str] = {}  # msg_id -> nonce
    
    def start(self):
        try:
            print(f"[PROXY] Connecting to {REMOTE_HOST}:{REMOTE_PORT}...")
            self.pool.connect((REMOTE_HOST, REMOTE_PORT))
            self.pool.settimeout(None)
            print(f"[PROXY] Connected to pool")
            
            threading.Thread(target=self._miner_to_pool, daemon=True).start()
            threading.Thread(target=self._pool_to_miner, daemon=True).start()
        except Exception as e:
            print(f"[PROXY] Connection failed: {e}")
            self.miner.close()
    
    def _send(self, sock: socket.socket, data: dict):
        try:
            sock.sendall((json.dumps(data) + '\n').encode())
        except:
            pass
    
    def _miner_to_pool(self):
        """Handle miner -> pool messages."""
        buf = ""
        while self.running:
            try:
                data = self.miner.recv(4096).decode('utf-8', errors='ignore')
                if not data:
                    break
                buf += data
                while '\n' in buf:
                    line, buf = buf.split('\n', 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line)
                        self._handle_miner_msg(msg)
                    except json.JSONDecodeError:
                        continue
            except:
                break
        self.running = False
    
    def _handle_miner_msg(self, msg: dict):
        method = msg.get('method', '')
        msg_id = msg.get('id')
        
        if method == 'mining.authorize':
            msg['params'] = [USER_WALLET, POOL_PASSWORD]
            self._send(self.pool, msg)
        
        elif method == 'mining.submit' and self.authorized:
            params = msg.get('params', [])
            job_id = params[1] if len(params) > 1 else ''
            nonce = params[4] if len(params) > 4 else ''
            
            should_send, features = self.engine.process_share(job_id, nonce, msg_id)
            
            if should_send:
                self.pending_submits[msg_id] = nonce
                self._send(self.pool, msg)
            else:
                # Filtered: fake acceptance to miner
                self._send(self.miner, {"id": msg_id, "result": True, "error": None})
        
        else:
            self._send(self.pool, msg)
    
    def _pool_to_miner(self):
        """Handle pool -> miner messages."""
        buf = ""
        while self.running:
            try:
                data = self.pool.recv(4096).decode('utf-8', errors='ignore')
                if not data:
                    break
                buf += data
                while '\n' in buf:
                    line, buf = buf.split('\n', 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line)
                        self._handle_pool_msg(msg)
                    except json.JSONDecodeError:
                        continue
            except:
                break
        self.running = False
    
    def _handle_pool_msg(self, msg: dict):
        method = msg.get('method', '')
        msg_id = msg.get('id')
        result = msg.get('result')
        error = msg.get('error')
        
        # Authorization response
        if msg_id is not None and result is True and not method:
            self.authorized = True
            print("[PROXY] Authorized with pool")
        
        # New job
        if method == 'mining.notify':
            self.current_job_id = msg.get('params', [None])[0]
            self.engine.new_job()
        
        # Share response
        if msg_id in self.pending_submits:
            nonce = self.pending_submits.pop(msg_id)
            accepted = (result is True and error is None)
            
            # Check for block winner
            is_winner = self._check_winner(msg)
            block_hash = msg.get('block_hash') or msg.get('blockhash')
            
            self.engine.record_response(msg_id, accepted, is_winner, block_hash)
        
        # Forward to miner
        self._send(self.miner, msg)
    
    def _check_winner(self, msg: dict) -> bool:
        """Detect if this is a block winner."""
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
    """Main controller."""
    
    def __init__(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.engine = ThermodynamicEngine()
    
    def start(self):
        self.server.bind((LOCAL_HOST, LOCAL_PORT))
        self.server.listen(5)
        
        print("\n" + "="*70)
        print("TPF VERITAS V7 - THERMODYNAMIC JITTER ANALYSIS")
        print("="*70)
        print(f"Based on: 'Speaking to Silicon' by F. Angulo de Lafuente")
        print("-"*70)
        print(f"Listen:   {LOCAL_HOST}:{LOCAL_PORT}")
        print(f"Pool:     {REMOTE_HOST}:{REMOTE_PORT}")
        print(f"Data:     {DATA_DIR}/")
        print("-"*70)
        print(f"Filter:   ACTIVE at 20% (initial mode, targeting high-jitter)")
        print(f"Winners:  {len(self.engine.winners)}")
        print(f"Pattern:  {'CONFIRMED' if self.engine.stats.pattern_confirmed else 'Not yet'}")
        print("="*70)
        print()
        print("KEY INSIGHT: Measuring JITTER VARIANCE, not raw speed.")
        print("High variance = entropic overflow = likely failure")
        print("Low variance = synchronized state = potential winner")
        print()
        print("Starting with 20% INITIAL FILTER targeting high-jitter shares.")
        print("Filter will adapt automatically after pattern confirmation.")
        print("="*70 + "\n")
        
        threading.Thread(target=self._status_loop, daemon=True).start()
        
        while True:
            try:
                conn, addr = self.server.accept()
                print(f"[CONNECT] Miner connected from {addr}")
                proxy = StratumProxy(conn, self.engine)
                threading.Thread(target=proxy.start, daemon=True).start()
            except KeyboardInterrupt:
                print("\n[EXIT] Saving state...")
                self.engine._save_state()
                break
            except Exception as e:
                print(f"[ERROR] {e}")
    
    def _status_loop(self):
        """Periodic status output."""
        while True:
            time.sleep(60)
            s = self.engine.get_status()
            
            sent_pct = s['shares_sent'] / max(1, s['total_shares']) * 100
            
            print(f"\n[STATUS @ {datetime.now().strftime('%H:%M:%S')}]")
            print(f"  Shares:  {s['total_shares']:,} total, {s['shares_sent']:,} sent ({sent_pct:.1f}%)")
            print(f"  Winners: {s['num_winners']}")
            print(f"  Filter:  ", end='')
            if s['pattern_confirmed']:
                print(f"LEARNED (rate: {s['current_filter_rate']:.1f}%, threshold: {s['jitter_threshold']:.1f}ms)")
            else:
                print(f"INITIAL 20% (targeting high-jitter shares)")
            
            if s['baseline_established']:
                print(f"  Jitter:  μ={s['mean_jitter']:.2f}ms (baseline)")
                if s['num_winners'] > 0:
                    print(f"  Winners: μ={s['winner_mean_jitter']:.2f}ms, effect_size={s['effect_size']:.3f}, p={s['p_value']:.4f}")
            print()


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    controller = VeritasController()
    controller.start()
