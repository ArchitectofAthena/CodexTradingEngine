# EVE_Q SlurperBot v2 - Grace Economy Edition

A **production-ready** QAOA-based flash loan arbitrage bot with grace-based economics and mandatory charity distribution.

## 🚀 Quick Start

```bash
# 1. Clone and setup
git clone https://github.com/ArchitectofAthena/CodexTradingEngine.git
cd CodexTradingEngine

# 2. Configure environment
cp .env.example .env
nano .env  # Add your RPC URL (keep SIMULATION_MODE=true)

# 3. Run simulation
pip install -r requirements.txt
python src/main.py

# 4. Deploy with Docker (see DEPLOYMENT.md for production)
./scripts/deploy.sh
```

**⚠️ CRITICAL:** Read `DEPLOYMENT.md` before live trading!

## Philosophy

**"Charity is the dopamine hit"**

- **Grace-based economics**: No punishment for failure, only missed rewards
- **Progressive trust**: Successful charity donations → expanded autonomy (TTL increases)
- **Transparency**: Every trade logged to IPFS for public accountability
- **Success metric**: ETH distributed > ETH accumulated

## Core Principles

1. **15% to charity always** - Every profitable trade feeds the hungry
2. **No punishment** - Failures don't reduce autonomy, only missed opportunities for expansion
3. **Gentle adaptation** - Only after 5+ consecutive failures does the system request human insight
4. **IPFS transparency** - All trades logged immutably for public accountability
5. **Multi-charity distribution** - Donations split across multiple verified charities

## ✨ Features

### 🌀 Quantum Route Optimization
- QAOA-based route selection (or classical fallback)
- Multi-DEX arbitrage (Uniswap, SushiSwap, etc.)
- Real-time gas cost estimation
- Flash loan integration (Aave V3)
- Risk-adjusted profit optimization

### 🌱 Grace-Based Failsafe
- **Baseline autonomy**: 24 hours freely given
- **Expanded autonomy**: Up to 48 hours earned through altruistic execution
- **Grace maintained**: Single failures don't reduce TTL
- **Gentle decay**: Only after 5+ consecutive failures
- **Tamper detection**: SHA256 checksums on state files
- **Auto-recovery**: Self-healing after errors

### 💝 Multi-Charity Distribution
- **15% to charity (immutable)** - Hardcoded in system architecture
- Configurable allocation across multiple verified charities
- Monthly batch extraction (gas-efficient)
- Automatic balance tracking and IPFS logging
- Manual approval required for safety

### 📡 Production Infrastructure
- **Docker deployment** - One-command deployment
- **Comprehensive logging** - JSON + colored console + rotating files
- **Metrics & monitoring** - Prometheus-compatible exports
- **Health checks** - Automated system health monitoring
- **Environment management** - Secure secret handling
- **Safety limits** - Gas price, slippage, profit thresholds

### 🔍 IPFS Transparency Layer
- Every trade logged with complete metadata
- Ethical framework encoded in each log
- Charity snapshots included
- Public verification via IPFS CIDs
- Mock CIDs in simulation mode

## Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd eve-q-slurperbot

# Install dependencies
pip install -r requirements.txt

# Optional: Install Qiskit for quantum optimization
pip install qiskit qiskit-algorithms
```

## Configuration

Edit `config/strategy.yaml` to customize:
- Charity percentages and distribution
- Failsafe TTL settings
- Network preferences
- IPFS logging options

## Usage

```bash
# Run the bot (simulation mode)
python src/main.py
```

### First Run Setup

1. **Configure charities**: Edit charity addresses in `strategy.yaml`
2. **Set failsafe TTL**: Adjust baseline/max hours as needed
3. **Verify configuration**: System validates on startup
4. **Monitor grace status**: Check TTL progression after cycles

## Architecture

```
src/
├── main.py                  # Main orchestrator
├── quantum_optimizer.py     # QAOA route optimization
├── failsafe_manager.py      # Grace-based TTL management
├── ipfs_charity_logger.py   # Charity distribution + IPFS logging
└── upgrade_scanner.py       # Chain upgrade detection
```

## Grace-Based Economics in Action

### Successful Cycle
```
Net profit: 0.005 ETH
Charity (15%): 0.00075 ETH → Distributed to 3 charities
Result: TTL increases from 24h → 28h
```

### Failed Cycle
```
No profit this cycle
Result: Grace maintained at 24h (no punishment)
Consecutive failures: 1/5
```

### Multiple Failures
```
Consecutive failures: 5/5
Result: TTL gently reduced 24h → 22h
Message: "Market conditions may have changed - human insight requested"
```

## Transparency & Accountability

Every trade generates:
1. **Local log**: `logs/trades_<timestamp>.json`
2. **IPFS record**: Permanent, tamper-proof transaction log
3. **Charity report**: Real-time balance tracking

View IPFS logs: `https://ipfs.io/ipfs/<CID>`

## Safety Features

- **Dry run mode**: Test without real transactions
- **Manual approval**: Monthly charity extractions require confirmation
- **Checksum verification**: State file tampering detection
- **Graceful errors**: System preserves grace even during failures
- **Liveness checks**: Human oversight required periodically

