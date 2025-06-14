#!/bin/bash

echo "=== Lavalink Docker Troubleshooting ==="
echo

# Check if Docker is running
echo "1. Checking Docker status..."
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running or not accessible"
    exit 1
else
    echo "✅ Docker is running"
fi
echo

# Check environment file
echo "2. Checking .env file..."
if [ -f ".env" ]; then
    echo "✅ .env file exists"
    if grep -q "LAVALINK_PASSWORD" .env; then
        echo "✅ LAVALINK_PASSWORD found in .env"
    else
        echo "❌ LAVALINK_PASSWORD missing from .env"
    fi
else
    echo "❌ .env file not found"
fi
echo

# Check application.yml
echo "3. Checking Lavalink configuration..."
if [ -f "lavalink/application.yml" ]; then
    echo "✅ application.yml exists"
    if grep -q "youshallnotpass" lavalink/application.yml; then
        echo "✅ Password matches in application.yml"
    else
        echo "⚠️  Password might not match between .env and application.yml"
    fi
else
    echo "❌ lavalink/application.yml not found"
fi
echo

# Create logs directory if it doesn't exist
echo "4. Checking logs directory..."
if [ ! -d "logs" ]; then
    echo "📁 Creating logs directory..."
    mkdir -p logs
fi
echo "✅ Logs directory ready"
echo

# Check if containers are running
echo "5. Checking container status..."
if docker ps -a --format "table {{.Names}}\t{{.Status}}" | grep -E "(lavalink|piumbot)"; then
    echo "Container status shown above"
else
    echo "No containers found"
fi
echo

# Check Lavalink logs if container exists
echo "6. Recent Lavalink logs..."
if docker ps -a --format "{{.Names}}" | grep -q "lavalink"; then
    echo "--- Last 20 lines of Lavalink logs ---"
    docker logs --tail 20 lavalink 2>&1 || echo "Could not retrieve logs"
else
    echo "Lavalink container not found"
fi
echo

# Test Lavalink HTTP endpoint
echo "7. Testing Lavalink HTTP endpoint..."
if docker ps --format "{{.Names}}" | grep -q "lavalink"; then
    echo "Testing from inside container..."
    docker exec lavalink wget --no-verbose --tries=1 --spider http://localhost:2333/version 2>&1 && echo "✅ Lavalink HTTP endpoint is working" || echo "❌ Lavalink HTTP endpoint is not responding"
    
    echo "Testing from host..."
    curl -s http://localhost:2333/version > /dev/null 2>&1 && echo "✅ Lavalink accessible from host" || echo "❌ Lavalink not accessible from host"
else
    echo "Lavalink container not running"
fi
echo

# Recommendations
echo "=== Recommendations ==="
echo "1. If Lavalink is failing to start:"
echo "   - Check that port 2333 is not in use: netstat -tulpn | grep 2333"
echo "   - Try: docker-compose down && docker-compose up --build"
echo
echo "2. If health check is failing:"
echo "   - Check Lavalink logs: docker logs lavalink"
echo "   - Try starting without health check temporarily"
echo
echo "3. If bot can't connect:"
echo "   - Verify passwords match in .env and application.yml"
echo "   - Check network connectivity between containers"
echo
echo "4. For more verbose output:"
echo "   - Run: docker-compose up --no-daemon to see real-time logs"
