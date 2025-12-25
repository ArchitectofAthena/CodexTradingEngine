# EVE_Q SlurperBot v2 - Deployment Guide

## ⚠️ CRITICAL SAFETY WARNINGS ⚠️

1. **THIS BOT HANDLES REAL FUNDS** - Test thoroughly in simulation mode first
2. **NEVER commit .env file** - Contains private keys and API secrets
3. **START SMALL** - Use minimal amounts until proven stable
4. **MONITOR CLOSELY** - Watch logs and metrics constantly
5. **HAVE KILL SWITCH READY** - `docker-compose down` stops everything

## Prerequisites

### Required
- Docker and Docker Compose
- Python 3.11+ (for local development)
- Blockchain RPC endpoint (Alchemy, Infura, or QuickNode)
- IPFS pinning service account (optional, for transparency logs)

### Recommended
- Dedicated server/VPS (not your laptop)
- Monitoring dashboard (Grafana + Prometheus)
- Alert system (Discord/Telegram webhook)
- Backup power/internet

## Step 1: Environment Setup

### 1.1 Copy Environment Template
```bash
cd /home/user/eve-q-slurperbot
cp .env.example .env
```

### 1.2 Edit .env File
```bash
nano .env  # or use your preferred editor
```

**Minimum Required Settings:**
```bash
# CRITICAL: Leave as true until thoroughly tested
SIMULATION_MODE=true

# Get free RPC from https://www.alchemy.com/
ETHEREUM_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY_HERE

# ONLY for live trading (leave empty for simulation)
PRIVATE_KEY=

# Safety limits
MAX_GAS_PRICE_GWEI=100
MIN_PROFIT_ETH=0.001
```

### 1.3 Verify Charity Addresses
Edit `config/strategy.yaml` and **VERIFY** charity wallet addresses:
```yaml
charity:
  distribution:
    - name: "GiveDirectly"
      address: "0x750EF1D7a0b4Ab1c97B7A623D7917CcEb5ea779C"  # VERIFY THIS!
```

Use Etherscan to confirm these are legitimate charity addresses.

## Step 2: Simulation Testing

### 2.1 Install Dependencies (Local)
```bash
pip install -r requirements.txt
```

### 2.2 Run Simulation
```bash
# Ensure SIMULATION_MODE=true in .env
python src/main.py
```

**Expected Output:**
```
======================================================================
EVE_Q SlurperBot v2 - Grace Economy Edition
======================================================================
✓ Configuration validation passed
  Charity: 15.0% to 3 organizations
  Simulation mode: True
  Ethos: Grace-based economics ACTIVE
🌐 Initializing Web3 components...
⚠️  Web3 not connected - using simulation mode
🔐 Checking human liveness token...
✓ Liveness token valid
🚀 Starting arbitrage loop...
======================================================================

CYCLE #1
======================================================================
🔍 Scanning for upgrades...
💹 Fetching arbitrage routes...
   Using simulated data (no DEX connector)
   Found 3 candidate routes
🌀 Optimizing routes using QAOA...
✓ Best route: ETH->DAI->ETH (SushiSwap→Uniswap)
   Expected profit: 0.012000 ETH
   Gas cost: 0.004000 ETH
💸 Executing arbitrage...
🎭 SIMULATION MODE - No real blockchain interaction
✓ Simulated profit: 0.007100 ETH (charity: 0.001065 ETH)

💝 DISTRIBUTING 0.001065 ETH TO CHARITIES:
   ↳ GiveDirectly: 0.000426 ETH
     Balance: 0.000426 ETH
   ↳ The Hunger Project: 0.000373 ETH
     Balance: 0.000373 ETH
   ↳ Water.org: 0.000266 ETH
     Balance: 0.000266 ETH
```

### 2.3 Verify Outputs
Check that these directories were created:
```bash
ls -la logs/              # Trade logs
ls -la data/metrics/      # Metrics
ls -la data/ipfs_logs/    # IPFS logs (mock CIDs)
```

## Step 3: Docker Deployment (Simulation)

### 3.1 Build Image
```bash
./scripts/deploy.sh
```

This will:
- Check .env exists
- Verify SIMULATION_MODE is set
- Build Docker image
- Start container

### 3.2 Monitor Logs
```bash
docker-compose logs -f eve-q-bot
```

### 3.3 Check Health
```bash
# View metrics
docker exec eve-q-slurperbot cat data/metrics/metrics_*.json | jq

# View charity balances
docker exec eve-q-slurperbot python -c "
from ipfs_charity_logger import CharityDistributor
import yaml
with open('config/strategy.yaml') as f:
    cfg = yaml.safe_load(f)
cd = CharityDistributor(cfg)
cd.print_charity_report()
"
```

## Step 4: Live Trading (DANGER ZONE)

### ⚠️ FINAL SAFETY CHECKS ⚠️

