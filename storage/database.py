import json
import sqlite3
from pathlib import Path


class Database:
    def __init__(self, path: str = "results/nexusbot.sqlite"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS backtest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy TEXT NOT NULL,
                started_at TEXT DEFAULT CURRENT_TIMESTAMP,
                metrics_json TEXT NOT NULL,
                config_json TEXT NOT NULL,
                dataset_fingerprint TEXT
            );
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                ticket INTEGER,
                direction TEXT,
                entry_time TEXT,
                entry_price REAL,
                exit_time TEXT,
                exit_price REAL,
                profit REAL,
                exit_reason TEXT,
                strategy_version TEXT,
                commission REAL,
                rsi REAL,
                atr REAL,
                volume_ratio REAL,
                momentum REAL,
                signal_strength INTEGER,
                session TEXT,
                market_regime TEXT,
                trade_duration_minutes REAL,
                outlier_flag INTEGER
            );
            CREATE TABLE IF NOT EXISTS event_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                timestamp TEXT,
                level TEXT,
                message TEXT
            );
            CREATE TABLE IF NOT EXISTS ai_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy TEXT NOT NULL,
                strategy_version TEXT NOT NULL,
                dataset_fingerprint TEXT NOT NULL,
                model TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                summary TEXT,
                strengths TEXT,
                weaknesses TEXT,
                recommendations TEXT,
                confidence_score REAL,
                raw_response_json TEXT,
                raw_response_md TEXT,
                tokens_estimated INTEGER,
                duration_seconds REAL
            );
            CREATE TABLE IF NOT EXISTS optimization_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy TEXT NOT NULL,
                strategy_version TEXT NOT NULL,
                dataset_fingerprint TEXT NOT NULL,
                parameters TEXT NOT NULL,
                metrics TEXT NOT NULL,
                stability_score REAL NOT NULL,
                ranking INTEGER,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS orchestrator_runs (
                run_id TEXT PRIMARY KEY,
                strategy TEXT NOT NULL,
                dataset_fingerprint TEXT NOT NULL,
                max_generations INTEGER NOT NULL,
                max_variants INTEGER NOT NULL,
                started_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS orchestrator_generations (
                generation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                generation_index INTEGER NOT NULL,
                ai_diagnostics TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS orchestrator_variants (
                variant_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                generation_index INTEGER NOT NULL,
                variant_name TEXT NOT NULL,
                parameters TEXT NOT NULL,
                train_metrics TEXT NOT NULL,
                val_metrics TEXT NOT NULL,
                stability_score REAL NOT NULL,
                validation_stability_score REAL NOT NULL,
                deployment_score REAL NOT NULL,
                ranking INTEGER NOT NULL,
                warnings TEXT
            );
            """
        )
        self.conn.commit()

        # Programmatically run migrations for older DB schemas
        try:
            self.conn.execute("ALTER TABLE backtest_runs ADD COLUMN dataset_fingerprint TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            self.conn.execute("ALTER TABLE orchestrator_variants ADD COLUMN warnings TEXT")
        except sqlite3.OperationalError:
            pass

        alter_trades = [
            ("strategy_version", "TEXT"),
            ("commission", "REAL"),
            ("rsi", "REAL"),
            ("atr", "REAL"),
            ("volume_ratio", "REAL"),
            ("momentum", "REAL"),
            ("signal_strength", "INTEGER"),
            ("session", "TEXT"),
            ("market_regime", "TEXT"),
            ("trade_duration_minutes", "REAL"),
            ("outlier_flag", "INTEGER")
        ]
        for col, col_type in alter_trades:
            try:
                self.conn.execute(f"ALTER TABLE trades ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                pass
        self.conn.commit()

    def save_backtest(self, strategy_name: str, config: dict, metrics: dict, trades: list[dict], events: list[dict], dataset_fingerprint: str = "unknown") -> int:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO backtest_runs(strategy, metrics_json, config_json, dataset_fingerprint) VALUES (?, ?, ?, ?)",
            (strategy_name, json.dumps(metrics), json.dumps(config), dataset_fingerprint),
        )
        run_id = cur.lastrowid
        for trade in trades:
            cur.execute(
                """
                INSERT INTO trades(
                    run_id, ticket, direction, entry_time, entry_price, exit_time, exit_price, profit, exit_reason,
                    strategy_version, commission, rsi, atr, volume_ratio, momentum, signal_strength, session, market_regime,
                    trade_duration_minutes, outlier_flag
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    trade.get("ticket"),
                    trade.get("direction"),
                    str(trade.get("entry_time")),
                    trade.get("entry_price"),
                    str(trade.get("exit_time")),
                    trade.get("exit_price"),
                    trade.get("profit"),
                    trade.get("exit_reason"),
                    trade.get("strategy_version", "1.0.0"),
                    trade.get("commission", 0.0),
                    trade.get("rsi"),
                    trade.get("atr"),
                    trade.get("volume_ratio"),
                    trade.get("momentum"),
                    trade.get("signal_strength"),
                    trade.get("session"),
                    trade.get("market_regime"),
                    trade.get("trade_duration_minutes"),
                    trade.get("outlier_flag", 0)
                ),
            )
        for event in events:
            cur.execute(
                "INSERT INTO event_logs(run_id, timestamp, level, message) VALUES (?, ?, ?, ?)",
                (run_id, event["timestamp"], event["level"], event["message"]),
            )
        self.conn.commit()
        return run_id

    def save_ai_analysis(self, strategy: str, version: str, fingerprint: str, model: str, data: dict) -> int:
        import datetime
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO ai_analyses (
                strategy, strategy_version, dataset_fingerprint, model, timestamp,
                summary, strengths, weaknesses, recommendations, confidence_score,
                raw_response_json, raw_response_md, tokens_estimated, duration_seconds
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                strategy,
                version,
                fingerprint,
                model,
                datetime.datetime.now().isoformat(),
                data.get("summary", ""),
                json.dumps(data.get("strengths", [])),
                json.dumps(data.get("weaknesses", [])),
                json.dumps(data.get("recommendations", [])),
                float(data.get("confidence_score", 0.0)),
                json.dumps(data),
                data.get("raw_response_md", ""),
                int(data.get("tokens_estimated", 0)),
                float(data.get("duration_seconds", 0.0))
            )
        )
        self.conn.commit()
        return cur.lastrowid

    def save_optimization_run(self, strategy: str, version: str, fingerprint: str, params: dict, metrics: dict, stability: float, ranking: int) -> int:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO optimization_runs (
                strategy, strategy_version, dataset_fingerprint, parameters, metrics, stability_score, ranking
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                strategy,
                version,
                fingerprint,
                json.dumps(params),
                json.dumps(metrics),
                float(stability),
                int(ranking)
            )
        )
        self.conn.commit()
        return cur.lastrowid
