"""
ui/components/tradingview_chart.py
TradingView Lightweight Charts component for institutional live execution views.

This uses the open-source tradingview/lightweight-charts library directly.
It does not use TradingView embedded widgets.
"""
from __future__ import annotations

import json
import math
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


def _clean_float(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
        if math.isfinite(number):
            return number
    except Exception:
        pass
    return default


def _positive_float(value: Any, default: float | None = None) -> float | None:
    number = _clean_float(value, default)
    if number is None or number <= 0:
        return default
    return number


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _standardize_ohlcv(df: pd.DataFrame, window_size: int = 900) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    work = df.copy()
    work.columns = [str(col).lower() for col in work.columns]
    required = {"open", "high", "low", "close"}
    if not required.issubset(set(work.columns)):
        return pd.DataFrame()
    if "timestamp" not in work.columns:
        work["timestamp"] = work.index
    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True, errors="coerce")
    work = work.dropna(subset=["timestamp"])
    for col in ("open", "high", "low", "close"):
        work[col] = pd.to_numeric(work[col], errors="coerce")
    work = work.dropna(subset=["open", "high", "low", "close"])
    if "volume" not in work.columns:
        work["volume"] = 0.0
    work["volume"] = pd.to_numeric(work["volume"], errors="coerce").fillna(0.0)
    work = work.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
    return work.tail(int(window_size)).reset_index(drop=True)


def _build_candles(df: pd.DataFrame) -> list[dict[str, Any]]:
    candles: list[dict[str, Any]] = []
    for row in df.itertuples(index=False):
        ts = getattr(row, "timestamp")
        candles.append({
            "time": int(pd.Timestamp(ts).timestamp()),
            "open": float(getattr(row, "open")),
            "high": float(getattr(row, "high")),
            "low": float(getattr(row, "low")),
            "close": float(getattr(row, "close")),
        })
    return candles


def _line_payload(df: pd.DataFrame, column: str) -> list[dict[str, Any]]:
    if column not in df.columns:
        return []
    payload: list[dict[str, Any]] = []
    values = pd.to_numeric(df[column], errors="coerce")
    for ts, value in zip(df["timestamp"], values):
        if pd.notna(value):
            payload.append({"time": int(pd.Timestamp(ts).timestamp()), "value": float(value)})
    return payload


