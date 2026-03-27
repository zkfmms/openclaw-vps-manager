#!/bin/bash
# OpenClaw VPS Setup Script
# This script sets up OpenClaw on a new VPS

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    print_error "This script should not be run as root"
    exit 1
fi

print_info "Starting OpenClaw VPS setup..."

# 1. Check and install Node.js
if ! command -v node &> /dev/null; then
    print_info "Node.js not found. Installing Node.js 20.x..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
    print_info "Node.js installed successfully"
else
    NODE_VERSION=$(node -v)
    print_info "Node.js is already installed: $NODE_VERSION"
fi

# 2. Install OpenClaw
if ! command -v openclaw &> /dev/null; then
    print_info "Installing OpenClaw..."
    sudo npm install -g openclaw || sudo npm install -g openclaw --unsafe-perm
    print_info "OpenClaw installed successfully"
else
    OPENCLAW_VERSION=$(openclaw --version)
    print_info "OpenClaw is already installed: $OPENCLAW_VERSION"
fi

# 3. Create OpenClaw directory structure
print_info "Creating OpenClaw directory structure..."
mkdir -p ~/.openclaw/{workspace,skills,credentials}
chmod 700 ~/.openclaw

# 4. Create systemd service
print_info "Creating systemd service..."
cat > /tmp/openclaw.service << 'EOF'
[Unit]
Description=OpenClaw Gateway
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=/home/$USER/.openclaw
Environment="NODE_ENV=production"
ExecStart=/usr/local/bin/openclaw gateway start --config ~/.openclaw/openclaw.json
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo mv /tmp/openclaw.service /etc/systemd/system/openclaw.service
sudo systemctl daemon-reload
sudo systemctl enable openclaw.service

# 5. Create placeholder configuration
print_info "Creating placeholder configuration..."
cat > ~/.openclaw/openclaw.json << 'EOF'
{
  "agent": {
    "model": "anthropic/claude-sonnet-4-6"
  },
  "gateway": {
    "port": 18789,
    "bind": "loopback",
    "auth": {
      "mode": "token",
      "token": {
        "source": "env",
        "provider": "default",
        "id": "OPENCLAW_GATEWAY_TOKEN"
      }
    }
  },
  "skills": {
    "load": {
      "extraDirs": ["~/.openclaw/workspace/skills"],
      "watch": true
    },
    "entries": {}
  }
}
EOF

chmod 600 ~/.openclaw/openclaw.json

# 6. Set up firewall rules (if ufw is available)
if command -v ufw &> /dev/null; then
    print_info "Configuring firewall..."
    # Note: OpenClaw Gateway is bound to loopback, but we may need port 22 for SSH
    # Add any additional ports as needed
fi

# 7. Create health check script
print_info "Creating health check script..."
cat > ~/.openclaw/health-check.sh << 'EOF'
#!/bin/bash
# OpenClaw health check script

if systemctl is-active --quiet openclaw.service; then
    echo "Service: ACTIVE"
else
    echo "Service: INACTIVE"
fi

if pgrep -f 'openclaw.*gateway' > /dev/null; then
    echo "Process: RUNNING"
else
    echo "Process: NOT RUNNING"
fi

echo "Version: $(openclaw --version 2>/dev/null || echo 'unknown')"

if [ -f ~/.openclaw/openclaw.json ]; then
    echo "Config: EXISTS"
else
    echo "Config: MISSING"
fi
EOF

chmod +x ~/.openclaw/health-check.sh

# 8. Summary
print_info "Setup complete!"
echo ""
echo "OpenClaw has been installed and configured as a systemd service."
echo ""
echo "Next steps:"
echo "1. Update configuration in ~/.openclaw/openclaw.json"
echo "2. Set OPENCLAW_GATEWAY_TOKEN environment variable:"
echo "   export OPENCLAW_GATEWAY_TOKEN='your-token-here'"
echo "   (Add to ~/.bashrc or ~/.profile for persistence)"
echo "3. Start the service:"
echo "   sudo systemctl start openclaw.service"
echo "4. Check status:"
echo "   sudo systemctl status openclaw.service"
echo "5. Run health check:"
echo "   ~/.openclaw/health-check.sh"
echo ""
echo "For remote access, use SSH tunneling:"
echo "  ssh -N -L 18789:127.0.0.1:18789 user@host"
echo ""
print_warn "Remember to configure your OpenClaw token before starting the service!"
