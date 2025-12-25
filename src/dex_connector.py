"""
DEX Connector for EVE_Q SlurperBot v2.

Connects to multiple DEXes (Uniswap, SushiSwap, etc.) to fetch real-time
price data and liquidity information for arbitrage opportunities.
"""

from typing import Dict, List, Any, Optional, Tuple
from decimal import Decimal
import asyncio
import logging

try:
    from web3 import Web3
    from web3.contract import Contract
    WEB3_AVAILABLE = True
except ImportError:
    WEB3_AVAILABLE = False
    Web3 = None
    Contract = None

logger = logging.getLogger(__name__)


# Uniswap V2 Router ABI (simplified - key functions only)
UNISWAP_V2_ROUTER_ABI = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"}
        ],
        "name": "getAmountsOut",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# Known DEX router addresses (Ethereum mainnet)
DEX_ROUTERS = {
    "uniswap_v2": "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
    "sushiswap": "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F",
    "uniswap_v3": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
}

# Common token addresses (Ethereum mainnet)
TOKEN_ADDRESSES = {
    "ETH": "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",  # Special address for native ETH
    "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
    "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
    "WBTC": "0x2260FAC5E5542a773Aa44fBCfeDF7C193bc2C599",
}


class DEXConnector:
    """Connects to multiple DEXes for price quotes and liquidity data."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize DEX connector.

        Parameters
        ----------
        config : dict
            Configuration with RPC endpoints and DEX settings
        """
        if not WEB3_AVAILABLE:
            raise RuntimeError("web3.py not installed. Install with: pip install web3")

        self.config = config
        self.rpc_url = config.get("rpc_url")
        if not self.rpc_url:
            raise ValueError("RPC URL not configured")

        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))

        # Verify connection
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to RPC: {self.rpc_url}")

        logger.info(f"Connected to blockchain - Chain ID: {self.w3.eth.chain_id}")

        # Initialize DEX router contracts
        self.routers: Dict[str, Contract] = {}
        self._init_routers()

        # Token addresses for this chain
        self.tokens = TOKEN_ADDRESSES.copy()
        custom_tokens = config.get("custom_tokens", {})
        self.tokens.update(custom_tokens)

    def _init_routers(self):
        """Initialize DEX router contracts."""
        for dex_name, router_address in DEX_ROUTERS.items():
            try:
                # Use checksummed address
                address = Web3.to_checksum_address(router_address)
                contract = self.w3.eth.contract(
                    address=address,
                    abi=UNISWAP_V2_ROUTER_ABI
                )
                self.routers[dex_name] = contract
                logger.info(f"Initialized {dex_name} router at {address}")
            except Exception as e:
                logger.error(f"Failed to initialize {dex_name}: {e}")

    async def get_price_quote(
        self,
        dex: str,
        token_in: str,
        token_out: str,
        amount_in: Decimal
    ) -> Optional[Decimal]:
        """Get price quote from a specific DEX.

        Parameters
        ----------
        dex : str
            DEX name (e.g., 'uniswap_v2')
        token_in : str
            Input token symbol
        token_out : str
            Output token symbol
        amount_in : Decimal
            Input amount in token units

        Returns
        -------
        Decimal or None
            Output amount, or None if quote fails
        """
        try:
            router = self.routers.get(dex)
            if not router:
                logger.warning(f"DEX {dex} not initialized")
                return None

            # Get token addresses
            addr_in = self.tokens.get(token_in)
            addr_out = self.tokens.get(token_out)

            if not addr_in or not addr_out:
                logger.error(f"Token address not found: {token_in} or {token_out}")
                return None

            # Convert to Wei (assuming 18 decimals - adjust for actual token)
            amount_wei = int(amount_in * Decimal(10**18))

            # Build path
            path = [
                Web3.to_checksum_address(addr_in),
                Web3.to_checksum_address(addr_out)
            ]

            # Get amounts out
            amounts = router.functions.getAmountsOut(amount_wei, path).call()

            # Convert back from Wei
            amount_out = Decimal(amounts[-1]) / Decimal(10**18)

            return amount_out

        except Exception as e:
            logger.error(f"Failed to get quote from {dex}: {e}")
            return None

    async def find_arbitrage_routes(
        self,
        base_amount: Decimal = Decimal("1.0")
    ) -> List[Dict[str, Any]]:
        """Scan all DEXes for arbitrage opportunities.

        Parameters
        ----------
        base_amount : Decimal
            Base amount to test (in ETH)

        Returns
        -------
        list
            List of potential arbitrage routes with profit estimates
        """
        routes = []

        # Common arbitrage patterns
        patterns = [
            ("WETH", "USDC", "WETH"),
            ("WETH", "DAI", "WETH"),
            ("WETH", "USDT", "WETH"),
            ("WETH", "WBTC", "WETH"),
        ]

        for pattern in patterns:
            for dex1 in self.routers.keys():
                for dex2 in self.routers.keys():
                    if dex1 == dex2:
                        continue

                    try:
                        # First swap
                        quote1 = await self.get_price_quote(
                            dex1, pattern[0], pattern[1], base_amount
                        )
                        if not quote1:
                            continue

                        # Second swap
                        quote2 = await self.get_price_quote(
                            dex2, pattern[1], pattern[2], quote1
                        )
                        if not quote2:
                            continue

                        # Calculate profit
                        profit = quote2 - base_amount
                        profit_pct = (profit / base_amount) * 100

                        if profit > 0:
                            route_name = f"{pattern[0]}->{pattern[1]}->{pattern[2]} ({dex1}→{dex2})"

                            routes.append({
                                "name": route_name,
                                "pattern": pattern,
                                "dex_buy": dex1,
                                "dex_sell": dex2,
                                "input_amount": float(base_amount),
                                "output_amount": float(quote2),
                                "gross_profit": float(profit),
                                "profit_percentage": float(profit_pct),
                                "quote1": float(quote1),
                                "quote2": float(quote2)
                            })

                            logger.info(
                                f"Found opportunity: {route_name} - "
                                f"Profit: {profit:.6f} ({profit_pct:.2f}%)"
                            )

                    except Exception as e:
                        logger.error(f"Error checking route {pattern}: {e}")
                        continue

        # Sort by profit
        routes.sort(key=lambda x: x["gross_profit"], reverse=True)

        return routes

    async def estimate_gas_cost(
        self,
        route: Dict[str, Any]
    ) -> Decimal:
        """Estimate gas cost for executing a route.

        Parameters
        ----------
        route : dict
            Route information

        Returns
        -------
        Decimal
            Estimated gas cost in ETH
        """
        try:
            # Get current gas price
            gas_price = self.w3.eth.gas_price

            # Estimate gas units (rough estimate for flash loan + 2 swaps)
            # - Flash loan: ~150k gas
            # - Swap 1: ~150k gas
            # - Swap 2: ~150k gas
            # - Overhead: ~50k gas
            estimated_gas_units = 500000

            # Calculate cost in ETH
            gas_cost_wei = gas_price * estimated_gas_units
            gas_cost_eth = Decimal(gas_cost_wei) / Decimal(10**18)

            logger.info(
                f"Gas estimate: {estimated_gas_units} units @ "
                f"{gas_price / 10**9:.2f} gwei = {gas_cost_eth:.6f} ETH"
            )

            return gas_cost_eth

        except Exception as e:
            logger.error(f"Failed to estimate gas: {e}")
            # Return conservative estimate
            return Decimal("0.01")

    def get_connection_status(self) -> Dict[str, Any]:
        """Get connection status and health metrics.

        Returns
        -------
        dict
            Connection status information
        """
        try:
            latest_block = self.w3.eth.block_number
            gas_price = self.w3.eth.gas_price / 10**9  # Convert to gwei

            return {
                "connected": True,
                "chain_id": self.w3.eth.chain_id,
                "latest_block": latest_block,
                "gas_price_gwei": float(gas_price),
                "routers_initialized": len(self.routers),
                "rpc_url": self.rpc_url
            }
        except Exception as e:
            logger.error(f"Connection status check failed: {e}")
            return {
                "connected": False,
                "error": str(e)
            }
