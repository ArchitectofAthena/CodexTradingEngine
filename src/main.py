"""
Main orchestrator for the EVE_Q SlurperBot v2 - Grace Economy Edition.

This module integrates quantum optimization, failsafe management, multi-charity
distribution, and IPFS logging into a cohesive system that treats altruism as
the core reward mechanism.

Philosophy:
- Every trade feeds the hungry
- Charity is the dopamine hit
- No punishment, only missed rewards
- Grace-based economics in action
- ETH distributed > ETH accumulated

Usage:
    python src/main.py
"""

import os
import json
import sys
import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from decimal import Decimal

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Import local modules
from quantum_optimizer import optimize_routes
from upgrade_scanner import scan_for_upgrades
from failsafe_manager import (
    check_liveness,
    update_liveness_token,
    progressive_trust_increment,
    get_trust_report,
)
from ipfs_charity_logger import CharityDistributor
from logger_config import setup_logging, get_logger
from metrics import MetricsCollector
from health_check import HealthChecker

# Optional imports (check if available)
try:
    from dex_connector import DEXConnector
    from flash_loan_executor import FlashLoanExecutor
    from web3 import Web3
    WEB3_AVAILABLE = True
except ImportError:
    WEB3_AVAILABLE = False
    DEXConnector = None
    FlashLoanExecutor = None
    Web3 = None

logger = None  # Will be initialized after logging setup


def load_strategy_config(config_path: str) -> Dict[str, Any]:
    """Load the strategy configuration from a YAML file.

    Parameters
    ----------
    config_path: str
        The path to the strategy YAML configuration file.

    Returns
    -------
    dict
        A dictionary with configuration parameters.

    Raises
    ------
    ValueError
        If configuration validation fails.
    FileNotFoundError
        If config file doesn't exist.
    """
    import yaml  # type: ignore

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in configuration file: {e}")

    # Merge environment variables (override YAML with env vars)
    cfg = _merge_env_vars(cfg)

    # Validate configuration
    _validate_config(cfg)
    return cfg