def _compute_indicators(df: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    if df.empty:
        return {"ema20": [], "ema50": [], "vwap": [], "atrUpper": [], "atrLower": []}
    work = df.copy()
    work["ema20"] = work["close"].ewm(span=20, adjust=False).mean()
    work["ema50"] = work["close"].ewm(span=50, adjust=False).mean()
    typical = (work["high"] + work["low"] + work["close"]) / 3.0
    cumulative_volume = work["volume"].replace(0, pd.NA).fillna(1.0).cumsum()
    work["vwap"] = (typical * work["volume"].replace(0, 1.0)).cumsum() / cumulative_volume

    prev_close = work["close"].shift(1)
    tr = pd.concat([
        work["high"] - work["low"],
        (work["high"] - prev_close).abs(),
        (work["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    work["atrUpper"] = work["ema20"] + atr
    work["atrLower"] = work["ema20"] - atr
    return {
        "ema20": _line_payload(work, "ema20"),
        "ema50": _line_payload(work, "ema50"),
        "vwap": _line_payload(work, "vwap"),
        "atrUpper": _line_payload(work, "atrUpper"),
        "atrLower": _line_payload(work, "atrLower"),
    }


def _normalize_markers(strategy_markers: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for marker in strategy_markers or []:
        try:
            ts = pd.to_datetime(marker.get("timestamp"), utc=True, errors="coerce")
            if pd.isna(ts):
                continue
            signal = str(marker.get("signal") or "HOLD").upper()
            is_buy = signal in {"BUY", "BULLISH", "UP"}
            is_sell = signal in {"SELL", "BEARISH", "DOWN"}
            if not (is_buy or is_sell):
                continue
            strategy = str(marker.get("strategy") or "Strategy")
            strength = marker.get("strength")
            text = str(marker.get("label") or f"{strategy} {signal}")
            if strength not in (None, "") and str(strength) not in text:
                text = f"{text} | {strength}"
            output.append({
                "time": int(ts.timestamp()),
                "position": "belowBar" if is_buy else "aboveBar",
                "color": "#16a34a" if is_buy else "#dc2626",
                "shape": "arrowUp" if is_buy else "arrowDown",
                "text": text[:64],
                "strategy": strategy,
                "signal": "BUY" if is_buy else "SELL",
            })
        except Exception:
            continue
    return output


def _trade_plan_from_candidate(
    runtime_symbol: str,
    active_trade_plan: dict[str, Any] | None,
    active_candidates: list[dict[str, Any]] | None,
    df: pd.DataFrame,
) -> dict[str, Any]:
    plan = dict(active_trade_plan or {})
    candidate = (active_candidates or [{}])[0] or {}
    candidate_has_trade_levels = bool(candidate.get("sl") or candidate.get("stop_loss")) and bool(candidate.get("tp") or candidate.get("take_profit"))
    if not plan and candidate and candidate_has_trade_levels:
        plan = dict(candidate)

    last_close = _clean_float(df["close"].iloc[-1]) if not df.empty else None
    has_valid_plan = bool(plan) and bool(plan.get("sl") or plan.get("stop_loss")) and bool(plan.get("tp") or plan.get("take_profit"))
    entry = _positive_float(plan.get("entry_price") or plan.get("entry"), None)
    if entry is None and has_valid_plan:
        entry = last_close
    sl = _positive_float(plan.get("sl") or plan.get("stop_loss"))
    tp = _positive_float(plan.get("tp") or plan.get("take_profit"))
    confidence = _clean_float(plan.get("confidence") or plan.get("trade_quality") or plan.get("quality"), 0.0)
    strategy = str(
        plan.get("strategy")
        or plan.get("strategy_winner")
        or ("No Active Trade Plan" if not has_valid_plan else st.session_state.get("runtime_strategy"))
        or "Awaiting Strategy"
    )
    direction = str(plan.get("direction") or "NEUTRAL").upper()
    if direction == "BULLISH":
        direction = "BUY"
    elif direction == "BEARISH":
        direction = "SELL"

    atr = None
    if not df.empty:
        prev_close = df["close"].shift(1)
        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ], axis=1).max(axis=1)
        atr = _clean_float(tr.rolling(14).mean().iloc[-1])
    band = atr or ((entry or last_close or 1.0) * 0.0025)
    if has_valid_plan:
        entry_low = _positive_float(plan.get("entry_zone_low") or plan.get("entry_low"), (entry - band * 0.35) if entry else None)
        entry_high = _positive_float(plan.get("entry_zone_high") or plan.get("entry_high"), (entry + band * 0.35) if entry else None)
        trigger_low = _positive_float(plan.get("trigger_low"), (entry - band * 0.18) if entry else None)
        trigger_high = _positive_float(plan.get("trigger_high"), (entry + band * 0.18) if entry else None)
        exec_low = _positive_float(plan.get("execution_low"), (entry - band * 0.08) if entry else None)
        exec_high = _positive_float(plan.get("execution_high"), (entry + band * 0.08) if entry else None)
    else:
        entry_low = entry_high = trigger_low = trigger_high = exec_low = exec_high = None

    return {
        "symbol": runtime_symbol,
        "strategyWinner": strategy,
        "direction": direction,
        "tradeQuality": confidence,
        "status": str(plan.get("status") or ("NO_PLAN" if not has_valid_plan else "SETUP_FORMING")),
        "currentPrice": last_close,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "entryZone": [entry_low, entry_high] if entry_low and entry_high else None,
        "triggerZone": [trigger_low, trigger_high] if trigger_low and trigger_high else None,
        "executionZone": [exec_low, exec_high] if exec_low and exec_high else None,
        "triggerCondition": str(plan.get("trigger_condition") or plan.get("trigger") or "Await fresh setup confirmation"),
        "executionCondition": str(plan.get("execution_condition") or plan.get("execution") or "Wait for gate approval"),
    }


def _position_payload(open_positions: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for pos in open_positions or []:
        entry = _clean_float(pos.get("entry_price") or pos.get("price_open"))
        if entry is None:
            continue
        payload.append({
            "ticket": pos.get("ticket"),
            "symbol": pos.get("symbol"),
            "strategy": pos.get("strategy"),
            "direction": str(pos.get("direction") or "").upper(),
            "entry": entry,
            "sl": _positive_float(pos.get("sl")),
            "tp": _positive_float(pos.get("tp")),
            "lot": _clean_float(pos.get("lot") or pos.get("qty"), 0.0),
            "pnl": _clean_float(pos.get("live_pnl") or pos.get("profit"), 0.0),
        })
    return payload


def render_tradingview_chart(
    *,
    df: pd.DataFrame,
    runtime_symbol: str,
    runtime_timeframe: str,
    active_trade_plan: dict[str, Any] | None = None,
    open_positions: list[dict[str, Any]] | None = None,
    strategy_markers: list[dict[str, Any]] | None = None,
    active_candidates: list[dict[str, Any]] | None = None,
    height: int = 680,
    window_size: int = 420,
    component_key: str = "primary_live_trading_chart",
) -> None:
    """
    Render a reusable TradingView Lightweight Charts execution chart.

    Inputs:
      - runtime_symbol: current MT5/runtime symbol
      - active_trade_plan: candidate/plan details for zones and SL/TP
      - open_positions: broker/runtime positions to draw
      - strategy_markers: historical strategy signals to show on candles

    Output:
      - interactive institutional chart embedded in Streamlit
    """
    chart_df = _standardize_ohlcv(df, window_size=window_size)
    if chart_df.empty:
        st.info("No market data loaded yet. Connect MT5 or download candles to populate the live chart.")
        return

    runtime_symbol = str(runtime_symbol or "UNKNOWN").upper()
    runtime_timeframe = str(runtime_timeframe or "M5").upper()
    plan = _trade_plan_from_candidate(runtime_symbol, active_trade_plan, active_candidates, chart_df)
    first_ts = int(pd.Timestamp(chart_df["timestamp"].iloc[0]).timestamp())
    last_ts = int(pd.Timestamp(chart_df["timestamp"].iloc[-1]).timestamp())
    data_signature = f"{runtime_symbol}|{runtime_timeframe}|{len(chart_df)}|{first_ts}|{last_ts}"
    plan_signature = "|".join([
        str(plan.get("strategyWinner") or ""),
        str(plan.get("direction") or ""),
        str(plan.get("status") or ""),
        str(plan.get("sl") or ""),
        str(plan.get("tp") or ""),
    ])
    payload = {
        "componentKey": component_key,
        "symbol": runtime_symbol,
        "timeframe": runtime_timeframe,
        "dataSignature": data_signature,
        "planSignature": plan_signature,
        "theme": st.session_state.get("ui_theme", "Dark"),
        "candles": _build_candles(chart_df),
        "indicators": _compute_indicators(chart_df),
        "positions": _position_payload(open_positions),
        "markers": _normalize_markers(strategy_markers),
        "plan": plan,
        "lastUpdate": int(pd.Timestamp.utcnow().timestamp()),
    }
    payload_json = json.dumps(_json_safe(payload), separators=(",", ":"))
    html = _build_chart_html(payload_json)
    components.html(html, height=height, scrolling=False)


def _build_chart_html(payload_json: str) -> str:
    return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    html, body {{
      margin: 0;
      padding: 0;
      width: 100%;
      height: 100%;
      background: transparent;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      overflow: hidden;
    }}
    .nxb-wrap {{
      width: 100%;
      height: 670px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) 310px;
      gap: 12px;
      box-sizing: border-box;
    }}
    .nxb-chart-shell {{
      position: relative;
      overflow: hidden;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: var(--surface);
      box-shadow: var(--shadow);
      min-width: 0;
    }}
    .nxb-chart {{
      width: 100%;
      height: 100%;
    }}
    .nxb-zone-layer,
    .nxb-session-layer {{
      position: absolute;
      inset: 0;
      pointer-events: none;
      overflow: hidden;
    }}
    .nxb-session {{
      position: absolute;
      top: 0;
      height: 100%;
      border-left: 1px solid rgba(100,116,139,0.12);
      border-right: 1px solid rgba(100,116,139,0.08);
    }}
    .nxb-zone {{
      position: absolute;
      left: 0;
      right: 0;
      border-top: 1px solid;
      border-bottom: 1px solid;
      display: flex;
      align-items: center;
      padding-left: 12px;
      box-sizing: border-box;
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0.7px;
      text-transform: uppercase;
    }}
    .nxb-hud {{
      position: absolute;
      left: 12px;
      top: 10px;
      z-index: 5;
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      pointer-events: none;
    }}
    .nxb-pill {{
      background: var(--pill);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 7px;
      padding: 5px 8px;
      font-size: 11px;
      font-weight: 800;
      letter-spacing: .3px;
      box-shadow: 0 8px 22px rgba(15,23,42,.16);
    }}
    .nxb-side {{
      border-radius: 10px;
      border: 1px solid var(--border);
      background: var(--surface);
      color: var(--text);
      box-shadow: var(--shadow);
      padding: 14px;
      box-sizing: border-box;
      overflow: hidden;
    }}
    .nxb-title {{
      font-size: 12px;
      color: var(--muted);
      font-weight: 900;
      letter-spacing: 1px;
      text-transform: uppercase;
      margin-bottom: 8px;
    }}
    .nxb-main {{
      font-size: 21px;
      font-weight: 900;
      color: var(--text);
      margin-bottom: 6px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .nxb-row {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      border-top: 1px solid var(--border);
      padding: 9px 0;
      font-size: 12px;
      color: var(--muted);
    }}
    .nxb-row b {{
      color: var(--text);
      text-align: right;
    }}
    .nxb-condition {{
      margin-top: 10px;
      padding: 10px;
      border-radius: 8px;
      background: var(--soft);
      border: 1px solid var(--border);
      color: var(--text);
      font-size: 12px;
      line-height: 1.45;
    }}
    @media (max-width: 1050px) {{
      .nxb-wrap {{ grid-template-columns: 1fr; height: 900px; }}
      .nxb-chart-shell {{ height: 620px; }}
      .nxb-side {{ height: 260px; }}
    }}
  </style>
</head>
<body>
  <div class="nxb-wrap" id="nxb-wrap">
    <div class="nxb-chart-shell">
      <div class="nxb-chart" id="nxb-chart"></div>
      <div class="nxb-session-layer" id="nxb-sessions"></div>
      <div class="nxb-zone-layer" id="nxb-zones"></div>
      <div class="nxb-hud" id="nxb-hud"></div>
    </div>
    <aside class="nxb-side" id="nxb-side"></aside>
  </div>
  <script>
    const NXB_PAYLOAD = {payload_json};
    const CDN_URLS = [
      "https://unpkg.com/lightweight-charts@4.2.3/dist/lightweight-charts.standalone.production.js",
      "https://cdn.jsdelivr.net/npm/lightweight-charts@4.2.3/dist/lightweight-charts.standalone.production.js"
    ];

    function loadScript(urls, done) {{
      if (window.LightweightCharts) return done();
      const url = urls.shift();
      if (!url) {{
        document.body.innerHTML = '<div style="padding:16px;color:#ef4444;font-family:Inter,sans-serif;">Lightweight Charts failed to load. Check network access to the library CDN.</div>';
        return;
      }}
      const script = document.createElement('script');
      script.src = url;
      script.onload = done;
      script.onerror = () => loadScript(urls, done);
      document.head.appendChild(script);
    }}

    function fmt(value, digits = 5) {{
      if (value === null || value === undefined || value === '') return 'N/A';
      const number = Number(value);
      if (!Number.isFinite(number) || number <= 0) return 'N/A';
      if (Math.abs(number) >= 1000) return number.toFixed(2);
      if (Math.abs(number) >= 10) return number.toFixed(3);
      return number.toFixed(digits);
    }}

    function colors(theme) {{
      const light = theme === 'Light';
      return {{
        bg: light ? '#f8fafc' : '#050816',
        surface: light ? '#ffffff' : '#0b1220',
        soft: light ? '#f1f5f9' : '#111827',
        pill: light ? 'rgba(255,255,255,.92)' : 'rgba(15,23,42,.88)',
        text: light ? '#0f172a' : '#e5edf7',
        muted: light ? '#475569' : '#94a3b8',
        border: light ? '#d5dfeb' : '#263449',
        grid: light ? '#e3eaf3' : 'rgba(100,116,139,.22)',
        green: '#16a34a',
        red: '#dc2626',
        blue: '#2563eb',
        amber: '#d97706',
        cyan: '#0891b2',
        purple: '#7c3aed',
        shadow: light ? '0 14px 34px rgba(15,23,42,.10)' : '0 14px 34px rgba(0,0,0,.34)'
      }};
    }}

    function cssVars(c) {{
      const root = document.documentElement;
      root.style.setProperty('--surface', c.surface);
      root.style.setProperty('--soft', c.soft);
      root.style.setProperty('--text', c.text);
      root.style.setProperty('--muted', c.muted);
      root.style.setProperty('--border', c.border);
      root.style.setProperty('--pill', c.pill);
      root.style.setProperty('--shadow', c.shadow);
    }}

    function createOrUpdate(payload) {{
      const c = colors(payload.theme);
      cssVars(c);
      const chartEl = document.getElementById('nxb-chart');
      const stateKey = 'nxb_lwc_range_' + payload.symbol + '_' + payload.timeframe;
      window.__nxbCharts = window.__nxbCharts || {{}};
      let inst = window.__nxbCharts[payload.componentKey];
      const layout = {{
        background: {{ type: 'solid', color: c.surface }},
        textColor: c.text,
        fontFamily: 'Inter, sans-serif',
      }};
      if (!inst) {{
        const chart = LightweightCharts.createChart(chartEl, {{
          width: chartEl.clientWidth,
          height: chartEl.clientHeight,
          layout,
          grid: {{ vertLines: {{ color: c.grid }}, horzLines: {{ color: c.grid }} }},
          rightPriceScale: {{ borderColor: c.border, scaleMargins: {{ top: 0.08, bottom: 0.12 }} }},
          timeScale: {{ borderColor: c.border, timeVisible: true, secondsVisible: false, rightOffset: 8, barSpacing: 8 }},
          crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
          handleScroll: true,
          handleScale: true,
        }});
        const candles = chart.addCandlestickSeries({{
          upColor: '#16a34a',
          downColor: '#dc2626',
          borderUpColor: '#16a34a',
          borderDownColor: '#dc2626',
          wickUpColor: '#16a34a',
          wickDownColor: '#dc2626',
          priceLineColor: c.blue,
        }});
        inst = {{
          chart,
          candles,
          lines: {{
            ema20: chart.addLineSeries({{ color: c.amber, lineWidth: 2, title: 'EMA20' }}),
            ema50: chart.addLineSeries({{ color: c.blue, lineWidth: 2, title: 'EMA50' }}),
            vwap: chart.addLineSeries({{ color: c.purple, lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Dotted, title: 'VWAP' }}),
            atrUpper: chart.addLineSeries({{ color: 'rgba(8,145,178,.50)', lineWidth: 1, title: 'ATR Upper' }}),
            atrLower: chart.addLineSeries({{ color: 'rgba(8,145,178,.50)', lineWidth: 1, title: 'ATR Lower' }}),
          }},
          priceLines: [],
          lastBarTime: null,
          candleCount: 0,
          dataSignature: null,
          planSignature: null,
          symbolKey: payload.symbol + ':' + payload.timeframe,
        }};
        window.__nxbCharts[payload.componentKey] = inst;
        chart.timeScale().subscribeVisibleLogicalRangeChange(range => {{
          if (range) localStorage.setItem(stateKey, JSON.stringify(range));
        }});
        new ResizeObserver(() => {{
          chart.applyOptions({{ width: chartEl.clientWidth, height: chartEl.clientHeight }});
          renderOverlays(inst, payload, c);
        }}).observe(chartEl);
      }} else {{
        inst.chart.applyOptions({{
          layout,
          grid: {{ vertLines: {{ color: c.grid }}, horzLines: {{ color: c.grid }} }},
          rightPriceScale: {{ borderColor: c.border }},
          timeScale: {{ borderColor: c.border }},
        }});
      }}

      const symbolKey = payload.symbol + ':' + payload.timeframe;
      const symbolChanged = inst.symbolKey !== symbolKey;
      const dataChanged = inst.dataSignature !== payload.dataSignature;
      if (symbolChanged || dataChanged) {{
        const previousLastBarTime = inst.lastBarTime;
        const previousCandleCount = inst.candleCount || 0;
        const last = payload.candles.length ? payload.candles[payload.candles.length - 1] : null;
        const appendedLiveBar = Boolean(
          !symbolChanged &&
          previousLastBarTime &&
          last &&
          last.time > previousLastBarTime &&
          payload.candles.length >= previousCandleCount
        );
        inst.symbolKey = symbolKey;
        if (appendedLiveBar) {{
          inst.candles.update(last);
        }} else {{
          inst.candles.setData(payload.candles);
          inst.chart.timeScale().fitContent();
        }}
        inst.lastBarTime = last ? last.time : null;
        inst.candleCount = payload.candles.length;
        inst.dataSignature = payload.dataSignature;
      }} else if (payload.candles.length) {{
        const last = payload.candles[payload.candles.length - 1];
        if (inst.lastBarTime && last.time >= inst.lastBarTime) {{
          inst.candles.update(last);
          if (payload.candles.length > 1 && last.time !== inst.lastBarTime) {{
            inst.candles.setData(payload.candles);
          }}
        }} else {{
          inst.candles.setData(payload.candles);
        }}
        inst.lastBarTime = last.time;
        inst.candleCount = payload.candles.length;
      }}
      inst.planSignature = payload.planSignature;

      Object.keys(inst.lines).forEach(key => {{
        inst.lines[key].setData((payload.indicators && payload.indicators[key]) || []);
      }});
      inst.candles.setMarkers(payload.markers || []);
      refreshPriceLines(inst, payload, c);
      renderHud(payload, c);
      renderSide(payload, c);
      requestAnimationFrame(() => renderOverlays(inst, payload, c));
      inst.latestPayload = payload;
      inst.latestColors = c;
      if (!inst.overlaySubscribed) {{
        inst.chart.timeScale().subscribeVisibleTimeRangeChange(() => renderOverlays(inst, inst.latestPayload, inst.latestColors));
        inst.chart.subscribeCrosshairMove(() => renderOverlays(inst, inst.latestPayload, inst.latestColors));
        inst.overlaySubscribed = true;
      }}
    }}

    function refreshPriceLines(inst, payload, c) {{
      inst.priceLines.forEach(line => {{
        try {{ inst.candles.removePriceLine(line); }} catch(e) {{}}
      }});
      inst.priceLines = [];
      const add = (price, title, color, style = LightweightCharts.LineStyle.Solid) => {{
        if (!Number.isFinite(Number(price)) || Number(price) <= 0) return;
        inst.priceLines.push(inst.candles.createPriceLine({{
          price: Number(price),
          color,
          lineWidth: 2,
          lineStyle: style,
          axisLabelVisible: true,
          title,
        }}));
      }};
      const plan = payload.plan || {{}};
      add(plan.currentPrice, 'Current', c.blue, LightweightCharts.LineStyle.Dotted);
      add(plan.entry, 'Entry', c.cyan, LightweightCharts.LineStyle.Dashed);
      add(plan.sl, 'SL', c.red, LightweightCharts.LineStyle.Solid);
      add(plan.tp, 'TP', c.green, LightweightCharts.LineStyle.Solid);
      (payload.positions || []).forEach(pos => {{
        add(pos.entry, '#' + pos.ticket + ' ' + pos.direction, c.blue, LightweightCharts.LineStyle.Dashed);
        add(pos.sl, '#' + pos.ticket + ' SL', c.red, LightweightCharts.LineStyle.Dotted);
        add(pos.tp, '#' + pos.ticket + ' TP', c.green, LightweightCharts.LineStyle.Dotted);
      }});
    }}

    function zoneSpecs(payload, c) {{
      const plan = payload.plan || {{}};
      return [
        {{ label: 'Setup Zone', prices: plan.entryZone, color: c.blue, fill: 'rgba(37,99,235,.11)' }},
        {{ label: 'Trigger Zone', prices: plan.triggerZone, color: c.amber, fill: 'rgba(217,119,6,.13)' }},
        {{ label: 'Execution Zone', prices: plan.executionZone, color: c.green, fill: 'rgba(22,163,74,.12)' }},
      ];
    }}

    function renderOverlays(inst, payload, c) {{
      const zoneLayer = document.getElementById('nxb-zones');
      const sessionLayer = document.getElementById('nxb-sessions');
      zoneLayer.innerHTML = '';
      sessionLayer.innerHTML = '';

      zoneSpecs(payload, c).forEach(spec => {{
        if (!spec.prices || spec.prices.length !== 2) return;
        const p1 = Number(spec.prices[0]);
        const p2 = Number(spec.prices[1]);
        if (!Number.isFinite(p1) || !Number.isFinite(p2)) return;
        const y1 = inst.candles.priceToCoordinate(Math.max(p1, p2));
        const y2 = inst.candles.priceToCoordinate(Math.min(p1, p2));
        if (y1 == null || y2 == null) return;
        const div = document.createElement('div');
        div.className = 'nxb-zone';
        div.style.top = Math.min(y1, y2) + 'px';
        div.style.height = Math.max(18, Math.abs(y2 - y1)) + 'px';
        div.style.borderColor = spec.color;
        div.style.background = spec.fill;
        div.style.color = spec.color;
        div.textContent = spec.label;
        zoneLayer.appendChild(div);
      }});

      renderSessions(inst, payload, sessionLayer, c);
    }}

    function renderSessions(inst, payload, layer, c) {{
      const candles = payload.candles || [];
      if (!candles.length) return;
      const minT = candles[0].time;
      const maxT = candles[candles.length - 1].time;
      const day = 86400;
      const firstDay = Math.floor(minT / day) * day;
      const sessions = [
        {{ name: 'London', start: 8, end: 13, color: 'rgba(37,99,235,.055)' }},
        {{ name: 'Overlap', start: 13, end: 17, color: 'rgba(124,58,237,.075)' }},
        {{ name: 'New York', start: 17, end: 22, color: 'rgba(22,163,74,.055)' }},
      ];
      for (let d = firstDay - day; d <= maxT + day; d += day) {{
        sessions.forEach(s => {{
          const t1 = d + s.start * 3600;
          const t2 = d + s.end * 3600;
          if (t2 < minT || t1 > maxT) return;
          const x1 = inst.chart.timeScale().timeToCoordinate(t1);
          const x2 = inst.chart.timeScale().timeToCoordinate(t2);
          if (x1 == null || x2 == null) return;
          const div = document.createElement('div');
          div.className = 'nxb-session';
          div.style.left = Math.min(x1, x2) + 'px';
          div.style.width = Math.max(2, Math.abs(x2 - x1)) + 'px';
          div.style.background = s.color;
          div.title = s.name;
          layer.appendChild(div);
        }});
      }}
    }}

    function renderHud(payload, c) {{
      const plan = payload.plan || {{}};
      document.getElementById('nxb-hud').innerHTML = [
        '<span class="nxb-pill">' + payload.symbol + ' ' + payload.timeframe + '</span>',
        '<span class="nxb-pill">Price ' + fmt(plan.currentPrice) + '</span>',
        '<span class="nxb-pill">Winner ' + (plan.strategyWinner || 'N/A') + '</span>',
        '<span class="nxb-pill">Quality ' + fmt(plan.tradeQuality, 1) + '%</span>',
      ].join('');
    }}

    function renderSide(payload, c) {{
      const plan = payload.plan || {{}};
      const side = document.getElementById('nxb-side');
      const positions = payload.positions || [];
      const markers = payload.markers || [];
      side.innerHTML = `
        <div class="nxb-title">Trade Plan</div>
        <div class="nxb-main">${{plan.strategyWinner || 'Awaiting Strategy'}}</div>
        <div class="nxb-row"><span>Symbol</span><b>${{payload.symbol}} ${{payload.timeframe}}</b></div>
        <div class="nxb-row"><span>Current Price</span><b>${{fmt(plan.currentPrice)}}</b></div>
        <div class="nxb-row"><span>Trade Quality</span><b>${{fmt(plan.tradeQuality, 1)}}%</b></div>
        <div class="nxb-row"><span>Status</span><b>${{plan.status || 'NO_PLAN'}}</b></div>
        <div class="nxb-row"><span>Direction</span><b>${{plan.direction || 'NEUTRAL'}}</b></div>
        <div class="nxb-row"><span>Entry Zone</span><b>${{plan.entryZone ? fmt(plan.entryZone[0]) + ' - ' + fmt(plan.entryZone[1]) : 'N/A'}}</b></div>
        <div class="nxb-row"><span>SL</span><b style="color:${{c.red}}">${{fmt(plan.sl)}}</b></div>
        <div class="nxb-row"><span>TP</span><b style="color:${{c.green}}">${{fmt(plan.tp)}}</b></div>
        <div class="nxb-condition"><b>Trigger</b><br>${{plan.triggerCondition || 'Await confirmation'}}</div>
        <div class="nxb-condition"><b>Execution</b><br>${{plan.executionCondition || 'Await gate approval'}}</div>
        <div class="nxb-row"><span>Open Positions</span><b>${{positions.length}}</b></div>
        <div class="nxb-row"><span>Visible Signals</span><b>${{markers.length}}</b></div>
      `;
    }}

    loadScript([...CDN_URLS], () => createOrUpdate(NXB_PAYLOAD));
  </script>
</body>
</html>
"""
