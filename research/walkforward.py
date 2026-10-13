import pandas as pd

def split_walkforward(df: pd.DataFrame, train_ratio: float = 0.7) -> tuple[pd.DataFrame, pd.DataFrame]:
    if df is None or not hasattr(df, "empty") or df.empty:
        empty_df = pd.DataFrame()
        return empty_df, empty_df
        
    try:
        sorted_df = df.copy()
        if "timestamp" in sorted_df.columns:
            sorted_df["timestamp"] = pd.to_datetime(sorted_df["timestamp"])
            sorted_df = sorted_df.sort_values("timestamp")
            
        sorted_df = sorted_df.reset_index(drop=True)
        split_idx = int(len(sorted_df) * train_ratio)
        
        train_df = sorted_df.iloc[:split_idx].reset_index(drop=True)
        val_df = sorted_df.iloc[split_idx:].reset_index(drop=True)
        return train_df, val_df
    except Exception:
        split_idx = int(len(df) * train_ratio)
        train_df = df.iloc[:split_idx].reset_index(drop=True)
        val_df = df.iloc[split_idx:].reset_index(drop=True)
        return train_df, val_df
