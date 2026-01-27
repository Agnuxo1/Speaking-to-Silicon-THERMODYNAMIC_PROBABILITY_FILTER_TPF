#!/usr/bin/env python3
"""
TPF S9 TRAINER
==============
Trains the TPF Neural Network on labeled S9 data.
Input: tpf_s9_labeled.csv
Output: tpf_s9_model.pkl, tpf_scaler.pkl
"""

import pandas as pd
import numpy as np
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
import joblib
import os

DATASET_FILE = "tpf_s9_labeled.csv"
MODEL_FILE = "tpf_s9_model.pkl"
SCALER_FILE = "tpf_scaler.pkl"

def main():
    if not os.path.exists(DATASET_FILE):
        print(f"[ERR] Dataset {DATASET_FILE} not found.")
        return

    print(f"Loading {DATASET_FILE}...")
    df = pd.read_csv(DATASET_FILE)
    
    # Feature Engineering
    # We need "Windowed" features like the bridge uses.
    # The raw data is per-share.
    # We simulate a sliding window over the shares.
    
    print("Generating features...")
    features = []
    labels = []
    
    # Sort by time
    df = df.sort_values("timestamp")
    
    # Sliding window of 10 shares
    window_size = 10
    
    for i in range(len(df) - window_size):
        window = df.iloc[i : i+window_size]
        
        # Target: Is the NEXT share (or current window average) a good block?
        # Actually, TPF predicts if the CURRENT state will produce a good block.
        # But we only have labels for "Found Diff".
        # Let's try to predict "Is this a High Entropy State?"
        # Proxy: If mean(FoundDiff) of window is low -> High Entropy (Bad).
        # If mean(FoundDiff) is high -> Low Entropy (Good).
        
        # But wait, labeler output is per share.
        # Let's use the label of the *last* share in window as target.
        target = window.iloc[-1]['label']
        
        # Features
        jitters = window['jitter_ms'].values
        jitter_mean = np.mean(jitters)
        jitter_std = np.std(jitters)
        share_rate = window_size / (window.iloc[-1]['timestamp'] - window.iloc[0]['timestamp'] + 1e-6)
        
        features.append([share_rate, jitter_mean, jitter_std])
        labels.append(target)
        
    X = np.array(features)
    y = np.array(labels)
    
    print(f"Dataset: {len(X)} samples")
    print(f"Class Balance: {np.sum(y)} Good / {len(y)-np.sum(y)} Bad")
    
    if np.sum(y) == 0:
        print("[WARN] No positive samples found. Training will fail/be useless.")
        # Create fake positive for structure testing if needed?
        # No, better to fail honest.
    
    # Split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Scale
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)
    
    # Train
    print("Training MLP (16,8,4)...")
    clf = MLPClassifier(hidden_layer_sizes=(16, 8, 4), max_iter=1000, random_state=42)
    clf.fit(X_train_s, y_train)
    
    # Evaluate
    info = score = clf.score(X_test_s, y_test)
    print(f"Accuracy: {score:.4f}")
    print(classification_report(y_test, clf.predict(X_test_s)))
    
    # Save
    joblib.dump(clf, MODEL_FILE)
    joblib.dump(scaler, SCALER_FILE)
    print("Model saved.")

if __name__ == "__main__":
    main()
