# OpenClaw VPS Manager API Documentation

Complete API reference for the OpenClaw VPS Manager.

## Table of Contents

- [Authentication](#authentication)
- [Request Format](#request-format)
- [Response Format](#response-format)
- [Error Handling](#error-handling)
- [VPS Management](#vps-management)
- [Customer Management](#customer-management)
- [Configuration Management](#configuration-management)
- [Audit Logging](#audit-logging)
- [Deployment Management](#deployment-management)
- [Health Checks](#health-checks)

---

## Authentication

All API endpoints (except health checks) require authentication using JWT tokens.

### Getting a Token

To get an authentication token, you need to log in with valid credentials:

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "your-password"
  }'
```

Response:

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

### Using the Token

Include the token in the `Authorization` header:

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/v1/vps
```

### Token Refresh

Tokens expire after 24 hours (configurable). Use the refresh endpoint to get a new token:

```bash
curl -X POST http://localhost:8000/api/v1/auth/refresh \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Request Format

### Common Headers

| Header | Description | Required |
|--------|-------------|-----------|
| `Authorization` | Bearer JWT token | Yes (except health) |
| `Content-Type` | `application/json` | Yes for POST/PUT |
| `X-Request-ID` | Unique request identifier | No |
| `Accept` | Response format (application/json) | No |

### Query Parameters

| Parameter | Type | Description |
|-----------|--------|-------------|
| `customer_id` | integer | Filter by customer ID |
| `limit` | integer | Number of results to return |
| `offset` | integer | Number of results to skip |

---

## Response Format

### Success Response

```json
{
  "data": { /* response data */ },
  "meta": {
    "page": 1,
    "per_page": 100,
    "total": 500
  }
}
```

### Error Response

```json
{
  "error": "ERROR_CODE",
  "message": "Human-readable error message",
  "status_code": 400,
  "path": "/api/v1/vps",
  "request_id": "uuid-of-request",
  "details": {
    "field": "error details"
  }
}
```

---

## Error Handling

### Error Codes

| Code | Status | Description |
|------|--------|-------------|
| `AUTHENTICATION_ERROR` | 401 | Invalid or expired token |
| `AUTHORIZATION_ERROR` | 403 | Insufficient permissions |
| `VALIDATION_ERROR` | 400 | Invalid input data |
| `NOT_FOUND` | 404 | Resource not found |
| `CONFLICT` | 409 | Resource already exists |
| `INTERNAL_ERROR` | 500 | Server error |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |
| `VPS_NOT_FOUND` | 404 | VPS server not found |
| `CUSTOMER_NOT_FOUND` | 404 | Customer not found |
| `DEPLOYMENT_ERROR` | 500 | Deployment failed |
| `SSH_CONNECTION_ERROR` | 503 | Cannot connect to VPS |
| `GIT_OPERATION_ERROR` | 500 | Git operation failed |

### Handling Errors

Always check the `status_code` field and handle errors appropriately:

```python
response = requests.get("/api/v1/vps/999")

if response.status_code == 404:
    print("VPS not found")
elif response.status_code == 403:
    print("Permission denied")
elif response.status_code >= 500:
    print("Server error, please try again later")
```

---

## VPS Management

### Create VPS

```bash
curl -X POST http://localhost:8000/api/v1/vps \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": 1,
    "hostname": "vps.example.com",
    "ssh_user": "openclaw",
    "openclaw_version": "latest"
  }'
```

**Request Schema:**

| Field | Type | Required | Description |
|-------|--------|-----------|-------------|
| `customer_id` | integer | Yes | Customer ID to assign VPS to |
| `hostname` | string | Yes | VPS hostname or IP address |
| `ssh_user` | string | No | SSH username (default: "openclaw") |
| `openclaw_version` | string | No | OpenClaw version (default: "latest") |

**Response:**

```json
{
  "id": 1,
  "customer_id": 1,
  "hostname": "vps.example.com",
  "ssh_user": "openclaw",
  "openclaw_version": "latest",
  "status": "pending",
  "last_health_check": null,
  "last_deployment_at": null,
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z"
}
```

**Possible Status Values:**
- `pending`: VPS created but not yet deployed
- `active`: VPS is running and healthy
- `maintenance`: VPS is under maintenance
- `error`: VPS has errors
- `decommissioned`: VPS has been removed

### List VPS

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/v1/vps?customer_id=1&limit=10"
```

### Get VPS Details

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/v1/vps/{id}"
```

### Update VPS

```bash
curl -X PUT http://localhost:8000/api/v1/vps/{id} \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "openclaw_version": "1.2.3",
    "status": "active"
  }'
```

### Delete VPS

```bash
curl -X DELETE http://localhost:8000/api/v1/vps/{id} \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Deploy to VPS

```bash
curl -X POST http://localhost:8000/api/v1/vps/{id}/deploy \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Response:**

```json
{
  "id": 123,
  "vps_id": 1,
  "customer_id": 1,
  "git_commit_hash": "abc123def456...",
  "deployed_at": "2024-01-01T12:00:00Z",
  "status": "success",
  "rollback_commit": null,
  "error_message": null
}
```

### Restart VPS

```bash
curl -X POST http://localhost:8000/api/v1/vps/{id}/restart \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### VPS Health Check

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/v1/vps/{id}/health"
```

**Response:**

```json
{
  "vps_id": 1,
  "service_active": true,
  "process_running": true,
  "version": "1.2.3",
  "config_exists": true,
  "timestamp": "2024-01-01T12:00:00Z"
}
```

---

## Customer Management

### Create Customer

```bash
curl -X POST http://localhost:8000/api/v1/customers \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Acme Corp",
    "description": "Acme Corporation VPS deployment"
  }'
```

**Request Schema:**

| Field | Type | Required | Description |
|-------|--------|-----------|-------------|
| `name` | string | Yes | Customer name |
| `description` | string | No | Customer description |

### List Customers

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/v1/customers"
```

### Get Customer Details

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/v1/customers/{id}"
```

### Update Customer

```bash
curl -X PUT http://localhost:8000/api/v1/customers/{id} \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Updated Name",
    "is_active": true
  }'
```

### Delete Customer

```bash
curl -X DELETE http://localhost:8000/api/v1/customers/{id} \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Configuration Management

### Get Customer Configuration

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/v1/config/{customer_id}"
```

**Response:**

```json
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
```

### Update Customer Configuration

```bash
curl -X PUT http://localhost:8000/api/v1/config/{customer_id} \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "agent": {
      "model": "anthropic/claude-opus-4-6"
    }
  }'
```

**Response:**

```json
{
  "message": "Configuration updated successfully",
  "commit_hash": "abc123def456789..."
}
```

### Manage Skills

```bash
# Enable a skill
curl -X POST http://localhost:8000/api/v1/config/{customer_id}/skills \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "skill_name": "web_browsing",
    "enabled": true,
    "config": {
      "max_pages": 10,
      "timeout": 30
    }
  }'

# Disable a skill
curl -X POST http://localhost:8000/api/v1/config/{customer_id}/skills \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "skill_name": "web_browsing",
    "enabled": false
  }'
```

### List Enabled Skills

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/v1/config/{customer_id}/skills"
```

**Response:**

```json
[
  "web_browsing",
  "file_operations",
  "code_execution"
]
```

### Get Configuration History

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/v1/config/{customer_id}/history?limit=10"
```

**Response:**

```json
[
  {
    "hash": "abc123def456...",
    "message": "Update configuration for customer 1",
    "author": "admin@example.com",
    "timestamp": "2024-01-01T12:00:00Z"
  }
]
```

---

## Audit Logging

### List Audit Logs

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/v1/audit/logs?limit=50&customer_id=1"
```

**Response:**

```json
[
  {
    "id": 1234,
    "user_id": 1,
    "vps_id": 10,
    "customer_id": 1,
    "action": "deploy",
    "resource_type": "vps",
    "resource_id": 10,
    "details": {},
    "ip_address": "192.168.1.100",
    "timestamp": "2024-01-01T12:00:00Z"
  }
]
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|--------|-------------|
| `customer_id` | integer | Filter by customer |
| `vps_id` | integer | Filter by VPS |
| `action` | string | Filter by action (create, update, delete, deploy, restart) |
| `limit` | integer | Maximum results (default: 100) |
| `offset` | integer | Skip N results (for pagination) |

### Get VPS Audit Trail

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/v1/audit/vps/{vps_id}"
```

### Get Audit Statistics

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/v1/audit/stats"
```

**Response:**

```json
{
  "by_resource_type": {
    "customer": 15,
    "vps": 50,
    "deployment": 100,
    "config": 75,
    "user": 5
  },
  "by_action": {
    "create": 30,
    "update": 45,
    "delete": 5,
    "deploy": 100,
    "restart": 65
  }
}
```

---

## Deployment Management

### List Deployments

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/v1/deployments?customer_id=1&status=success"
```

### Get Deployment Details

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/v1/deployments/{id}"
```

### Rollback Deployment

```bash
curl -X POST http://localhost:8000/api/v1/deployments/{id}/rollback \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Response:**

```json
{
  "message": "Rollback completed successfully",
  "rollback_commit": "xyz789abc123...",
  "previous_commit": "abc123def456..."
}
```

### Get VPS Deployment History

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/v1/deployments/vps/{vps_id}"
```

---

## Health Checks

### Basic Health Check

```bash
curl http://localhost:8000/health
```

**Response:**

```json
{
  "status": "healthy",
  "service": "OpenClaw VPS Manager",
  "version": "1.0.0",
  "timestamp": "2024-01-01T12:00:00Z"
}
```

### Liveness Probe

```bash
curl http://localhost:8000/health/live
```

**Response:**

```json
{
  "status": "alive",
  "timestamp": "2024-01-01T12:00:00Z"
}
```

### Readiness Probe

```bash
curl http://localhost:8000/health/ready
```

**Response:**

```json
{
  "status": "ready",
  "checks": {
    "database": {
      "status": "healthy",
      "message": "Database connection established"
    },
    "ssh_pool": {
      "status": "healthy",
      "message": "SSH connection pool initialized"
    }
  },
  "timestamp": "2024-01-01T12:00:00Z"
}
```

### Metrics Endpoint

```bash
curl http://localhost:8000/metrics
```

**Response (Prometheus format):**

```
# TYPE http_request_duration summary
http_request_duration_count 1000
http_request_duration_sum 45.5
http_request_duration_min 0.01
http_request_duration_max 2.5
```

---

## Rate Limiting

The API implements rate limiting to prevent abuse:

- **Default**: 100 requests per 60 seconds
- **Headers**: Rate limit info is returned in response headers
  - `X-RateLimit-Limit`: Maximum requests per window
  - `X-RateLimit-Remaining`: Requests remaining in current window
  - `X-RateLimit-Reset`: Unix timestamp when window resets

**Rate Limit Exceeded Response:**

```json
{
  "error": "RATE_LIMIT_EXCEEDED",
  "message": "Rate limit exceeded: 100 requests per 60 seconds",
  "status_code": 429,
  "retry_after": 60
}
```

---

## Security

### Password Requirements

All passwords must meet the following requirements:

- Minimum 12 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one digit
- At least one special character (!@#$%^&*()_+-=[]{}|;:,.<>?)

### Input Validation

All input is validated:

- Hostnames must match pattern: `^[\w\-\.]+$`
- Maximum request size: 10 MB
- SQL injection protection on all string inputs
- XSS protection on all text outputs

### Security Headers

All API responses include security headers:

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Strict-Transport-Security: max-age=31536000; includeSubDomains
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

---

## Examples

### Complete Workflow Example

```bash
# 1. Get auth token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "password"}' \
  | jq -r '.access_token')