def _merge_env_vars(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Merge environment variables into configuration.

    Environment variables take precedence over YAML config.

    Parameters
    ----------
    cfg : dict
        Base configuration from YAML

    Returns
    -------
    dict
        Configuration with env vars merged
    """
    # Execution settings
    if "execution" not in cfg:
        cfg["execution"] = {}

    cfg["execution"]["simulation_mode"] = (
        os.getenv("SIMULATION_MODE", "true").lower() == "true"
    )

    # RPC URL
    rpc_url = os.getenv("ETHEREUM_RPC_URL")
    if rpc_url:
        cfg["rpc_url"] = rpc_url

    # Private key (only if not in simulation mode)
    if not cfg["execution"]["simulation_mode"]:
        private_key = os.getenv("PRIVATE_KEY")
        if private_key:
            cfg["private_key"] = private_key

    # Safety limits
    if "safety" not in cfg:
        cfg["safety"] = {}

    max_gas = os.getenv("MAX_GAS_PRICE_GWEI")
    if max_gas:
        cfg["execution"]["max_gas_price_gwei"] = float(max_gas)

    min_profit = os.getenv("MIN_PROFIT_ETH")
    if min_profit:
        cfg["execution"]["min_profit_eth"] = float(min_profit)

    # Logging
    log_level = os.getenv("LOG_LEVEL")
    if log_level:
        cfg["logging"]["level"] = log_level

    log_dir = os.getenv("LOG_DIR")
    if log_dir:
        cfg["logging"]["log_dir"] = log_dir

    return cfg


def _validate_config(cfg: Dict[str, Any]) -> None:
    """Validate configuration parameters.

    Parameters
    ----------
    cfg: dict
        Configuration dictionary to validate.

    Raises
    ------
    ValueError
        If any configuration parameter is invalid.
    """
    # Validate charity percentage
    charity_cfg = cfg.get("charity", {})
    charity_pct = charity_cfg.get("percentage", 0)
    if not isinstance(charity_pct, (int, float)):
        raise ValueError(f"Charity percentage must be numeric, got {type(charity_pct)}")
    if not 0 <= charity_pct <= 1:
        raise ValueError(f"Charity percentage must be between 0 and 1, got {charity_pct}")

    # Validate charity distribution
    distribution = charity_cfg.get("distribution", [])
    if not distribution:
        raise ValueError("At least one charity must be configured")

    total_allocation = 0.0
    for i, charity in enumerate(distribution):
        if "name" not in charity or "address" not in charity:
            raise ValueError(f"Charity {i} missing name or address")
        allocation = charity.get("allocation", 0)
        if not 0 <= allocation <= 1:
            raise ValueError(f"Charity {charity.get('name')} allocation must be 0-1, got {allocation}")
        total_allocation += allocation

    if abs(total_allocation - 1.0) > 0.01:
        raise ValueError(f"Charity allocations must sum to 1.0, got {total_allocation}")

    # Validate failsafe TTL
    failsafe_cfg = cfg.get("failsafe", {})
    ttl_hours = failsafe_cfg.get("ttl_hours", 24)
    if not isinstance(ttl_hours, (int, float)) or ttl_hours <= 0:
        raise ValueError(f"Failsafe TTL must be positive number, got {ttl_hours}")

    max_ttl = failsafe_cfg.get("max_ttl_hours", 48)
    if not isinstance(max_ttl, (int, float)) or max_ttl < ttl_hours:
        raise ValueError(f"Max TTL must be >= TTL, got max={max_ttl}, ttl={ttl_hours}")

    logger.info("✓ Configuration validation passed")
    logger.info(f"  Charity: {charity_pct*100}% to {len(distribution)} organizations")
    logger.info(f"  Simulation mode: {cfg.get('execution', {}).get('simulation_mode', True)}")
    logger.info(f"  Ethos: Grace-based economics ACTIVE")


async def run_arbitrage_cycle(
    cfg: Dict[str, Any],
    charity_distributor: CharityDistributor,
    metrics: MetricsCollector,
    dex_connector: Optional[Any] = None,
    flash_executor: Optional[Any] = None
) -> Dict[str, Any]:
    """Run one complete arbitrage cycle.

    Parameters
    ----------
    cfg : dict
        Configuration
    charity_distributor : CharityDistributor
        Charity distribution manager
    metrics : MetricsCollector
        Metrics collector
    dex_connector : optional
        DEX connector for real price data
    flash_executor : optional
        Flash loan executor

    Returns
    -------
    dict
        Cycle result
    """
    failsafe_cfg = cfg.get("failsafe", {})
    charity_cfg = cfg.get("charity", {})
    charity_pct = charity_cfg.get("percentage", 0.15)

    try:
        # Step 1: Scan for upgrades
        logger.info("🔍 Scanning for upgrades...")
        upgrades = scan_for_upgrades(cfg.get("upgrade", {}))
        if upgrades:
            for upgrade in upgrades:
                logger.info(f"   • {upgrade}")

        # Step 2: Fetch arbitrage routes
        logger.info("💹 Fetching arbitrage routes...")

        if dex_connector:
            # Use real DEX data
            logger.info("   Using live DEX data")
            routes_list = await dex_connector.find_arbitrage_routes(Decimal("1.0"))

            if not routes_list:
                logger.warning("   No profitable routes found")
                return {"success": False, "reason": "no_routes"}

            # Convert to dict format for quantum optimizer
            candidate_routes = {}
            for i, route in enumerate(routes_list[:10]):  # Top 10 routes
                # Estimate gas cost
                gas_cost = await dex_connector.estimate_gas_cost(route)

                candidate_routes[route["name"]] = {
                    "profit": route["gross_profit"],
                    "risk": 0.0001,  # TODO: Calculate actual risk
                    "gas_cost": float(gas_cost),
                }
        else:
            # Use simulated data
            logger.info("   Using simulated data (no DEX connector)")
            candidate_routes = {
                "ETH->USDC->ETH (Uniswap→SushiSwap)": {
                    "profit": 0.01,
                    "risk": 0.001,
                    "gas_cost": 0.005,
                },
                "ETH->DAI->ETH (SushiSwap→Uniswap)": {
                    "profit": 0.012,
                    "risk": 0.0007,
                    "gas_cost": 0.004,
                },
                "ETH->USDT->ETH (Uniswap→Uniswap)": {
                    "profit": 0.008,
                    "risk": 0.0005,
                    "gas_cost": 0.003,
                },
            }

        logger.info(f"   Found {len(candidate_routes)} candidate routes")

        # Step 3: Optimize using QAOA
        logger.info("🌀 Optimizing routes using QAOA...")
        quantum_start = time.time()

        try:
            best_route = optimize_routes(candidate_routes)
            route_data = candidate_routes[best_route]

            quantum_duration = (time.time() - quantum_start) * 1000
            metrics.record_quantum_optimization({
                "duration_ms": quantum_duration,
                "routes_evaluated": len(candidate_routes),
                "fallback_classical": False  # TODO: Detect if fell back
            })

            logger.info(f"✓ Best route: {best_route}")
            logger.info(f"   Expected profit: {route_data['profit']:.6f} ETH")
            logger.info(f"   Gas cost: {route_data['gas_cost']:.6f} ETH")

        except Exception as e:
            logger.error(f"❌ Route optimization failed: {e}")
            metrics.increment("quantum_optimization_failures")
            return {"success": False, "reason": "optimization_failed", "error": str(e)}

        # Step 4: Execute arbitrage
        logger.info("💸 Executing arbitrage...")

        if flash_executor:
            # Use real flash loan executor
            route_with_name = {**route_data, "name": best_route}
            result = await flash_executor.execute_arbitrage(route_with_name, charity_pct)
        else:
            # Simulate execution
            gross_profit = Decimal(str(route_data["profit"]))
            gas_cost = Decimal(str(route_data["gas_cost"]))
            flash_loan_amount = Decimal("1.0")
            flash_loan_fee = flash_loan_amount * Decimal("0.0009")  # 0.09%

            net_profit = gross_profit - gas_cost - flash_loan_fee

            result = {
                "success": net_profit > 0,
                "simulation": True,
                "route": best_route,
                "gross_profit": float(gross_profit),
                "gas_cost": float(gas_cost),
                "flash_loan_fee": float(flash_loan_fee),
                "net_profit": float(net_profit),
            }

        # Step 5: Charity distribution
        if result["success"] and result["net_profit"] > 0:
            net_profit = Decimal(str(result["net_profit"]))
            charity_amount = net_profit * Decimal(str(charity_pct))
            profit_after_charity = net_profit - charity_amount

            # Distribute charity
            charity_distributions = charity_distributor.distribute_donation(float(charity_amount))

            # Check monthly extraction
            monthly_extractions = charity_distributor.check_monthly_extraction()

            result["charity_amount"] = float(charity_amount)
            result["profit_after_charity"] = float(profit_after_charity)
            result["charity_distributions"] = charity_distributions
            result["monthly_extractions"] = monthly_extractions

            logger.info(f"✓ Net profit: {net_profit:.6f} ETH")
            logger.info(f"  Charity ({charity_pct*100}%): {charity_amount:.6f} ETH")
            logger.info(f"  Profit after charity: {profit_after_charity:.6f} ETH")
            logger.info("  💝 Dopamine hit: Charity executed successfully!")

            # Record success metrics
            metrics.record_trade(result)

            return {"success": True, "result": result}

        else:
            logger.warning("⏸️  No profit this cycle - charity not executed")
            logger.info("   Grace maintained - this is not a punishment")

            metrics.record_trade(result)

            return {"success": False, "reason": "no_profit", "result": result}

    except Exception as e:
        logger.error(f"❌ Cycle failed: {e}", exc_info=True)
        metrics.increment("cycle_failures")
        return {"success": False, "reason": "exception", "error": str(e)}


async def main() -> None:
    """Entry point for the EVE_Q orchestrator."""
    global logger

    try:
        # Load configuration
        root_dir = Path(__file__).resolve().parent.parent
        cfg_path = root_dir / "config" / "strategy.yaml"

        cfg = load_strategy_config(str(cfg_path))

        # Setup logging (must be first)
        setup_logging(cfg)
        logger = get_logger(__name__)

        logger.info("🌱 EVE_Q SlurperBot v2 - Grace Economy Edition")
        logger.info("=" * 70)

        # Initialize components
        failsafe_cfg = cfg.get("failsafe", {})
        charity_cfg = cfg.get("charity", {})
        execution_cfg = cfg.get("execution", {})

        # Metrics collector
        metrics = MetricsCollector(cfg)

        # Charity distributor
        charity_distributor = CharityDistributor(cfg)

        # Health checker
        health_checker = HealthChecker(cfg)

        # Optional: Initialize Web3 components
        w3 = None
        dex_connector = None
        flash_executor = None

        if WEB3_AVAILABLE and cfg.get("rpc_url"):
            try:
                logger.info("🌐 Initializing Web3 components...")

                # Initialize Web3
                w3 = Web3(Web3.HTTPProvider(cfg["rpc_url"]))

                if not w3.is_connected():
                    logger.warning("⚠️  Web3 not connected - using simulation mode")
                else:
                    logger.info(f"✓ Connected to chain ID: {w3.eth.chain_id}")

                    # Initialize DEX connector
                    dex_connector = DEXConnector(cfg)

                    # Initialize flash loan executor
                    flash_executor = FlashLoanExecutor(cfg, w3)

            except Exception as e:
                logger.warning(f"⚠️  Web3 initialization failed: {e}")
                logger.info("   Continuing in pure simulation mode")

        # Check liveness
        logger.info("🔐 Checking human liveness token...")
        if not check_liveness(failsafe_cfg):
            logger.error("❌ Failsafe triggered: human liveness token expired")
            logger.error("   Please check in to continue operation")
            logger.error("   This is a safety feature, not a punishment")
            sys.exit(1)

        logger.info("✓ Liveness token valid")

        # Initial health check
        logger.info("🏥 Running initial health check...")
        health = await health_checker.check_all(
            w3=w3,
            dex_connector=dex_connector,
            failsafe_state=get_trust_report(),
            metrics=metrics
        )
        health_checker.print_health_summary()

        if health["overall_status"] == "unhealthy":
            logger.error("❌ System unhealthy - aborting")
            sys.exit(1)

        # Main arbitrage loop
        logger.info("🚀 Starting arbitrage loop...")
        logger.info(f"   Simulation mode: {execution_cfg.get('simulation_mode', True)}")
        logger.info(f"   Charity percentage: {charity_cfg.get('percentage', 0.15)*100}%")
        logger.info("=" * 70)

        consecutive_failures = 0
        max_failures = cfg.get("safety", {}).get("max_consecutive_failures", 10)
        cycle_count = 0

        while True:
            cycle_count += 1
            logger.info(f"\n{'=' * 70}")
            logger.info(f"CYCLE #{cycle_count}")
            logger.info(f"{'=' * 70}\n")

            # Run arbitrage cycle
            cycle_result = await run_arbitrage_cycle(
                cfg,
                charity_distributor,
                metrics,
                dex_connector,
                flash_executor
            )

            # Update grace-based economics
            cycle_success = cycle_result.get("success", False)
            progressive_trust_increment(failsafe_cfg, success=cycle_success)

            if cycle_success:
                consecutive_failures = 0
                ttl_change = 4  # Hours gained
                metrics.record_grace_event("expansion", ttl_change)
            else:
                consecutive_failures += 1
                if consecutive_failures >= 5:
                    ttl_change = -2  # Hours lost
                    metrics.record_grace_event("decay", ttl_change)
                else:
                    metrics.record_grace_event("maintenance", 0)

            # Update liveness token
            update_liveness_token(failsafe_cfg)

            # Save logs
            if cycle_result.get("result"):
                logs_dir = root_dir / "logs"
                logs_dir.mkdir(exist_ok=True)
                timestamp = int(time.time())
                log_file = logs_dir / f"trade_{timestamp}.json"

                with open(log_file, "w", encoding="utf-8") as f:
                    json.dump(cycle_result["result"], f, indent=2)

                # Log to IPFS
                charity_distributor.log_to_ipfs(cycle_result["result"])

            # Safety check: Too many consecutive failures
            if consecutive_failures >= max_failures:
                logger.error(f"❌ Too many consecutive failures ({consecutive_failures})")
                logger.error("   Aborting for safety - human intervention required")
                break

            # Periodic health check
            if cycle_count % 10 == 0:
                logger.info("\n🏥 Periodic health check...")
                health = await health_checker.check_all(
                    w3=w3,
                    dex_connector=dex_connector,
                    failsafe_state=get_trust_report(),
                    metrics=metrics
                )

                if health["overall_status"] == "unhealthy":
                    logger.error("❌ System became unhealthy - aborting")
                    break

            # Save metrics periodically
            if cycle_count % 5 == 0:
                metrics.save_metrics()
                metrics.print_summary()

            # Print charity report periodically
            if cycle_count % 20 == 0:
                charity_distributor.print_charity_report()

            # Sleep between cycles
            await asyncio.sleep(cfg.get("dex", {}).get("scan_interval_seconds", 10))

    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Interrupted by user - shutting down gracefully")
        logger.info("   Grace preserved")

    except Exception as e:
        logger.error(f"\n❌ Fatal error: {e}", exc_info=True)

        # On fatal error, maintain grace
        try:
            logger.info("🌱 Grace maintained despite error - no punishment")
            progressive_trust_increment(failsafe_cfg, success=False)
        except:
            pass

    finally:
        # Final metrics save
        if 'metrics' in locals():
            logger.info("\n📊 Saving final metrics...")
            metrics.save_metrics()
            metrics.print_summary()

        # Final charity report
        if 'charity_distributor' in locals():
            charity_distributor.print_charity_report()

        logger.info("\n✅ Shutdown complete")
        logger.info("=" * 70)


if __name__ == "__main__":
    # Run async main
    asyncio.run(main())
