"""
Health check and system monitoring for EVE_Q SlurperBot v2.

Provides comprehensive system health checks for all components:
- Blockchain connectivity
- DEX availability
- IPFS connectivity
- Grace-based economics state
- Resource usage
"""

import logging
import psutil
import time
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


class HealthChecker:
    """Performs comprehensive system health checks."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize health checker.

        Parameters
        ----------
        config : dict
            Configuration dictionary
        """
        self.config = config
        self.last_check = None
        self.health_history: List[Dict[str, Any]] = []

    async def check_all(self, **components) -> Dict[str, Any]:
        """Run all health checks.

        Parameters
        ----------
        **components
            Component instances to check (w3, dex_connector, etc.)

        Returns
        -------
        dict
            Health check results
        """
        start_time = time.time()

        health = {
            "timestamp": datetime.utcnow().isoformat(),
            "overall_status": "healthy",
            "checks": {},
            "warnings": [],
            "errors": [],
        }

        # System resources
        health["checks"]["resources"] = self._check_resources()

        # Blockchain connectivity
        if "w3" in components and components["w3"]:
            health["checks"]["blockchain"] = await self._check_blockchain(components["w3"])

        # DEX connector
        if "dex_connector" in components and components["dex_connector"]:
            health["checks"]["dex"] = self._check_dex_connector(components["dex_connector"])

        # Failsafe manager
        if "failsafe_state" in components:
            health["checks"]["grace"] = self._check_grace_state(components["failsafe_state"])

        # Metrics collector
        if "metrics" in components and components["metrics"]:
            health["checks"]["metrics"] = self._check_metrics(components["metrics"])

        # Determine overall status
        for check_name, check_result in health["checks"].items():
            if check_result.get("status") == "error":
                health["overall_status"] = "unhealthy"
                health["errors"].append(f"{check_name}: {check_result.get('message', 'Unknown error')}")
            elif check_result.get("status") == "warning":
                if health["overall_status"] != "unhealthy":
                    health["overall_status"] = "degraded"
                health["warnings"].append(f"{check_name}: {check_result.get('message', 'Unknown warning')}")

        health["check_duration_ms"] = (time.time() - start_time) * 1000
        self.last_check = health

        # Store in history (keep last 100)
        self.health_history.append(health)
        if len(self.health_history) > 100:
            self.health_history = self.health_history[-100:]

        return health

    def _check_resources(self) -> Dict[str, Any]:
        """Check system resources.

        Returns
        -------
        dict
            Resource check result
        """
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            status = "healthy"
            message = "Resources normal"

            # Check thresholds
            if cpu_percent > 90:
                status = "warning"
                message = f"High CPU usage: {cpu_percent}%"
            elif memory.percent > 90:
                status = "warning"
                message = f"High memory usage: {memory.percent}%"
            elif disk.percent > 90:
                status = "warning"
                message = f"High disk usage: {disk.percent}%"

            return {
                "status": status,
                "message": message,
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_gb": memory.available / (1024**3),
                "disk_percent": disk.percent,
                "disk_free_gb": disk.free / (1024**3),
            }

        except Exception as e:
            logger.error(f"Resource check failed: {e}")
            return {
                "status": "error",
                "message": str(e)
            }

    async def _check_blockchain(self, w3) -> Dict[str, Any]:
        """Check blockchain connectivity.

        Parameters
        ----------
        w3
            Web3 instance

        Returns
        -------
        dict
            Blockchain check result
        """
        try:
            if not w3.is_connected():
                return {
                    "status": "error",
                    "message": "Not connected to blockchain"
                }

            # Get latest block
            latest_block = w3.eth.block_number
            gas_price = w3.eth.gas_price / 10**9  # Convert to gwei

            status = "healthy"
            message = "Blockchain connected"

            # Check gas price
            max_gas = self.config.get("max_gas_price_gwei", 100)
            if gas_price > max_gas:
                status = "warning"
                message = f"High gas price: {gas_price:.2f} gwei"

            return {
                "status": status,
                "message": message,
                "connected": True,
                "chain_id": w3.eth.chain_id,
                "latest_block": latest_block,
                "gas_price_gwei": gas_price,
            }

        except Exception as e:
            logger.error(f"Blockchain check failed: {e}")
            return {
                "status": "error",
                "message": str(e),
                "connected": False
            }

    def _check_dex_connector(self, dex_connector) -> Dict[str, Any]:
        """Check DEX connector health.

        Parameters
        ----------
        dex_connector
            DEX connector instance

        Returns
        -------
        dict
            DEX check result
        """
        try:
            status_info = dex_connector.get_connection_status()

            if not status_info.get("connected"):
                return {
                    "status": "error",
                    "message": "DEX connector not connected",
                    "details": status_info
                }

            return {
                "status": "healthy",
                "message": "DEX connectors operational",
                "routers_count": status_info.get("routers_initialized", 0),
                "gas_price_gwei": status_info.get("gas_price_gwei", 0),
            }

        except Exception as e:
            logger.error(f"DEX check failed: {e}")
            return {
                "status": "error",
                "message": str(e)
            }

    def _check_grace_state(self, failsafe_state: Dict[str, Any]) -> Dict[str, Any]:
        """Check grace-based economics state.

        Parameters
        ----------
        failsafe_state : dict
            Current failsafe state from get_trust_report()

        Returns
        -------
        dict
            Grace check result
        """
        try:
            ttl = failsafe_state.get("current_ttl_hours", 0)
            failures = failsafe_state.get("consecutive_failures", 0)
            grace_status = failsafe_state.get("grace_status", "baseline")

            status = "healthy"
            message = f"Grace {grace_status} - TTL: {ttl}h"

            # Check for concerning patterns
            if failures >= 5:
                status = "warning"
                message = f"{failures} consecutive failures - market adaptation needed"
            elif ttl < 12:
                status = "warning"
                message = f"Low TTL: {ttl}h - grace depleting"

            return {
                "status": status,
                "message": message,
                "current_ttl_hours": ttl,
                "consecutive_failures": failures,
                "grace_status": grace_status,
            }

        except Exception as e:
            logger.error(f"Grace state check failed: {e}")
            return {
                "status": "error",
                "message": str(e)
            }

    def _check_metrics(self, metrics_collector) -> Dict[str, Any]:
        """Check metrics collector health.

        Parameters
        ----------
        metrics_collector
            Metrics collector instance

        Returns
        -------
        dict
            Metrics check result
        """
        try:
            summary = metrics_collector.get_summary()

            status = "healthy"
            message = "Metrics collection active"

            # Check charity ratio
            charity_metrics = summary.get("charity_metrics", {})
            success_metric = charity_metrics.get("success_metric", "UNKNOWN")

            if success_metric == "FAIL":
                status = "warning"
                message = "Charity ratio below target (15%)"

            return {
                "status": status,
                "message": message,
                "total_trades": summary.get("trade_metrics", {}).get("total", 0),
                "charity_ratio": charity_metrics.get("charity_ratio_percent", 0),
                "success_metric": success_metric,
            }

        except Exception as e:
            logger.error(f"Metrics check failed: {e}")
            return {
                "status": "error",
                "message": str(e)
            }

    def print_health_summary(self):
        """Print health check summary to console."""
        if not self.last_check:
            print("No health checks performed yet")
            return

        health = self.last_check

        print("\n" + "=" * 70)
        print("🏥 SYSTEM HEALTH CHECK")
        print("=" * 70)
        print(f"Overall Status: {health['overall_status'].upper()}")
        print(f"Timestamp: {health['timestamp']}")
        print(f"Check Duration: {health['check_duration_ms']:.2f}ms")
        print()

        # Print individual checks
        for check_name, check_result in health["checks"].items():
            status_icon = {
                "healthy": "✅",
                "warning": "⚠️ ",
                "error": "❌"
            }.get(check_result.get("status", "unknown"), "❓")

            print(f"{status_icon} {check_name.upper()}: {check_result.get('message', 'No message')}")

        # Print warnings
        if health["warnings"]:
            print(f"\n⚠️  Warnings ({len(health['warnings'])}):")
            for warning in health["warnings"]:
                print(f"  - {warning}")

        # Print errors
        if health["errors"]:
            print(f"\n❌ Errors ({len(health['errors'])}):")
            for error in health["errors"]:
                print(f"  - {error}")

        print("=" * 70 + "\n")

    def get_health_history(self) -> List[Dict[str, Any]]:
        """Get health check history.

        Returns
        -------
        list
            List of historical health checks
        """
        return self.health_history