Before enabling live trading, verify:

- [ ] Simulated for at least 24 hours without errors
- [ ] Charity distributions working correctly
- [ ] Grace-based TTL system functioning
- [ ] All safety limits configured
- [ ] Monitoring alerts set up
- [ ] Emergency shutdown procedure tested
- [ ] Using dedicated wallet (NOT your main wallet)
- [ ] Wallet has minimal funds (start with <0.1 ETH)
- [ ] RPC endpoint is reliable and fast
- [ ] You understand you could lose all funds

### 4.1 Configure for Live Trading

Edit `.env`:
```bash
SIMULATION_MODE=false

# Use dedicated wallet with minimal funds
PRIVATE_KEY=0x...your...private...key...here
```

**CRITICAL:** This private key should be:
- From a NEW wallet (never used before)
- With minimal funds (< 0.1 ETH to start)
- NOT your main wallet
- Backed up securely

### 4.2 Deploy to Production
```bash
# Stop simulation
docker-compose down

# Verify configuration
cat .env | grep SIMULATION_MODE  # Should be 'false'

# Deploy (you'll be asked to confirm)
./scripts/deploy.sh

# Monitor CLOSELY
docker-compose logs -f eve-q-bot
```

### 4.3 Monitor Live Trading

Watch for:
- Successful blockchain connections
- Real DEX price quotes
- Flash loan executions
- Actual charity distributions
- Gas costs vs. profits
- Error rates

**Kill switch:**
```bash
# Emergency stop
docker-compose down
```

## Step 5: Production Monitoring

### 5.1 Metrics Dashboard
```bash
# View real-time metrics
watch -n 5 'docker exec eve-q-slurperbot cat data/metrics/metrics_*.json | jq .charity_metrics'
```

### 5.2 Charity Report
```bash
# Daily charity report
docker exec eve-q-slurperbot python -c "
from src.ipfs_charity_logger import CharityDistributor
import yaml
with open('config/strategy.yaml') as f:
    cfg = yaml.safe_load(f)
cd = CharityDistributor(cfg)
cd.print_charity_report()
"
```

### 5.3 Grace Status
```bash
# Check grace-based economics state
docker exec eve-q-slurperbot cat liveness_state.json | jq
```

## Troubleshooting

### Bot Won't Start
```bash
# Check logs
docker-compose logs eve-q-bot

# Common issues:
# 1. Missing .env file
# 2. Invalid RPC URL
# 3. Missing dependencies
```

### No Trades Executing
```bash
# Check gas prices
# Check DEX liquidity
# Verify min_profit_eth threshold
# Check consecutive failures count
```

### Liveness Token Expired
```bash
# Update token manually
docker exec eve-q-slurperbot python -c "
from src.failsafe_manager import update_liveness_token
update_liveness_token({'ttl_hours': 24})
print('Token updated')
"
```

### Grace TTL Depleted
```bash
# Check grace report
docker exec eve-q-slurperbot python -c "
from src.failsafe_manager import get_trust_report
import json
print(json.dumps(get_trust_report(), indent=2))
"
```

## Maintenance

### Daily Tasks
- [ ] Check logs for errors
- [ ] Verify charity accumulation
- [ ] Monitor gas prices
- [ ] Review trade success rate

### Weekly Tasks
- [ ] Backup logs and metrics
- [ ] Review charity report
- [ ] Check for upgrades
- [ ] Analyze profitability

### Monthly Tasks
- [ ] Execute charity extractions
- [ ] Verify IPFS logs
- [ ] Review grace economics performance
- [ ] Update dependencies

## Emergency Procedures

### Immediate Shutdown
```bash
docker-compose down
```

### Recover from Error
```bash
# Reset state (CAREFUL - clears grace history)
docker-compose down
mv liveness_state.json liveness_state.json.backup
mv data/charity_extraction.json data/charity_extraction.json.backup
docker-compose up -d
```

### Manual Charity Extraction
```bash
# View pending balances
docker exec eve-q-slurperbot python -c "
from src.ipfs_charity_logger import CharityDistributor
import yaml
with open('config/strategy.yaml') as f:
    cfg = yaml.safe_load(f)
cd = CharityDistributor(cfg)
print(cd.monthly_balances)
"

# TODO: Implement manual extraction script
```

## Success Metrics

The bot is successful if:

1. **Charity Ratio ≥ 15%** - ETH distributed to charity / Total ETH profit
2. **Grace Expanding** - TTL increasing over time (rewards working)
3. **No Critical Errors** - System remains healthy
4. **Profitable** - Net profit > gas costs + charity
5. **Transparent** - All trades logged to IPFS

## Philosophy Reminder

This bot treats **charity as the core reward mechanism**. The goal is:

**ETH distributed to charity > ETH accumulated by operator**

If this inequality doesn't hold, the system has failed its purpose.

Every trade should feed the hungry. 🌱
