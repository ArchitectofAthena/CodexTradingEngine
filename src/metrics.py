"""
Metrics and monitoring for EVE_Q SlurperBot v2.

Tracks system health, performance, and grace-based economics metrics.
Provides Prometheus-compatible metrics export for monitoring dashboards.
"""

import time
import json
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime, timedelta
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects and exports system metrics."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize metrics collector.

        Parameters
        ----------
        config : dict
            Configuration with metrics settings
        """
        self.config = config
        self.metrics_dir = Path(config.get("metrics_dir", "data/metrics"))
        self.metrics_dir.mkdir(exist_ok=True, parents=True)

        # Metrics storage
        self.counters: Dict[str, float] = defaultdict(float)
        self.gauges: Dict[str, float] = defaultdict(float)
        self.histograms: Dict[str, List[float]] = defaultdict(list)

        # Timing
        self.start_time = time.time()
        self.last_save = time.time()

        logger.info("Metrics collector initialized")

    def increment(self, metric: str, value: float = 1.0):
        """Increment a counter metric.

        Parameters
        ----------
        metric : str
            Metric name
        value : float
            Amount to increment (default 1.0)
        """
        self.counters[metric] += value

    def gauge(self, metric: str, value: float):
        """Set a gauge metric.

        Parameters
        ----------
        metric : str
            Metric name
        value : float
            Current value
        """
        self.gauges[metric] = value

    def histogram(self, metric: str, value: float):
        """Record a histogram value.

        Parameters
        ----------
        metric : str
            Metric name
        value : float
            Value to record
        """
        self.histograms[metric].append(value)

        # Keep only last 1000 values
        if len(self.histograms[metric]) > 1000:
            self.histograms[metric] = self.histograms[metric][-1000:]

    def record_trade(self, trade_data: Dict[str, Any]):
        """Record trade execution metrics.

        Parameters
        ----------
        trade_data : dict
            Trade execution data
        """
        # Counters
        if trade_data.get("success"):
            self.increment("trades_successful")
            profit = trade_data.get("net_profit", 0)
            charity = trade_data.get("charity_amount", 0)

            self.increment("total_profit_eth", profit)
            self.increment("total_charity_eth", charity)

            # Histograms
            self.histogram("profit_per_trade", profit)
            self.histogram("charity_per_trade", charity)
        else:
            self.increment("trades_failed")

        # Total trades
        self.increment("trades_total")

    def record_grace_event(self, event_type: str, ttl_change: float):
        """Record grace-based economics event.

        Parameters
        ----------
        event_type : str
            Event type ('expansion', 'maintenance', 'decay')
        ttl_change : float
            TTL change in hours
        """
        self.increment(f"grace_events_{event_type}")
        self.histogram("ttl_changes", ttl_change)

    def record_quantum_optimization(self, optimization_data: Dict[str, Any]):
        """Record quantum optimization metrics.

        Parameters
        ----------
        optimization_data : dict
            Optimization result data
        """
        duration = optimization_data.get("duration_ms", 0)
        routes_evaluated = optimization_data.get("routes_evaluated", 0)

        self.histogram("quantum_optimization_duration_ms", duration)
        self.increment("quantum_optimizations_total")

        if optimization_data.get("fallback_classical"):
            self.increment("quantum_fallback_classical")

    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary.

        Returns
        -------
        dict
            Metrics summary
        """
        uptime = time.time() - self.start_time

        # Calculate histogram statistics
        histogram_stats = {}
        for metric, values in self.histograms.items():
            if values:
                histogram_stats[metric] = {
                    "count": len(values),
                    "min": min(values),
                    "max": max(values),
                    "mean": sum(values) / len(values),
                }

        # Calculate charity metrics
        total_profit = self.counters.get("total_profit_eth", 0)
        total_charity = self.counters.get("total_charity_eth", 0)

        charity_ratio = 0
        if total_profit > 0:
            charity_ratio = (total_charity / total_profit) * 100

        # Grace metrics
        grace_events = {
            "expansion": self.counters.get("grace_events_expansion", 0),
            "maintenance": self.counters.get("grace_events_maintenance", 0),
            "decay": self.counters.get("grace_events_decay", 0),
        }

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_seconds": uptime,
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "histogram_stats": histogram_stats,
            "charity_metrics": {
                "total_profit_eth": total_profit,
                "total_charity_eth": total_charity,
                "charity_ratio_percent": charity_ratio,
                "success_metric": "PASS" if total_charity >= total_profit * 0.15 else "FAIL",
            },
            "grace_metrics": {
                "events": grace_events,
                "total_events": sum(grace_events.values()),
            },
            "trade_metrics": {
                "total": self.counters.get("trades_total", 0),
                "successful": self.counters.get("trades_successful", 0),
                "failed": self.counters.get("trades_failed", 0),
                "success_rate": (
                    self.counters.get("trades_successful", 0) /
                    max(self.counters.get("trades_total", 1), 1) * 100
                ),
            },
        }

    def save_metrics(self):
        """Save metrics to file."""
        try:
            summary = self.get_summary()
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            metrics_file = self.metrics_dir / f"metrics_{timestamp}.json"

            with open(metrics_file, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2)

            self.last_save = time.time()
            logger.info(f"Metrics saved to {metrics_file}")

        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")

    def export_prometheus(self) -> str:
        """Export metrics in Prometheus format.

        Returns
        -------
        str
            Prometheus-formatted metrics
        """
        lines = []

        # Counters
        for metric, value in self.counters.items():
            metric_name = f"eve_q_{metric.replace('.', '_')}"
            lines.append(f"# TYPE {metric_name} counter")
            lines.append(f"{metric_name} {value}")

        # Gauges
        for metric, value in self.gauges.items():
            metric_name = f"eve_q_{metric.replace('.', '_')}"
            lines.append(f"# TYPE {metric_name} gauge")
            lines.append(f"{metric_name} {value}")

        # Histograms (simplified - just avg/min/max)
        for metric, values in self.histograms.items():
            if not values:
                continue

            metric_name = f"eve_q_{metric.replace('.', '_')}"
            lines.append(f"# TYPE {metric_name} summary")
            lines.append(f"{metric_name}_count {len(values)}")
            lines.append(f"{metric_name}_sum {sum(values)}")
            lines.append(f"{metric_name}_min {min(values)}")
            lines.append(f"{metric_name}_max {max(values)}")
            lines.append(f"{metric_name}_avg {sum(values) / len(values)}")

        return "\n".join(lines)

    def print_summary(self):
        """Print metrics summary to console."""
        summary = self.get_summary()

        print("\n" + "=" * 70)
        print("📊 METRICS SUMMARY")
        print("=" * 70)
        print(f"Uptime: {summary['uptime_seconds'] / 3600:.2f} hours")
        print(f"\nTrade Metrics:")
        print(f"  Total: {summary['trade_metrics']['total']}")
        print(f"  Successful: {summary['trade_metrics']['successful']}")
        print(f"  Failed: {summary['trade_metrics']['failed']}")
        print(f"  Success Rate: {summary['trade_metrics']['success_rate']:.2f}%")
        print(f"\nCharity Metrics:")
        print(f"  Total Profit: {summary['charity_metrics']['total_profit_eth']:.6f} ETH")
        print(f"  Total Charity: {summary['charity_metrics']['total_charity_eth']:.6f} ETH")
        print(f"  Charity Ratio: {summary['charity_metrics']['charity_ratio_percent']:.2f}%")
        print(f"  Success Metric: {summary['charity_metrics']['success_metric']}")
        print(f"\nGrace Events:")
        for event, count in summary['grace_metrics']['events'].items():
            print(f"  {event.capitalize()}: {count}")
        print("=" * 70 + "\n")
