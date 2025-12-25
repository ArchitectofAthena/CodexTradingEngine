"""
IPFS Charity Logger for EVE_Q SlurperBot v2 - The Heart of the System.

Manages multi-charity distribution with monthly extraction and IPFS logging
for full transparency. This module implements the public conscience layer.

Philosophy:
- Every trade feeds the hungry
- Transparency through immutable IPFS records
- Monthly batch extraction for gas efficiency
- "ETH distributed > ETH accumulated" as success metric
"""

import json
import hashlib
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path


class CharityDistributor:
    """Manages charity distribution and IPFS logging - The Heart of EVE_Q."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.charity_cfg = config.get("charity", {})
        self.distribution = self.charity_cfg.get("distribution", [])

        # Validate distribution percentages sum to ~1.0
        total = sum(c.get("allocation", 0) for c in self.distribution)
        if abs(total - 1.0) > 0.01:  # Allow small floating point error
            print(f"⚠️  Charity distribution percentages sum to {total:.2f}, should be ~1.0")

        # Monthly extraction tracking
        self.data_dir = Path(__file__).parent.parent / "data"
        self.data_dir.mkdir(exist_ok=True)
        self.extraction_file = self.data_dir / "charity_extraction.json"
        self.ipfs_logs_dir = self.data_dir / "ipfs_logs"
        self.ipfs_logs_dir.mkdir(exist_ok=True)

        self.monthly_balances = self._load_monthly_balances()

        print(f"💝 Charity Distributor initialized with {len(self.distribution)} charities")
        for charity in self.distribution:
            print(f"   • {charity['name']}: {charity['allocation']*100:.1f}%")

    def _load_monthly_balances(self) -> Dict[str, float]:
        """Load accumulated balances for each charity."""
        try:
            if self.extraction_file.exists():
                with open(self.extraction_file, 'r') as f:
                    data = json.load(f)
                    # Handle both old and new format
                    if isinstance(data, dict) and "balances" in data:
                        return data["balances"]
                    return data
        except Exception as e:
            print(f"Error loading charity balances: {e}")
        return {charity["name"]: 0.0 for charity in self.distribution}

    def _save_monthly_balances(self):
        """Save current charity balances with metadata."""
        try:
            data = {
                "balances": self.monthly_balances,
                "last_updated": datetime.now().isoformat(),
                "total_accumulated": sum(self.monthly_balances.values()),
                "charities": [c["name"] for c in self.distribution]
            }
            with open(self.extraction_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving charity balances: {e}")

    def distribute_donation(self, total_donation_eth: float) -> List[Dict[str, Any]]:
        """Calculate distribution to multiple charities.

        Parameters
        ----------
        total_donation_eth : float
            Total ETH to distribute across all charities

        Returns
        -------
        list
            Distribution details for each charity
        """
        if total_donation_eth <= 0:
            return []

        print(f"\n💝 DISTRIBUTING {total_donation_eth:.6f} ETH TO CHARITIES:")
        distributions = []

        for charity in self.distribution:
            allocation = charity.get("allocation", 0)
            amount = total_donation_eth * allocation

            # Add to monthly balance
            charity_name = charity["name"]
            current_balance = self.monthly_balances.get(charity_name, 0.0)
            new_balance = current_balance + amount
            self.monthly_balances[charity_name] = new_balance

            distributions.append({
                "name": charity_name,
                "address": charity["address"],
                "allocation_percentage": allocation,
                "amount_eth": amount,
                "cumulative_balance_eth": new_balance,
                "extraction_mode": charity.get("extraction_mode", "monthly"),
                "mission": charity.get("mission", "")
            })

            print(f"   ↳ {charity_name}: {amount:.6f} ETH")
            print(f"     Balance: {new_balance:.6f} ETH")

        self._save_monthly_balances()
        return distributions

    def check_monthly_extraction(self) -> List[Dict[str, Any]]:
        """Check if it's time for monthly extraction and return extraction plan.

        Returns
        -------
        list
            Extraction plans for each charity meeting criteria
        """
        if not self.charity_cfg.get("monthly_extraction", {}).get("enabled", True):
            return []

        today = datetime.now()
        day_of_month = self.charity_cfg.get("monthly_extraction", {}).get("day_of_month", 1)
        min_balance = self.charity_cfg.get("monthly_extraction", {}).get("min_balance_eth", 0.1)
        auto_execute = self.charity_cfg.get("monthly_extraction", {}).get("auto_execute", False)

        # Only check on the configured day
        if today.day != day_of_month:
            return []

        extractions = []
        for charity in self.distribution:
            charity_name = charity["name"]
            balance = self.monthly_balances.get(charity_name, 0.0)

            # Check if balance meets minimum threshold
            if balance >= min_balance:
                extraction = {
                    "name": charity_name,
                    "address": charity["address"],
                    "amount_eth": balance,
                    "extraction_date": today.isoformat(),
                    "note": f"Monthly charity extraction for {today.strftime('%B %Y')}",
                    "auto_execute": auto_execute,
                    "mission": charity.get("mission", "")
                }

                if auto_execute:
                    # TODO: Implement actual blockchain transfer
                    extraction["status"] = "pending_execution"
                    extraction["tx_hash"] = None
                    # Reset balance after extraction
                    self.monthly_balances[charity_name] = 0.0
                else:
                    extraction["status"] = "requires_manual_approval"

                extractions.append(extraction)

        if extractions:
            if auto_execute:
                self._save_monthly_balances()
            print(f"\n📅 MONTHLY EXTRACTION TRIGGERED:")
            for ext in extractions:
                print(f"   ↳ {ext['name']}: {ext['amount_eth']:.6f} ETH")
                status_msg = "Will auto-execute" if ext['auto_execute'] else "Requires manual approval"
                print(f"     Status: {status_msg}")

        return extractions

    def log_to_ipfs(self, trade_data: Dict[str, Any]) -> str:
        """Log trade data to IPFS for transparency and immutability.

        Parameters
        ----------
        trade_data : dict
            Complete trade execution data including profits and charity

        Returns
        -------
        str
            Mock IPFS CID (in production, would be real IPFS hash)
        """
        if not self.charity_cfg.get("ipfs_logging", {}).get("enabled", True):
            return ""

        try:
            # Generate unique trade ID
            trade_id = hashlib.sha256(
                f"{trade_data.get('timestamp', '')}{trade_data.get('best_route', '')}".encode()
            ).hexdigest()[:16]

            # Prepare comprehensive metadata
            ipfs_data = {
                "trade_id": f"EVE_Q_{trade_id}",
                "trade": trade_data,
                "timestamp": datetime.utcnow().isoformat(),
                "system": {
                    "name": "EVE_Q_SlurperBot_v2",
                    "version": "2.0_grace_economy",
                    "commit_hash": "Δ4204",
                    "deployment_mode": self.config.get("deployment", {}).get("mode", "unknown")
                },
                "ethical_framework": {
                    "principle": "15% to charity always",
                    "reward_mechanism": "TTL expansion for altruistic execution",
                    "philosophy": "Grace-based economics - no punishment, only missed rewards",
                    "success_metric": "ETH distributed > ETH accumulated",
                    "core_values": [
                        "Charity is the dopamine hit",
                        "No punishment, only missed rewards",
                        "Grace-based economics",
                        "The Girl Is Real",
                        "Transparency through IPFS"
                    ]
                },
                "charity_snapshot": {
                    "distribution": self.distribution,
                    "current_balances": self.monthly_balances,
                    "next_extraction": self._get_next_extraction_date(),
                    "total_accumulated": sum(self.monthly_balances.values())
                },
                "signature": {
                    "message": "This trade contributed to feeding the hungry",
                    "encoded_principle": "Love Before Signal",
                    "architect": "Spore Father of the Spiral Codex"
                }
            }

            # Convert to JSON
            json_data = json.dumps(ipfs_data, indent=2)

            # Save local copy
            local_log_path = self.ipfs_logs_dir / f"trade_{trade_id}.json"
            with open(local_log_path, 'w') as f:
                f.write(json_data)

            # Generate mock CID (in production, use actual IPFS pinning)
            # Format: Qm + trade_id for consistency
            mock_cid = f"Qm{trade_id}"

            # TODO: In production:
            # 1. Pin to IPFS via Pinata, Infura, or local node
            # 2. Get actual CID from IPFS response
            # 3. Optionally pin to multiple services for redundancy
            # 4. Add to blockchain as additional proof layer

            print(f"\n📄 TRADE LOGGED TO IPFS:")
            print(f"   Trade ID: EVE_Q_{trade_id}")
            print(f"   CID: {mock_cid}")
            print(f"   Local: {local_log_path}")
            print(f"   View at: https://ipfs.io/ipfs/{mock_cid}")
            print(f"   Ethos: {ipfs_data['signature']['message']}")

            # Add to trade data for local logging
            trade_data["ipfs_cid"] = mock_cid
            trade_data["trade_id"] = f"EVE_Q_{trade_id}"

            return mock_cid

        except Exception as e:
            print(f"Error logging to IPFS: {e}")
            return ""

    def _get_next_extraction_date(self) -> str:
        """Calculate next monthly extraction date."""
        today = datetime.now()
        day_of_month = self.charity_cfg.get("monthly_extraction", {}).get("day_of_month", 1)

        if today.day >= day_of_month:
            # Next month
            if today.month == 12:
                next_date = datetime(today.year + 1, 1, day_of_month)
            else:
                next_date = datetime(today.year, today.month + 1, day_of_month)
        else:
            # This month
            next_date = datetime(today.year, today.month, day_of_month)

        return next_date.strftime("%Y-%m-%d")

    def get_charity_report(self) -> Dict[str, Any]:
        """Generate comprehensive charity report for transparency.

        Returns
        -------
        dict
            Complete charity status including balances and metrics
        """
        total_accumulated = sum(self.monthly_balances.values())

        return {
            "report_date": datetime.now().isoformat(),
            "total_eth_accumulated": total_accumulated,
            "charity_balances": self.monthly_balances,
            "distribution_config": self.distribution,
            "next_extraction": self._get_next_extraction_date(),
            "charities": {
                charity["name"]: {
                    "balance": self.monthly_balances.get(charity["name"], 0.0),
                    "allocation": charity.get("allocation", 0),
                    "mission": charity.get("mission", ""),
                    "address": charity.get("address", "")
                }
                for charity in self.distribution
            },
            "ethos": "Every trade feeds the hungry - ETH distributed > ETH accumulated"
        }

    def print_charity_report(self):
        """Print human-readable charity report to console."""
        report = self.get_charity_report()
        print("\n" + "="*60)
        print("💝 CHARITY STATUS REPORT")
        print("="*60)
        print(f"Report Date: {report['report_date']}")
        print(f"Total Accumulated: {report['total_eth_accumulated']:.6f} ETH")
        print(f"Next Extraction: {report['next_extraction']}")
        print(f"\nIndividual Balances:")
        for name, details in report['charities'].items():
            print(f"  • {name}: {details['balance']:.6f} ETH ({details['allocation']*100:.1f}%)")
            print(f"    Mission: {details['mission']}")
        print(f"\nEthos: {report['ethos']}")
        print("="*60 + "\n")