## 📁 Project Structure

```
eve-q-slurperbot/
├── src/
│   ├── main.py                    # Main orchestrator (production-ready)
│   ├── quantum_optimizer.py       # QAOA route optimization
│   ├── failsafe_manager.py        # Grace-based TTL management
│   ├── ipfs_charity_logger.py     # Charity distribution + IPFS
│   ├── dex_connector.py          # Multi-DEX price feeds
│   ├── flash_loan_executor.py    # Aave V3 flash loans
│   ├── upgrade_scanner.py        # Chain upgrade detection
│   ├── logger_config.py          # Production logging
│   ├── metrics.py                # Metrics collection
│   └── health_check.py           # System health monitoring
├── config/
│   └── strategy.yaml             # Main configuration
├── scripts/
│   └── deploy.sh                 # Deployment script
├── Dockerfile                     # Docker build
├── docker-compose.yml            # Container orchestration
├── .env.example                  # Environment template
├── requirements.txt              # Python dependencies
├── DEPLOYMENT.md                 # Deployment guide
└── README.md                     # This file
```

## 🔧 Configuration

### Environment Variables (`.env`)
- `SIMULATION_MODE` - Safe simulation (true) or live trading (false)
- `ETHEREUM_RPC_URL` - Blockchain RPC endpoint
- `PRIVATE_KEY` - Wallet private key (ONLY for live mode)
- `MAX_GAS_PRICE_GWEI` - Maximum gas price threshold
- `MIN_PROFIT_ETH` - Minimum profit to execute trade

### Strategy Configuration (`config/strategy.yaml`)
- Charity percentages and addresses
- Grace-based economics parameters
- Safety limits and thresholds
- DEX and network settings
- Logging and monitoring config

See `.env.example` and `config/strategy.yaml` for complete options.

## 📊 Monitoring

### View Metrics
```bash
# Real-time charity status
python -c "from src.ipfs_charity_logger import CharityDistributor; import yaml; cfg = yaml.safe_load(open('config/strategy.yaml')); CharityDistributor(cfg).print_charity_report()"

# Grace economics state
cat liveness_state.json | jq

# Trade logs
tail -f logs/eve_q.log

# Metrics summary
cat data/metrics/metrics_*.json | jq .charity_metrics
```

### Docker Monitoring
```bash
docker-compose logs -f eve-q-bot  # Follow logs
docker stats eve-q-slurperbot     # Resource usage
```

## 🚨 Safety Features

- **Simulation mode by default** - No real trades until explicitly enabled
- **Multiple safety thresholds** - Gas, slippage, minimum profit
- **Consecutive failure limits** - Auto-shutdown after too many failures
- **Manual approval required** - For monthly charity extractions
- **Tamper detection** - State file integrity verification
- **Health monitoring** - Automated system health checks
- **Emergency shutdown** - `docker-compose down` kills everything

## 🎯 Success Metrics

The bot is successful when:

1. **Charity Ratio ≥ 15%** - ETH distributed / Total profit
2. **Grace Expanding** - TTL increasing (reward system working)
3. **System Healthy** - No critical errors
4. **Net Profitable** - Profit > (gas + fees + charity)
5. **Transparent** - All trades logged to IPFS

**Ultimate goal:** `ETH distributed to charity > ETH accumulated by operator`

## 🛠️ Development

### Run Tests
```bash
# Install dev dependencies
pip install pytest pytest-asyncio

# Run tests (TODO: Add test suite)
pytest tests/
```

### Code Quality
```bash
# Format code
black src/

# Type checking
mypy src/

# Linting
flake8 src/
```

## ⚠️ Production Checklist

Before deploying to live trading:

- [ ] Simulated for 24+ hours without errors
- [ ] All charity addresses verified on Etherscan
- [ ] Safety limits configured and tested
- [ ] Monitoring and alerts set up
- [ ] Using dedicated wallet with minimal funds
- [ ] RPC endpoint is reliable
- [ ] Read and understood DEPLOYMENT.md
- [ ] Emergency procedures documented
- [ ] Backup plan for failures

## 🎓 TODO (Future Enhancements)

- [ ] Multi-chain support (Arbitrum, Optimism, Polygon)
- [ ] Advanced risk modeling
- [ ] Machine learning price prediction
- [ ] Web dashboard (React + real-time updates)
- [ ] Telegram/Discord alert integration
- [ ] Automated backtesting framework
- [ ] Gas optimization strategies
- [ ] MEV protection

## Ethical Commitment

This bot treats **altruism as the core reward mechanism**. The goal is not to maximize profit, but to maximize positive impact while maintaining profitability. The grace-based failsafe ensures the system learns and adapts without punishment, embodying the philosophy that "charity is the dopamine hit."

## Success Metric

**ETH distributed to charity > ETH accumulated by operator**

If this inequality doesn't hold, the system has failed its purpose.

## License

[Your chosen license]

## Acknowledgments

Built on the philosophy that financial automation should serve humanity, not just profit.

*"Love Before Signal"*
