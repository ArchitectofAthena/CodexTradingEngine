#!/bin/bash
# EVE_Q SlurperBot v2 - Deployment Script

set -e  # Exit on error

echo "========================================"
echo "EVE_Q SlurperBot v2 - Deployment"
echo "========================================"
echo

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found!"
    echo "   Please copy .env.example to .env and configure it:"
    echo "   cp .env.example .env"
    echo "   Then edit .env with your API keys"
    exit 1
fi

# Source environment variables
source .env

# Safety check - ensure simulation mode is set
if [ "$SIMULATION_MODE" != "true" ]; then
    echo "⚠️  WARNING: SIMULATION_MODE is set to false!"
    echo "   This will execute REAL trades with REAL funds!"
    echo
    read -p "   Are you ABSOLUTELY sure? (type 'YES' to continue): " confirm
    if [ "$confirm" != "YES" ]; then
        echo "   Deployment cancelled."
        exit 1
    fi
fi

# Check if private key is set (for non-simulation mode)
if [ "$SIMULATION_MODE" != "true" ] && [ -z "$PRIVATE_KEY" ]; then
    echo "❌ Error: PRIVATE_KEY not set in .env!"
    echo "   Required for non-simulation mode"
    exit 1
fi

# Build Docker image
echo "🐳 Building Docker image..."
docker-compose build

echo
echo "✅ Build complete!"
echo

# Show configuration
echo "Current configuration:"
echo "  Simulation Mode: $SIMULATION_MODE"
echo "  Charity Percentage: ${CHARITY_PERCENTAGE}%"
echo "  Log Level: $LOG_LEVEL"
echo

# Start services
echo "🚀 Starting EVE_Q SlurperBot..."
docker-compose up -d

echo
echo "✅ Deployment complete!"
echo
echo "To view logs:"
echo "  docker-compose logs -f eve-q-bot"
echo
echo "To stop:"
echo "  docker-compose down"
echo
echo "To view metrics:"
echo "  cat data/metrics/metrics_*.json | jq"
echo
