"""Prometheus metrics exporter for telemetry and trading engine.

This module provides Prometheus-compatible metrics for monitoring the trading engine,
including cycle execution, profitability, and operational health.
"""

from __future__ import annotations

from typing import Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class PrometheusMetric:
    """A Prometheus metric.
    
    Attributes:
        name: Metric name (e.g., 'eve_cycles_total').
        metric_type: Type of metric (counter, gauge, histogram, summary).
        help_text: Help text describing the metric.
        value: Current metric value.
        labels: Dictionary of label names and values.
        timestamp: When metric was recorded.
    """
    name: str
    metric_type: str
    help_text: str
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: Optional[str] = None

    def __post_init__(self) -> None:
        """Initialize timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_prometheus_line(self) -> str:
        """Format metric as Prometheus text exposition format line.
        
        Returns:
            Prometheus format string for this metric.
        """
        labels_str = ""
        if self.labels:
            label_pairs = [f'{k}="{v}"' for k, v in self.labels.items()]
            labels_str = "{" + ",".join(label_pairs) + "}"
        return f"{self.name}{labels_str} {self.value}"


class PrometheusRegistry:
    """Registry for Prometheus metrics.
    
    Example:
        >>> registry = PrometheusRegistry()
        >>> registry.counter_inc('eve_cycles_total', labels={'mode': 'shadow'})
        >>> registry.gauge_set('eve_profit_eth', 0.5, labels={'chain': 'base'})
        >>> text = registry.export_text()
    """

    def __init__(self) -> None:
        """Initialize metrics registry."""
        self.metrics: Dict[str, PrometheusMetric] = {}
        self._initialize_core_metrics()

    def _initialize_core_metrics(self) -> None:
        """Initialize core EVE_Q metrics."""
        core_metrics = [
            ("eve_cycles_total", "counter", "Total cycles executed"),
            ("eve_cycles_success", "counter", "Successfully executed cycles"),
            ("eve_cycles_failed", "counter", "Failed cycles"),
            ("eve_profit_eth_total", "gauge", "Total profit in ETH"),
            ("eve_profit_eth_last_cycle", "gauge", "Profit from last cycle in ETH"),
            ("eve_gas_cost_eth_total", "gauge", "Total gas costs in ETH"),
            ("eve_slippage_eth_total", "gauge", "Total slippage in ETH"),
            ("eve_charity_distributed_eth", "gauge", "Total charity distributed in ETH"),
            ("eve_cycle_duration_seconds", "histogram", "Cycle execution duration in seconds"),
            ("eve_routes_evaluated", "histogram", "Number of routes evaluated per cycle"),
            ("eve_execution_success_ratio", "gauge", "Execution success ratio (0-1)"),
            ("eve_trust_level", "gauge", "Current trust level for execution"),
            ("eve_alerts_dispatched", "counter", "Total alerts dispatched"),
            ("eve_alerts_delivered", "counter", "Alerts successfully delivered"),
        ]
        for name, mtype, help_text in core_metrics:
            self.metrics[name] = PrometheusMetric(
                name=name,
                metric_type=mtype,
                help_text=help_text,
                value=0.0,
            )

    def _make_key(self, name: str, labels: Optional[Dict[str, str]] = None) -> str:
        """Create a unique key for a metric with labels.
        
        Args:
            name: Metric name.
            labels: Label dictionary.
            
        Returns:
            Unique key for storing the metric.
        """
        if not labels:
            return name
        label_str = "|".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}[{label_str}]"

    def counter_inc(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """Increment a counter metric.
        
        Args:
            name: Metric name.
            value: Amount to increment by (default 1.0).
            labels: Optional labels.
        """
        key = self._make_key(name, labels)
        if key not in self.metrics:
            self.metrics[key] = PrometheusMetric(
                name=name,
                metric_type="counter",
                help_text="",
                value=0.0,
                labels=labels or {},
            )
        self.metrics[key].value += value
        self.metrics[key].timestamp = datetime.now(timezone.utc).isoformat()

    def gauge_set(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Set a gauge metric.
        
        Args:
            name: Metric name.
            value: Value to set.
            labels: Optional labels.
        """
        key = self._make_key(name, labels)
        if key not in self.metrics:
            self.metrics[key] = PrometheusMetric(
                name=name,
                metric_type="gauge",
                help_text="",
                value=value,
                labels=labels or {},
            )
        else:
            self.metrics[key].value = value
        self.metrics[key].timestamp = datetime.now(timezone.utc).isoformat()

    def gauge_add(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Add to a gauge metric.
        
        Args:
            name: Metric name.
            value: Amount to add.
            labels: Optional labels.
        """
        key = self._make_key(name, labels)
        if key not in self.metrics:
            self.metrics[key] = PrometheusMetric(
                name=name,
                metric_type="gauge",
                help_text="",
                value=value,
                labels=labels or {},
            )
        else:
            self.metrics[key].value += value
        self.metrics[key].timestamp = datetime.now(timezone.utc).isoformat()

    def histogram_observe(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Record a histogram observation.
        
        Args:
            name: Metric name.
            value: Value to observe.
            labels: Optional labels.
        """
        # For simplicity, store as gauge (production would use full histogram buckets)
        self.gauge_set(name, value, labels)

    def export_text(self) -> str:
        """Export metrics in Prometheus text exposition format.
        
        Returns:
            Prometheus format text representation of all metrics.
        """
        lines: list[str] = []
        last_help: Optional[str] = None
        last_type: Optional[str] = None

        for key in sorted(self.metrics.keys()):
            metric = self.metrics[key]
            if metric.help_text != last_help:
                lines.append(f"# HELP {metric.name} {metric.help_text}")
                last_help = metric.help_text
            if metric.metric_type != last_type:
                lines.append(f"# TYPE {metric.name} {metric.metric_type}")
                last_type = metric.metric_type
            lines.append(metric.to_prometheus_line())

        return "\n".join(lines) + "\n"

    def get_metric(self, name: str, labels: Optional[Dict[str, str]] = None) -> Optional[float]:
        """Get a metric value.
        
        Args:
            name: Metric name.
            labels: Optional labels.
            
        Returns:
            Metric value or None if not found.
        """
        key = self._make_key(name, labels)
        metric = self.metrics.get(key)
        return metric.value if metric else None
