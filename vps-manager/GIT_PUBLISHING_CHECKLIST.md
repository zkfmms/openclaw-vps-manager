# Git Publishing Checklist

Use this checklist before publishing the VPS Manager to any public Git repository.

## Pre-Publishing Checks

### 1. Verify Sensitive Files Are Not Tracked

```bash
# Check for .env files
git status | grep .env

# Check for SSH keys
git ls-files | grep -E '\.(key|pem)$'

# Check for encryption keys
git ls-files | grep -i 'encryption\|secret\|credential\|token'

# Should return no results for sensitive files
```

### 2. Verify .gitignore Coverage

```bash
# Check if .gitignore exists and is properly configured
cat .gitignore

# Should include patterns for:
# - *.key, *.pem (SSH/TLS keys)
# - .env, .env.local (env files)
# - **/openclaw.json (unencrypted configs)
# - secrets/, credentials/, tokens/ directories
```

### 3. Verify Encryption Implementation

```bash
# Check that encrypted config files exist
find . -name "*.enc" -type f

# Check that unencrypted config files are NOT in Git
git ls-files | grep openclaw.json | grep -v '.enc'

# Should return only .enc files or nothing
```

### 4. Review Environment Variables

```bash
# Check that .env.example exists but .env is not tracked
git ls-files | grep -E '^\.env$'  # Should return nothing
git ls-files | grep '.env.example'   # Should return .env.example
```

### 5. Check for Hardcoded Secrets

```bash
# Check for API keys, tokens, passwords in code
grep -rE '(api_key|token|password|secret)' --include='*.py' --exclude-dir=tests

# Look for database connection strings
grep -rE '(DATABASE_URL|postgresql://|mysql://)' --include='*.py'

# Should only find references to env variables, not actual values
```

## Verification Commands

```bash
# Show all tracked files
git ls-files

# Show files staged for commit
git diff --cached --name-only

# Show untracked files that might be sensitive
git status --short | grep -E '\.(key|pem|env|json)$'

# Verify no SSH keys in repository
git ls-files | grep -E '\.(key|pem)$'

# Verify no unencrypted configs in repository
git ls-files | grep 'openclaw.json' | grep -v '.enc'

# Verify no .env files in repository
git ls-files | grep -E '^\.env$'
```

## Safe Files to Commit

✅ Python source files (`*.py`)
✅ Configuration templates (`*.template`)
✅ Encrypted config files (`*.enc`)
✅ Documentation (`*.md`)
✅ Docker files (`Dockerfile`, `docker-compose.yml`)
✅ Environment template (`.env.example`)
✅ Test files
✅ `.gitignore` (properly configured)
✅ Git repository's own `.gitignore` (for config repo)

## Files Never to Commit

❌ Environment files (`.env`, `.env.local`)
❌ SSH private keys (`*.key`, `*.pem`)
❌ TLS certificates (`ca.key`, `server.key`)
❌ Encryption master keys
❌ Unencrypted config files (`openclaw.json`)
❌ Database backups (`*.db`, `*.sql`)
❌ API tokens or secrets
❌ Password files
❌ Customer-specific credentials

## Common Mistakes to Avoid

### ❌ Mistake 1: Adding All Files

```bash
# DON'T DO THIS:
git add .
git commit -m "Initial commit"
```

### ✅ Correct Approach:

```bash
# Add specific files only:
git add src/
git add tests/
git add requirements.txt
git add Dockerfile
git add README.md
git add .gitignore
```

### ❌ Mistake 2: Including Config Files

```bash
# DON'T DO THIS:
git add config/openclaw.json
```

### ✅ Correct Approach:

```bash
# Only add encrypted version:
git add config/openclaw.json.enc
```

### ❌ Mistake 3: Pushing .env Files

```bash
# DON'T DO THIS:
git add .env
```

### ✅ Correct Approach:

```bash
# Add template instead:
git add .env.example
# Create local .env from template:
cp .env.example .env
```

## After Publishing

### 1. Monitor Repository

```bash
# Watch for accidental commits
git log --all --full-history --oneline

# Check for sensitive files in all branches
git ls-files -r | grep -E '\.(key|pem|env|db)$'
```

### 2. Educate Team

- Share this checklist
- Train on security practices
- Set up pre-commit hooks
- Use git-secrets if available

### 3. Set Up Git Hooks

Consider installing `git-secrets`:

```bash
# Install git-secrets
brew install git-secrets  # macOS
# or
apt-get install git-secrets  # Ubuntu

# Configure patterns to block
git secrets --install
git secrets --register-aws
git secrets --add 'password\s*=\s*".+"'
git secrets --add 'api_key\s*=\s*".+"'
```

## Emergency: If You Accidentally Committed Secrets

### 1. Immediately Revoke

```bash
# Cancel any compromised keys/tokens
# Rotate SSH keys
# Rotate JWT secrets
# Revoke TLS certificates
```

### 2. Remove from History

```bash
# Remove file from git history
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch filename.txt" \
  --prune-empty --tag-name-filter cat -- --all

# Clean up
git reflog expire --expire=now --all
git gc --prune=now --aggressive
```

### 3. Force Push

```bash
# WARNING: This rewrites history
git push origin --force --all
git push origin --force --tags
```

### 4. Notify Users

- Inform all users of the breach
- Provide remediation steps
- Document the incident

## Regular Maintenance

### Weekly Checks

- [ ] Review recent commits for secrets
- [ ] Check .gitignore coverage
- [ ] Verify encryption status
- [ ] Update documentation

### Monthly Checks

- [ ] Rotate SSH keys
- [ ] Review audit logs
- [ ] Update dependencies
- [ ] Security scan repository

## Questions?

If you're unsure about whether a file is safe to commit:

1. Review the content
2. Check if it's in `.gitignore`
3. Ask in a private channel
4. Err on the side of caution

---

**Remember: Once published, removing files from Git history is difficult.**
**Better to be safe than sorry!**
