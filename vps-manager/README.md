# OpenClaw VPS Manager

Central management server for OpenClaw instances across multiple VPSes with SSH-key-only authentication, Git-based configuration management, and Zero Trust security.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Security Warning](#security-warning)
- [Quick Start](#quick-start)
- [Rich CLI Usage](#rich-cli-usage)
- [API Usage Examples](#api-usage-examples)
- [API Endpoints](#api-endpoints)
- [Development](#development)
- [Security](#security)
- [Production Deployment](#production-deployment)
- [Remote Access to OpenClaw](#remote-access-to-openclaw)
- [Troubleshooting](#troubleshooting)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)
- [Support](#support)

## Overview

OpenClaw VPS Manager is a centralized system for managing OpenClaw instances distributed across multiple VPSes from a single management server.

### Key Features

- 🚀 **Central Management**: Manage OpenClaw across multiple VPSes from a single server
- 🔐 **SSH-Key-Only**: No password authentication, Ed25519 keys only
- 📦 **Git-Based Config**: Version-controlled configuration with rollback support
- 🛡️ **Zero Trust Security**: mTLS, JWT auth, RBAC, customer isolation
- 🔒 **Customer Isolation**: Each customer has isolated Git branch and encryption keys
- 📝 **Audit Trail**: Complete logging of all administrative actions
- 🐳 **Docker Ready**: Fully containerized with docker-compose
- 🖥️ **Rich CLI**: Beautiful command-line interface

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   VPS Manager Server                         │
│                    (Python + FastAPI)                        │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  REST API    │  │   Git Repo   │  │  PostgreSQL   │ │
│  │  (FastAPI)   │  │   (Config)   │  │   (State)    │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│         │                  │                  │               │
│         └──────────────────┼──────────────────┘               │
│                            │                                │
└────────────────────────────┼────────────────────────────────┘
                             │ SSH (mTLS)
              ┌──────────────┼──────────────┐
              │              │              │
         ┌────▼────┐   ┌───▼────┐   ┌───▼────┐
         │  VPS 1  │   │  VPS 2  │   │  VPS N  │
         │(Customer │   │(Customer│   │(Customer│
         │    A)    │   │    B)   │   │    C)   │
         │          │   │         │   │         │
         │OpenClaw  │   │OpenClaw │   │OpenClaw │
         │Gateway   │   │Gateway  │   │Gateway  │
         └──────────┘   └─────────┘   └─────────┘
```

## Security Warning

⚠️ **Important Security Notice**

This system handles sensitive data including:
- SSH private keys
- Customer configurations
- Encryption keys
- API tokens

**Before using or publishing to Git, please review:**

1. ✅ Read `SECURITY.md` - Complete security documentation
2. ✅ Read `GIT_PUBLISHING_CHECKLIST.md` - Before publishing to Git
3. ✅ Never commit `.env` files
4. ✅ Verify encryption is working correctly
5. ✅ Change default credentials immediately

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- Git installed
- SSH access to VPS servers

### 1. Setup

```bash
cd vps-manager
cp .env.example .env
```

Edit `.env` if needed (default values work for local development).

### 2. Start Services

```bash
docker-compose up -d
```

This starts:
- PostgreSQL database (port 5432)
- VPS Manager API (port 8000)

### 3. Initialize Database

```bash
docker-compose exec api python scripts/init_db.py
```

This creates a default admin user:
- **Email**: `admin@openclaw.local`
- **Password**: `admin123`
- **⚠️ Important**: Change this immediately!

### 4. Verify Installation

```bash
# Check API health
curl http://localhost:8000/health

# Open API documentation
open http://localhost:8000/docs
```

## Rich CLI Usage

VPS Manager includes a beautiful command-line interface with rich formatting.

```bash
# Install dependencies (for local development)
pip install -r requirements.txt

# Set API URL and token
export VPS_MANAGER_API_URL="http://localhost:8000"
export VPS_MANAGER_TOKEN="YOUR_JWT_TOKEN"

# Health check
python cli.py health

# List VPS servers
python cli.py list-vps

# List customers
python cli.py list-customers

# Check VPS health
python cli.py check-health 1

# Deploy to VPS
python cli.py deploy-vps 1

# Restart VPS
python cli.py restart-vps 1

# View audit logs
python cli.py list-audit-logs

# Interactive mode
python cli.py interactive
```

### Interactive Mode

```bash
python cli.py interactive
```

Available commands in interactive mode:
```
health              - API health check
list-vps            - List VPS servers
list-customers      - List customers
list-deployments    - List deployments
show-config <id>    - Show customer configuration
deploy <vps-id>     - Deploy to VPS
restart <vps-id>    - Restart VPS service
check <vps-id>      - Check VPS health
logs                - Show audit logs
help                - Show help
exit                - Exit interactive mode
```

## API Usage Examples

For complete API documentation with all endpoints, schemas, and error handling, see [API_USAGE.md](API_USAGE.md).

### Quick Start Examples

### Create Customer

```bash
curl -X POST http://localhost:8000/api/v1/customers \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "name": "My Company",
    "description": "My First Customer"
  }'
```

### Add VPS

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

### Update Configuration

```bash
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
```

### Deploy to VPS

```bash
curl -X POST http://localhost:8000/api/v1/vps/1/deploy \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### Health Check

```bash
curl http://localhost:8000/api/v1/vps/1/health \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

## API Endpoints

### VPS Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/vps` | Create new VPS |
| GET | `/api/v1/vps` | List VPS servers (filtered) |
| GET | `/api/v1/vps/{id}` | Get VPS details |
| PUT | `/api/v1/vps/{id}` | Update VPS |
| DELETE | `/api/v1/vps/{id}` | Remove VPS |
| POST | `/api/v1/vps/{id}/deploy` | Deploy configuration |
| POST | `/api/v1/vps/{id}/restart` | Restart service |
| GET | `/api/v1/vps/{id}/health` | Health check |

### Customer Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/customers` | Create customer |
| GET | `/api/v1/customers` | List customers |
| GET | `/api/v1/customers/{id}` | Get customer details |
| PUT | `/api/v1/customers/{id}` | Update customer |
| DELETE | `/api/v1/customers/{id}` | Delete customer |

### Configuration Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/config/{customer_id}` | Get configuration |
| PUT | `/api/v1/config/{customer_id}` | Update configuration |
| POST | `/api/v1/config/{customer_id}/skills` | Manage skills |
| GET | `/api/v1/config/{customer_id}/skills` | List enabled skills |
| GET | `/api/v1/config/{customer_id}/history` | Config history |

### Audit Logging

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/audit/logs` | List audit logs |
| GET | `/api/v1/audit/vps/{vps_id}` | VPS audit trail |
| GET | `/api/v1/audit/stats` | Audit statistics |

### Deployment Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/deployments` | List deployments |
| GET | `/api/v1/deployments/{id}` | Get deployment details |
| POST | `/api/v1/deployments/{id}/rollback` | Rollback deployment |
| GET | `/api/v1/deployments/vps/{vps_id}` | VPS deployment history |

## Development

### Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL="postgresql://..."
export GIT_REPO_PATH="/path/to/git/repo"

# Initialize database
python scripts/init_db.py

# Run the API
python main.py
```

### Running Tests

```bash
pytest tests/
```

### SSH Key Rotation

```bash
# Rotate all VPS keys
python scripts/rotate_keys.py

# Rotate specific VPS key
python scripts/rotate_keys.py --vps-id 1
```

### Project Structure

```
vps-manager/
├── main.py                      # FastAPI application
├── cli.py                       # Rich CLI interface
├── config.py                    # Configuration management
├── database.py                  # Database models
├── requirements.txt              # Python dependencies
├── .env.example                # Environment template
├── .gitignore                  # Git ignore patterns
├── Dockerfile                  # Docker image
├── docker-compose.yml          # Full stack
├── setup-vps.sh              # VPS setup script
│
├── auth/                       # Authentication & authorization
│   ├── __init__.py
│   ├── middleware.py           # mTLS & JWT
│   └── rbac.py               # Role-based access control
│
├── services/                   # Core business logic
│   ├── __init__.py
│   ├── ssh_manager.py         # SSH connection pool
│   ├── git_manager.py         # Git operations
│   ├── openclaw_manager.py    # OpenClaw orchestration
│   └── encryption.py         # Configuration encryption
│
├── api/                       # REST API endpoints
│   ├── __init__.py
│   ├── vps.py               # VPS management
│   ├── customers.py         # Customer management
│   ├── config.py          # Configuration management
│   ├── audit.py           # Audit logging
│   └── deployments.py    # Deployment management
│
├── scripts/                   # Utility scripts
│   ├── init_db.py         # Database initialization
│   └── rotate_keys.py    # SSH key rotation
│
├── tests/                     # Test suite
│   └── test_api.py
│
├── README.md                  # This file
├── SECURITY.md               # Security documentation
└── QUICKSTART.md             # Quick start guide
```

## Security

### Zero Trust Model

1. **mTLS**: Client certificate verification (optional, recommended for production)
2. **SSH-Key-Only**: Ed25519 keys only, no passwords
3. **Customer Isolation**: Separate Git branches and encryption keys
4. **Data Protection**: AES-256-GCM encryption
5. **Audit Trail**: Complete logging of all actions

### Role-Based Access Control (RBAC)

| Role | Permissions |
|-------|-------------|
| admin | Full access to all resources |
| operator | Deploy and manage VPSes |
| auditor | Read-only access to audit logs |
| customer_admin | Manage own customer's resources only |

### Encryption

- **AES-256-GCM** encryption for customer configurations
- Per-customer encryption keys derived from master key
- Master key stored securely (chmod 600)
- Only encrypted files committed to Git

## Production Deployment

### 1. Environment Configuration

Edit `.env` with production values:
- Change `JWT_SECRET`
- Set `TLS_VERIFY_CLIENT=true`
- Configure `GIT_REPO_URL`
- Update database credentials

### 2. Generate TLS Certificates

```bash
# Generate CA certificate
openssl genrsa -out ca.key 4096
openssl req -new -x509 -days 365 -key ca.key -out ca.crt

# Generate server certificate
openssl genrsa -out server.key 4096
openssl req -new -key server.key -out server.csr
openssl x509 -req -days 365 -in server.csr -CA ca.crt -CAkey ca.key -set_serial 01 -out server.crt

# Generate client certificate
openssl genrsa -out client.key 4096
openssl req -new -key client.key -out client.csr
openssl x509 -req -days 365 -in client.csr -CA ca.crt -CAkey ca.key -set_serial 02 -out client.crt
```

### 3. Prepare Remote VPS

On each VPS:

```bash
# Copy setup script
scp setup-vps.sh user@vps:/tmp/

# Run setup
ssh user@vps
sudo bash /tmp/setup-vps.sh

# Add public key
echo "YOUR_PUBLIC_KEY" >> ~/.ssh/authorized_keys

# Enable key-only authentication
sudo sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo systemctl restart sshd
```

### 4. Start with Docker Compose

```bash
docker-compose up -d
docker-compose logs -f
```

## Remote Access to OpenClaw

OpenClaw Gateway runs on port 18789 (loopback only). Access it via SSH tunnel:

```bash
ssh -N -L 18789:127.0.0.1:18789 user@vps
```

Now you can access the gateway at `http://localhost:18789`.

## Troubleshooting

### Docker Container Won't Start

```bash
# Check logs
docker-compose logs api

# Restart services
docker-compose restart
```

### Database Connection Issues

```bash
# Check if PostgreSQL is running
docker-compose ps postgres

# Check database logs
docker-compose logs postgres
```

### SSH Connection Fails

```bash
# Test SSH manually
ssh -i /var/ssh/keys/vps_1_key user@vps

# Check key permissions
ls -la /var/ssh/keys/
```

### Health Check Returns Errors

```bash
# Check OpenClaw service on VPS
ssh user@vps "sudo systemctl status openclaw.service"

# Check OpenClaw logs
ssh user@vps "sudo journalctl -u openclaw.service -f"
```

## Documentation

- `API_USAGE.md` - Complete API documentation with examples and error handling
- `QUICKSTART.md` - Get started in 5 minutes
- `SECURITY.md` - Complete security documentation
- `GIT_PUBLISHING_CHECKLIST.md` - Checklist before publishing to Git
- `IMPLEMENTATION.md` - Detailed implementation guide
- `openclaw.config.example.json` - Example OpenClaw configuration

## Contributing

We welcome bug reports, feature requests, and pull requests!

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

### Development Guidelines

- Follow PEP 8 style guidelines
- Write tests for new features
- Update documentation as needed
- Ensure all tests pass before submitting

## License

This project is licensed under the MIT License.

## Support

For questions and issues:
- Full documentation: `QUICKSTART.md` and `SECURITY.md`
- API documentation: `http://localhost:8000/docs`
- GitHub Issues: Report bugs and feature requests

---

**Happy deploying! 🚀**
