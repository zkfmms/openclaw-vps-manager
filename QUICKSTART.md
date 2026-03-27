# Quick Start Guide

Get OpenClaw VPS Manager up and running in 5 minutes.

## Prerequisites

- Docker and Docker Compose installed
- Basic knowledge of SSH keys

## Step 1: Setup

```bash
cd vps-manager
cp .env.example .env
```

Edit `.env` if needed (default values work for local development).

## Step 2: Start Services

```bash
docker-compose up -d
```

This starts:
- PostgreSQL database on port 5432
- VPS Manager API on port 8000

## Step 3: Initialize Database

```bash
docker-compose exec api python scripts/init_db.py
```

This creates a default admin user:
- **Email**: `admin@openclaw.local`
- **Password**: `admin123`
- **Important**: Change this password immediately!

## Step 4: Verify Installation

```bash
# Check API health
curl http://localhost:8000/health

# View API documentation
open http://localhost:8000/docs
```

## Step 5: Use the CLI (Rich Interface)

The VPS Manager includes a beautiful rich CLI interface:

```bash
# Install dependencies locally (or use docker exec)
pip install -r requirements.txt

# Set API URL and token
export VPS_MANAGER_API_URL="http://localhost:8000"
export VPS_MANAGER_TOKEN="admin@example.com:password"  # Replace with actual JWT

# Check health
python cli.py health

# List all VPS servers
python cli.py list-vps

# List customers
python cli.py list-customers

# Check a VPS health
python cli.py check-health 1

# Deploy to a VPS
python cli.py deploy-vps 1

# Restart a VPS
python cli.py restart-vps 1

# View audit logs
python cli.py list-audit-logs

# Interactive mode
python cli.py interactive
```

## Step 6: Create Your First Customer

```bash
curl -X POST http://localhost:8000/api/v1/customers \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "name": "My Company",
    "description": "My First Customer"
  }'
```

## Step 7: Add a VPS

```bash
curl -X POST http://localhost:8000/api/v1/vps \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "customer_id": 1,
    "hostname": "your-vps.example.com",
    "ssh_user": "openclaw",
    "openclaw_version": "latest"
  }'
```

This automatically:
1. Generates a unique Ed25519 SSH key pair
2. Creates a VPS record in the database
3. Stores the private key securely

## Step 8: Prepare Your VPS

On your target VPS:

```bash
# Copy the public key from the VPS Manager (shown when you create the VPS)
# Add it to authorized_keys
echo "YOUR_PUBLIC_KEY_HERE" >> ~/.ssh/authorized_keys

# Ensure SSH key-only authentication
sudo sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo systemctl restart sshd

# Run the setup script (or copy from VPS Manager)
bash setup-vps.sh
```

## Step 9: Deploy Configuration

```bash
# Update configuration (example)
curl -X PUT http://localhost:8000/api/v1/config/1 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "agent": {
      "model": "anthropic/claude-sonnet-4-6"
    },
    "gateway": {
      "port": 18789,
      "bind": "loopback"
    }
  }'

# Deploy to VPS
curl -X POST http://localhost:8000/api/v1/vps/1/deploy \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

## Step 10: Verify Deployment

```bash
# Check health via CLI
python cli.py check-health 1

# Or via API
curl http://localhost:8000/api/v1/vps/1/health \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

## Next Steps

### Remote Access to OpenClaw

OpenClaw Gateway runs on port 18789 (loopback only). Access it via SSH tunnel:

```bash
ssh -N -L 18789:127.0.0.1:18789 user@vps
```

Now you can access the gateway at `http://localhost:18789`.

### Managing Skills

```bash
# List enabled skills
python cli.py show-config 1

# Enable a skill via API
curl -X POST http://localhost:8000/api/v1/config/1/skills \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "skill_name": "weather",
    "enabled": true,
    "config": {}
  }'
```

### Viewing Audit Logs

```bash
# View all audit logs
python cli.py list-audit-logs

# View logs for specific VPS
curl http://localhost:8000/api/v1/audit/vps/1 \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### Rollback Configuration

```bash
# List deployment history
python cli.py list-deployments

# Rollback to previous version
curl -X POST http://localhost:8000/api/v1/deployments/1/rollback \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

## Production Setup

For production deployment:

1. **Change all default credentials** in `.env`
2. **Enable mTLS** by setting `TLS_VERIFY_CLIENT=true`
3. **Generate proper TLS certificates**
4. **Configure Git repository URL** for backup
5. **Use a secrets manager** for encryption keys
6. **Set up monitoring and alerts**
7. **Configure firewall rules**
8. **Enable rate limiting**

## Troubleshooting

### Docker container won't start

```bash
# Check logs
docker-compose logs api

# Restart services
docker-compose restart
```

### Can't connect to database

```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Check database logs
docker-compose logs postgres
```

### SSH connection fails

```bash
# Test SSH manually
ssh -i /var/ssh/keys/vps_1_key user@vps

# Check key permissions
ls -la /var/ssh/keys/
```

### Health check returns errors

```bash
# Check OpenClaw service on VPS
ssh user@vps "sudo systemctl status openclaw.service"

# Check OpenClaw logs
ssh user@vps "sudo journalctl -u openclaw.service -f"
```

## Getting Help

- Full documentation: `README.md`
- API documentation: `http://localhost:8000/docs`
- GitHub Issues: Report bugs and feature requests

## Security Best Practices

1. **Never commit SSH keys** to version control
2. **Rotate SSH keys** regularly: `python scripts/rotate_keys.py`
3. **Use strong JWT secrets**
4. **Enable mTLS** in production
5. **Audit logs regularly**
6. **Monitor deployment status**
7. **Backup Git repository**

Happy deploying! 🚀
