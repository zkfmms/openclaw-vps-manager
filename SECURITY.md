# Security Documentation

## Overview

The OpenClaw VPS Manager implements a Zero Trust security model to protect sensitive data and ensure secure operations across all components.

## Security Principles

### 1. Encryption at Rest

- **AES-256-GCM** encryption for all customer configurations
- Per-customer encryption keys derived from master key
- Master key stored in secure location with restricted permissions (chmod 600)
- Encrypted files committed to Git: `openclaw.json.enc`
- Unencrypted files excluded via `.gitignore`

### 2. SSH Security

- **Ed25519 keys only** (no RSA, no password authentication)
- Each VPS gets unique SSH key pair
- Keys stored encrypted in PostgreSQL
- SSH key rotation support with backup
- No password-based authentication allowed

### 3. Authentication

- **JWT tokens** with configurable expiration
- **mTLS support** (optional, recommended for production)
- **bcrypt** password hashing with salt
- Role-Based Access Control (RBAC)

### 4. Customer Isolation

- Each customer has isolated Git branch
- Separate encryption keys per customer
- Database queries filtered by customer_id
- RBAC prevents cross-customer access
- Audit logs track all access

### 5. Audit Trail

- Complete logging of all administrative actions
- Immutable audit logs (append-only)
- IP address tracking
- User attribution for all changes

## Sensitive Data Protection

### What's Protected

| Data Type | Protection Method |
|-----------|------------------|
| SSH Private Keys | File permissions, never in Git |
| Customer Configurations | AES-256-GCM encryption |
| Database Passwords | Environment variables (.env) |
| JWT Secrets | Environment variables (.env) |
| TLS Certificates | Secure storage, never in Git |
| API Tokens | Environment variables |

### What's in Git

✅ **Safe to commit:**
- Encrypted configuration files (`*.json.enc`)
- Template files (`.template` extension)
- Deployment tracking metadata
- Skill configuration (non-sensitive parts)
- AGENTS.md template

❌ **Never committed:**
- Unencrypted configuration files (`openclaw.json`)
- SSH private keys (`*.key`, `*.pem`)
- TLS certificates (server.key, ca.key)
- Environment files (`.env`)
- Database backups
- Encryption master keys

## Git Repository Security

### .gitignore Configuration

The Git repository includes a comprehensive `.gitignore` that:

1. **Excludes all unencrypted JSON files**:
   ```
   **/openclaw.json
   **/openclaw.json.bak
   ```

2. **Includes only encrypted versions**:
   ```
   !**/openclaw.json.enc
   ```

3. **Excludes sensitive directories**:
   ```
   **/credentials/
   **/secrets/
   **/tokens/
   ```

4. **Excludes backup SSH keys**:
   ```
   **/*.key.bak
   **/*.pem.bak
   ```

### Workflow for Publishing to Public Git

When publishing to a public Git repository:

1. **Verify encryption is working**:
   ```bash
   # Check that encrypted files exist
   find git-repo -name "*.enc" -type f

   # Verify unencrypted files are not staged
   git status
   ```

2. **Commit only encrypted files**:
   ```bash
   # Add only encrypted files
   git add *.enc
   git add templates/
   git add .gitignore

   # Never add unencrypted configs
   # git add openclaw.json  # DON'T DO THIS!
   ```

3. **Review what will be pushed**:
   ```bash
   git diff --cached --name-only
   ```

4. **Push to remote**:
   ```bash
   git push origin customer-1
   ```

## Environment Variables

### Required Variables (Never Commit)

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:port/db

# JWT
JWT_SECRET=your-secret-key-here

# Encryption
ENCRYPTION_KEY_PATH=/var/keys/encryption

# TLS (if mTLS enabled)
TLS_CERT_PATH=/var/tls/cert.pem
TLS_KEY_PATH=/var/tls/key.pem
TLS_CA_CERT_PATH=/var/tls/ca.pem

# Git (if using remote)
GIT_REPO_URL=git@github.com:org/repo.git
```

### Recommended Setup

1. **Never commit `.env` files**
2. **Use `.env.example` as template**
3. **Use secrets manager in production** (AWS KMS, HashiCorp Vault)
4. **Rotate secrets regularly**

## SSH Key Management

### Key Generation

```bash
# Keys are generated automatically when creating VPS
# Ed25519 keys only
# Private keys: /var/ssh/keys/vps_{id}_key
# Public keys: /var/ssh/keys/vps_{id}_key.pub
```

### Key Rotation

```bash
# Rotate all SSH keys
python scripts/rotate_keys.py

# Rotate specific VPS key
python scripts/rotate_keys.py --vps-id 1
```

### Key Security

- Private keys have restricted permissions (600)
- Never committed to Git
- Encrypted in database
- Backup created before rotation

## TLS/mTLS Configuration

### For Development

```bash
TLS_VERIFY_CLIENT=false
```

### For Production

```bash
TLS_VERIFY_CLIENT=true
# Generate proper CA and client certificates
```

## Access Control

### Roles and Permissions

| Role | Permissions |
|------|-------------|
| admin | Full access to all resources |
| operator | Deploy and manage VPSes |
| auditor | Read-only audit access |
| customer_admin | Manage own customer's resources |

### Customer Isolation

- Customer admins can only access their own data
- API queries filtered by `customer_id`
- Git branches are customer-specific
- Encryption keys are customer-specific

## Best Practices

### Before Publishing to Git

1. ✅ Verify `.gitignore` is configured
2. ✅ Check for unencrypted config files
3. ✅ Ensure SSH keys are not tracked
4. ✅ Verify no API tokens in code
5. ✅ Review commit history for secrets

### Production Deployment

1. ✅ Enable mTLS
2. ✅ Use secrets manager for keys
3. ✅ Configure firewall rules
4. ✅ Enable rate limiting
5. ✅ Set up monitoring
6. ✅ Regular key rotation
7. ✅ Audit log monitoring
8. ✅ Backup encryption keys securely

### Security Audits

Regular security audits should verify:

- [ ] No unencrypted configs in Git
- [ ] SSH keys are rotated quarterly
- [ ] TLS certificates are valid
- [ ] JWT secrets are strong
- [ ] Database credentials are secure
- [ ] Audit logs are complete
- [ ] RBAC is correctly configured

## Incident Response

If a security breach is suspected:

1. **Immediate actions:**
   - Rotate all SSH keys
   - Rotate JWT secret
   - Rotate encryption master key
   - Revoke TLS certificates

2. **Investigation:**
   - Review audit logs
   - Identify affected customers
   - Assess data exposure

3. **Recovery:**
   - Restore from backups
   - Notify affected users
   - Document the incident
   - Update security policies

## Compliance

This system implements security controls for:

- **Zero Trust Architecture**
- **Defense in Depth**
- **Principle of Least Privilege**
- **Audit Trail Requirements**
- **Data at Rest Encryption**
- **Secure Key Management**

## Questions or Security Issues?

Report security concerns immediately:
- Do NOT open public issues
- Contact security team privately
- Provide detailed reproduction steps
- Await response before disclosure

---

**Remember: Security is everyone's responsibility.**
