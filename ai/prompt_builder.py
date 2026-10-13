import json


class PromptBuilder:
    @staticmethod
    def build_analysis_prompt(
        strategy_name: str,
        strategy_version: str,
        genome: dict,
        config: dict,
        metrics: dict,
        attribution: dict,
        warnings: list,
        rejected_signals_summary: list
    ) -> str:
        # Limit rejected signals logs to top 15 to avoid token blowout
        compressed_rejections = rejected_signals_summary[:15]
        
        # Build prompt
        prompt = f"""
You are the AI Strategy Analyst for NexusBot (Version: {strategy_version}), an AI-assisted quantitative strategy workbench.
Your role is to interpret deterministic backtest metrics, diagnose strengths/weaknesses, and provide a structured parameter recommendation.

### STRATEGY GENOME
{json.dumps(genome, indent=2)}

### RUNTIME CONFIGURATION
{json.dumps(config, indent=2)}

### QUANTITATIVE METRICS (Computed locally in Python)
- Total Trades: {metrics.get('trades', 0)}
- Win Rate: {metrics.get('win_rate', 0.0):.2f}%
- Net Profit: ${metrics.get('net_profit', 0.0):.2f}
- ROI: {metrics.get('roi', 0.0):.2f}%
- Profit Factor: {metrics.get('profit_factor', 0.0):.2f}
- Sharpe Ratio: {metrics.get('sharpe_ratio', 0.0):.2f}
- Max Drawdown: ${metrics.get('max_drawdown_abs', 0.0):.2f} ({metrics.get('max_drawdown_pct', 0.0):.2f}%)
- Realized Risk-to-Reward (R:R) Ratio: {metrics.get('realized_rr', 0.0):.2f}
- Longest Losing Streak: {metrics.get('longest_losing_streak', 0)}
- Average Trade Duration: {metrics.get('avg_duration_min', 0.0):.1f} minutes
- Outlier Trades count: {attribution.get('outliers_count', 0)}

### STRATEGY HEURISTIC WARNINGS
{json.dumps(warnings, indent=2)}

### EXIT REASON BREAKDOWN
{json.dumps(metrics.get('exit_breakdown', {}), indent=2)}

### REGIME attributions
- Trending Market trades: {attribution.get('trending_pct', 0.0):.1f}%
- Ranging Market trades: {attribution.get('ranging_pct', 0.0):.1f}%
- Volatile Market trades: {attribution.get('volatile_pct', 0.0):.1f}%
- Low Volatility Market trades: {attribution.get('low_vol_pct', 0.0):.1f}%

### SESSION attributions (Net Profit)
{json.dumps(attribution.get('profit_by_session', {}), indent=2)}
- Best session: {attribution.get('best_session', 'None')}
- Worst session: {attribution.get('worst_session', 'None')}

### INDICATOR PERFORMANCE ATTRIBUTIONS (Averages)
- Winning Trades: {json.dumps(attribution.get('winning_stats', {}), indent=2)}
- Losing Trades: {json.dumps(attribution.get('losing_stats', {}), indent=2)}

### PEARSON CORRELATION (Indicator entry values vs final trade profit)
{json.dumps(attribution.get('correlations', {}), indent=2)}

### REJECTED SIGNALS LOG (Top 15 entries)
{json.dumps(compressed_rejections, indent=2)}

You MUST respond strictly in the following JSON format. Do not write normal conversation text. Do not wrap JSON in triple backticks unless required by system templates. Ensure JSON properties match the keys exactly.

Required JSON Structure:
{{
  "confidence_score": 85, // Integer 0-100 indicating confidence based on trade count, metric consistency, and PF stability.
  "why_won_reasons": [
    "London session overlap provides momentum",
    "ADX > 25 filter prevents flat chop entries",
    "High RSI indicates strong breakouts"
  ], // EXACTLY 3 bullet points of reasons why the strategy succeeded
  "why_lost_reasons": [
    "Asian session entries trade into low liquidity",
    "Low ATR periods trigger false breakout exits",
    "Early breakeven trail cuts short profitable runs"
  ], // EXACTLY 3 bullet points of reasons why the strategy failed
  "summary": "Short explanation of behavior and performance.",
  "strengths": [
    "Good trend capturing in trending sessions",
    "Stable drawdown"
  ], // Concise list of strengths
  "weaknesses": [
    "Asian rollover volatility triggers stops",
    "High frequency of noise entries"
  ], // Concise list of weaknesses
  "recommendations": [
    "Increase entry cooldown to 8 candles",
    "Set spread threshold to 0.2 ATR"
  ] // Quantitative, parameter-level recommendations
}}
"""
        return prompt
