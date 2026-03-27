# VPS Git Bidirectional Synchronization Guide

## Overview

The VPS Manager supports bidirectional Git synchronization between the central management server and VPS instances. This allows changes made on the VPS to be synced back to the central repository, and vice versa.

## Architecture

```
┌─────────────────────────────────────────────┐
│     VPS Manager (中央サーバー)         │
│  Git Repo: /var/git/openclaw-configs  │
│                                        │
│  Git Push/Pull (双方向)            │
├─────────────────────────────────────────────┤
│         SSH                           │
│                                        │
│  ┌──────────┐   Git Repo: ~/.openclaw  │
│  │   VPS     │                       │
│  └──────────┘                       │
└─────────────────────────────────────────────┘
```

## How It Works

### 1. Two-Way Synchronization

**Push (Central → VPS):**
```
VPS Manager → SSH → VPS Git → Commit
```

**Pull (VPS → Central):**
```
VPS Git → SSH → VPS Manager → Merge → Central Git
```

### 2. Conflict Resolution

When both sides have changes to the same files, conflicts occur:

- **Local (Remote)**: Prefer remote changes
- **Remote (Local)**: Prefer local changes
- **Merge**: AI-assisted merge
- **Manual**: Manual resolution required

### 3. Sync Status

| Status | Description |
|---------|-------------|
| pending | Sync queued |
| in_progress | Sync in progress |
| success | Sync completed |
| failed | Sync failed |
| conflict | Merge conflict detected |

## CLI Usage

### Basic Sync
```bash
python cli.py sync vps <vps-id>
```

### Directional Sync
```bash
# Pull changes from VPS only
python cli.py sync vps <vps-id> --pull

# Push changes to VPS only
python cli.py sync vps <vps-id> --push
```

### Force Sync
```bash
# Force sync (overwrites VPS changes)
python cli.py sync vps <vps-id> --force
```

### Check Status
```bash
python cli.py sync status <vps-id>
```

### View Sync History
```bash
python cli.py sync history <vps-id>
```

### Data Synchronization (New!)
```bash
# Sync OpenClaw data (tweets, skills, etc.) from any VPS
python cli.py sync-data <hostname>

# Example: Sync from rokkonch
python cli.py sync-data rokkonch

# Sync with custom database path
python cli.py sync-data rokkonch --db-path /custom/path/tweets.db

# Sync without creating backup
python cli.py sync-data rokkonch --no-backup

# Sync from custom workspace directory
python cli.py sync-data user@vps.example.com --workspace-dir /path/to/workspace
```

**What gets synced:**
- Tweet data (my_tweets.json, replies_to_target.json, etc.)
- Skills directory (backup only)
- All data stored in local SQLite database

**Key features:**
- Works with any VPS hostname (not just rokkonch)
- Automatic database creation and schema management
- Duplicate detection and handling
- Progress reporting for large datasets
- Configurable paths and options

### Resolve Conflict
```bash
python cli.py resolve sync <vps-id> local
python cli.py resolve sync <vps-id> remote
python cli.py resolve sync <vps-id> merge
```

## API Endpoints

### Trigger Sync
```http
POST /api/v1/sync/vps/{vps_id}/sync
Content-Type: application/json
Authorization: Bearer <token>

{
  "direction": "both",  // "push", "pull", or "both"
  "force": false
}
```

### Get Sync Status
```http
GET /api/v1/sync/vps/{vps_id}/status
Authorization: Bearer <token>
```

### Resolve Conflict
```http
POST /api/v1/sync/vps/{vps_id}/resolve-conflict
Content-Type: application/json
Authorization: Bearer <token>

{
  "resolution": "local"  // "local", "remote", "merge", or "manual"
}
```

### Get Sync History
```http
GET /api/v1/sync/vps/{vps_id}/history?limit=50
Authorization: Bearer <token>
```

### Compare Repositories
```http
GET /api/v1/sync/vps/{vps_id}/compare
Authorization: Bearer <token>
```

## Interactive Mode Commands

```
vps-manager> sync vps <id>
vps-manager> sync vps <id> --pull
vps-manager> sync vps <id> --push
vps-manager> sync vps <id> --force
vps-manager> sync status <id>
vps-manager> sync history <id>
vps-manager> resolve sync <id> <resolution>
```

## Best Practices

### 1. Before Syncing
- Commit all local changes first
- Check VPS is online and healthy
- Review sync history for conflicts

### 2. During Sync
- Monitor sync status
- Wait for completion before next action
- Handle conflicts promptly

### 3. After Sync
- Verify changes are present on both sides
- Test OpenClaw service
- Check VPS health

### 4. Conflict Handling
- Understand what changes were made
- Choose appropriate resolution strategy
- Document resolution in sync history

### 5. Automation

- Set up periodic sync via cron
- Use webhooks for instant notification
- Monitor sync failures and retry

## Automation Example

### Cron Job (Sync Every 5 Minutes)
```cron
*/5 * * * * /usr/local/bin/python3 -m vps_manager.cli sync vps 1 --pull
*/10 * * * * /usr/local/bin/python3 -m vps_manager.cli sync vps 1 --push
```

### Systemd Service
```ini
[Unit]
Description=VPS Sync Service - VPS 1
After=network.target

[Service]
Type=simple
User=vps-manager
ExecStart=/usr/local/bin/python3 -m vps_manager.cli sync vps 1
Restart=on-failure
RestartSec=60

[Install]
WantedBy=multi-user.target
```

## Troubleshooting

### Sync Fails
1. Check VPS SSH connectivity
2. Verify Git is installed on VPS
3. Check Git repository permissions
4. Review SSH key permissions

### Conflicts Not Resolving
1. Use `--force` option to overwrite
2. Resolve manually then sync
3. Review conflict details in sync history

### VPS Git Issues
1. Ensure `.openclaw` is a Git repository
2. Check `.gitignore` doesn't exclude needed files
3. Verify SSH user has write permissions

### Performance Issues
1. Large repos may take longer to sync
2. Consider sync history pruning
3. Implement diff-based sync for large repos

## Security Considerations

1. **SSH Key Protection**
   - Private keys stored securely
   - SSH keys rotated regularly
   - No password authentication

2. **Access Control**
   - Only VPS owner can sync
   - RBAC enforced on all endpoints
   - Audit logs track all syncs

3. **Data Integrity**
   - Verify commits during sync
   - Check file integrity
   - Secure conflict resolution

4. **Network Security**
   - SSH over port 22 only
   - mTLS recommended for production
   - Rate limiting on sync endpoint

## AI-Assisted Merge (Future Enhancement)

The system includes AI-assisted merge capabilities:

1. Analyze conflicting changes
2. Suggest resolution strategy
3. Apply chosen resolution
4. Document resolution

This requires integration with an LLM for intelligent conflict resolution.

---

**Note**: This feature is in active development. Feedback and issues are welcome!