# 2. Create a customer
CUSTOMER_ID=$(curl -s -X POST http://localhost:8000/api/v1/customers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "My Company"}' \
  | jq -r '.id')

# 3. Add a VPS
VPS_ID=$(curl -s -X POST http://localhost:8000/api/v1/vps \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"customer_id": '$CUSTOMER_ID', "hostname": "vps1.example.com"}' \
  | jq -r '.id')

# 4. Update configuration
curl -X PUT http://localhost:8000/api/v1/config/$CUSTOMER_ID \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"agent": {"model": "anthropic/claude-opus-4-6"}}'

# 5. Deploy to VPS
curl -X POST http://localhost:8000/api/v1/vps/$VPS_ID/deploy \
  -H "Authorization: Bearer $TOKEN"

# 6. Check VPS health
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/vps/$VPS_ID/health
```

### Python Example

```python
import requests
import json

class VPSManagerClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.token = None

    def login(self, email, password):
        """Authenticate and get token."""
        response = requests.post(
            f"{self.base_url}/api/v1/auth/login",
            json={"email": email, "password": password}
        )
        response.raise_for_status()
        self.token = response.json()["access_token"]

    def _headers(self):
        """Get headers with auth token."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def create_vps(self, customer_id, hostname):
        """Create a new VPS."""
        response = requests.post(
            f"{self.base_url}/api/v1/vps",
            headers=self._headers(),
            json={
                "customer_id": customer_id,
                "hostname": hostname
            }
        )
        response.raise_for_status()
        return response.json()

    def deploy_vps(self, vps_id):
        """Deploy configuration to VPS."""
        response = requests.post(
            f"{self.base_url}/api/v1/vps/{vps_id}/deploy",
            headers=self._headers()
        )
        response.raise_for_status()
        return response.json()

# Usage
client = VPSManagerClient()
client.login("admin@example.com", "password")
vps = client.create_vps(1, "vps.example.com")
print(f"Created VPS {vps['id']}")
client.deploy_vps(vps["id"])
print("Deployment complete!")
```

---

## SDK / Client Libraries

Official client libraries are available:

- Python: `pip install openclaw-vps-manager`
- JavaScript: `npm install @openclaw/vps-manager-client`
- Go: `go get github.com/openclaw/vps-manager-go`

For more information, see the [SDK documentation](https://github.com/openclaw/vps-manager/sdk).

---

## Support

- Documentation: [https://docs.openclaw.dev/vps-manager](https://docs.openclaw.dev/vps-manager)
- API Reference: https://localhost:8000/docs (when running locally)
- Issues: [GitHub Issues](https://github.com/openclaw/vps-manager/issues)
- Email: support@openclaw.dev
