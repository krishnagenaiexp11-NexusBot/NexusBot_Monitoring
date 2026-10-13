import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.rolling(period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    return pd.DataFrame({"macd": macd_line, "macd_signal": signal_line, "macd_hist": macd_line - signal_line})


def supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    data = df.copy()
    data["atr_st"] = atr(data, period)
    hl2 = (data["high"] + data["low"]) / 2
    upper = hl2 + multiplier * data["atr_st"]
    lower = hl2 - multiplier * data["atr_st"]

    final_upper = upper.copy()
    final_lower = lower.copy()
    direction = pd.Series(1, index=data.index, dtype="int64")
    trend = pd.Series(np.nan, index=data.index, dtype="float64")

    for i in range(1, len(data)):
        final_upper.iloc[i] = upper.iloc[i] if upper.iloc[i] < final_upper.iloc[i - 1] or data["close"].iloc[i - 1] > final_upper.iloc[i - 1] else final_upper.iloc[i - 1]
        final_lower.iloc[i] = lower.iloc[i] if lower.iloc[i] > final_lower.iloc[i - 1] or data["close"].iloc[i - 1] < final_lower.iloc[i - 1] else final_lower.iloc[i - 1]

        if data["close"].iloc[i] > final_upper.iloc[i - 1]:
            direction.iloc[i] = 1
        elif data["close"].iloc[i] < final_lower.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]

        trend.iloc[i] = final_lower.iloc[i] if direction.iloc[i] == 1 else final_upper.iloc[i]

    return pd.DataFrame({"supertrend": trend, "supertrend_dir": direction})


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]

    prev_high = high.shift(1)
    prev_low = low.shift(1)
    prev_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    up_move = high - prev_high
    down_move = prev_low - low

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr_s = pd.Series(tr).ewm(alpha=1/period, adjust=False).mean()
    plus_dm_s = pd.Series(plus_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean()
    minus_dm_s = pd.Series(minus_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean()

    plus_di = 100 * (plus_dm_s / tr_s.replace(0, np.nan))
    minus_di = 100 * (minus_dm_s / tr_s.replace(0, np.nan))

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_series = dx.ewm(alpha=1/period, adjust=False).mean()
    return adx_series.fillna(0)


def htf_ema(df: pd.DataFrame, htf_resample: str, period: int) -> pd.Series:
    try:
        temp = df.copy()
        temp["timestamp"] = pd.to_datetime(temp["timestamp"])
        temp = temp.sort_values("timestamp")
        resampled = temp.set_index("timestamp")["close"].resample(htf_resample, closed="right", label="right").last()
        r_ema = ema(resampled, period)
        r_ema_shifted = r_ema.shift(1)
        htf_ema_series = r_ema_shifted.reindex(temp["timestamp"], method="ffill")
        htf_ema_series.index = df.index
        return htf_ema_series
    except Exception:
        return pd.Series(np.nan, index=df.index)
