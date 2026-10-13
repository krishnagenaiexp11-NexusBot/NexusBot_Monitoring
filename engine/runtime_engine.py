import time

from engine.backtest_engine import BacktestEngine


class PaperRuntime:
    def __init__(self, strategy, event_bus, delay_seconds: float = 0.0):
        self.strategy = strategy
        self.event_bus = event_bus
        self.delay_seconds = delay_seconds

    def run_dataset(self, df):
        self.event_bus.emit("PAPER RUNTIME STARTED")
        if self.delay_seconds > 0:
            for _ in range(min(len(df), 5)):
                time.sleep(self.delay_seconds)
        result = BacktestEngine(self.strategy, event_bus=self.event_bus).run(df)
        self.event_bus.emit("PAPER RUNTIME FINISHED")
        return result
