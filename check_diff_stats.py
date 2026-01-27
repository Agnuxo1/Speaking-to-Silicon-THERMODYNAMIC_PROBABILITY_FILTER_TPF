import pandas as pd
try:
    df = pd.read_csv("tpf_s9_labeled.csv")
    print(f"Count: {len(df)}")
    print(f"Min Diff: {df['found_difficulty'].min()}")
    print(f"Max Diff: {df['found_difficulty'].max()}")
    print(f"Mean Diff: {df['found_difficulty'].mean()}")
    print(f"Distribution:\n{df['found_difficulty'].describe()}")
except Exception as e:
    print(e)
