#!/usr/bin/env python3
"""
Generic VPS synchronization script for OpenClaw data.
This script can sync tweet data and workspace files from any VPS instance.
"""
import asyncio
import json
import sqlite3
from pathlib import Path
from datetime import datetime
import subprocess
import argparse
import sys

# Default paths (can be overridden via command line)
DEFAULT_DB_PATH = Path.home() / ".openclaw-vps-manager" / "tweets.db"
DEFAULT_REMOTE_BACKUP = "~/openclaw-backup-{timestamp}.tar.gz"


async def import_tweets_to_db(db_path: str, tweets: list, tweet_type: str):
    """Import tweets to SQLite database."""
    print(f"Importing {len(tweets)} tweets (type: {tweet_type})...")

    if not tweets:
        print("  No tweets to import")
        return 0

    # Ensure database directory exists
    db_path_obj = Path(db_path)
    db_path_obj.parent.mkdir(parents=True, exist_ok=True)

    # Connect to database
    conn = sqlite3.connect(str(db_path_obj))
    cursor = conn.cursor()

    # Create table if not exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tweets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tweet_id TEXT UNIQUE,
            tweet_type TEXT NOT NULL,
            content TEXT,
            user TEXT,
            created_at TEXT,
            scraped_at TEXT DEFAULT CURRENT_TIMESTAMP,
            source TEXT
        )
    """)

    # Insert tweets
    imported_count = 0
    skipped_count = 0

    for tweet in tweets:
        tweet_id = tweet.get('id')
        if not tweet_id:
            continue

        content = tweet.get('content', '') or tweet.get('text', '')
        user = tweet.get('username', '') or tweet.get('user', '')
        created_at = tweet.get('timestamp', '') or tweet.get('created_at', '')

        try:
            cursor.execute("""
                INSERT OR IGNORE INTO tweets (tweet_id, tweet_type, content, user, created_at, source)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (tweet_id, tweet_type, content, user, created_at, tweet_type))

            if cursor.rowcount > 0:
                imported_count += 1
                if imported_count % 100 == 0:
                    print(f"  Progress: {imported_count} tweets imported")
            else:
                skipped_count += 1
        except sqlite3.Error as e:
            print(f"  Error importing tweet {tweet_id}: {e}")
            continue

    conn.commit()
    conn.close()

    print(f"  ✓ {imported_count} tweets imported, {skipped_count} skipped (duplicates)")
    return imported_count


async def check_vps_alive(hostname: str) -> bool:
    """Check if VPS is reachable via SSH."""
    print(f"[1/5] {hostname} の生存確認...")
    try:
        result = subprocess.run(
            ["ssh", hostname, "echo", "alive"],
            capture_output=True,
            timeout=10
        )
        if result.returncode == 0:
            print("     ✓ VPS is alive")
            return True
        else:
            print("     ✗ VPS is not reachable")
            print(f"     エラー: {result.stderr}")
            return False
    except Exception as e:
        print(f"     ✗ VPS 確認エラー: {e}")
        return False


async def collect_tweet_data(hostname: str, workspace_dir: str = "~/.openclaw/workspace"):
    """Collect tweet data from VPS."""
    print(f"[2/5] {hostname} からツイートデータを収集...")

    tweet_files = {
        "my_tweets.json": "my_tweet",
        "replies_to_target.json": "reply",
        "search_results.json": "search_result"
    }

    all_tweets = []

    for filename, tweet_type in tweet_files.items():
        remote_path = f"{workspace_dir}/{filename}"
        print(f"     {filename} を読み取り...")

        try:
            result = subprocess.run(
                ["ssh", hostname, "cat", remote_path],
                capture_output=True,
                timeout=30
            )

            if result.returncode == 0:
                tweets = json.loads(result.stdout)
                print(f"     ✓ {len(tweets)} 件の {tweet_type} を取得")
                all_tweets.extend(tweets)
            else:
                print(f"     ✗ {filename} 読み取りエラー: {result.stderr}")
        except FileNotFoundError:
            print(f"     ⚠️ {filename} は存在しません (スキップ)")
        except Exception as e:
            print(f"     ✗ {filename} 読み取りエラー: {e}")

    return all_tweets


async def backup_skills(hostname: str, backup_path: str, workspace_dir: str = "~/.openclaw/workspace"):
    """Create backup of skills directory on VPS."""
    print(f"[4/5] バックアップを作成...")

    try:
        result = subprocess.run(
            ["ssh", hostname, "tar", "-czf", backup_path, "-C", workspace_dir, "skills"],
            capture_output=True,
            timeout=60
        )

        if result.returncode == 0:
            print(f"     ✓ リモートバックアップを作成しました: {backup_path}")
            return True
        else:
            print(f"     ✗ バックアップ作成エラー: {result.stderr}")
            return False
    except Exception as e:
        print(f"     ✗ バックアップエラー: {e}")
        return False


async def sync_from_vps(
    hostname: str,
    db_path: str = None,
    backup: bool = True,
    workspace_dir: str = "~/.openclaw/workspace"
):
    """
    Sync OpenClaw data from VPS instance.

    Args:
        hostname: VPS hostname (as configured in SSH config)
        db_path: Local database path (default: ~/.openclaw-vps-manager/tweets.db)
        backup: Create backup of skills directory (default: True)
        workspace_dir: Remote workspace directory (default: ~/.openclaw/workspace)
    """
    if db_path is None:
        db_path = str(DEFAULT_DB_PATH)

    print(f"=== VPS 同期開始: {hostname} ===")
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"ローカル DB: {db_path}")
    print("")

    # Step 1: Check VPS is alive
    if not await check_vps_alive(hostname):
        return False

    print("")

    # Step 2: Collect tweet data
    all_tweets = await collect_tweet_data(hostname, workspace_dir)

    if not all_tweets:
        print("⚠️ ツイートデータが見つかりませんでした")
        return False

    print("")

    # Step 3: Import to local database
    print(f"[3/5] データをローカル DB にインポート...")

    # Import by type
    import_count = 0
    tweet_types = set()

    for tweet in all_tweets:
        tweet_type = "unknown"
        if 'id' in tweet:
            # Try to determine type from filename context
            tweet_types.add(tweet_type)

    # Import all tweets
    import_count = await import_tweets_to_db(db_path, all_tweets, "sync")

    print("")
    print(f"     インポート済み:")
    print(f"       • 合計: {import_count} 件")
    print(f"       • ユニークツイートタイプ: {len(tweet_types)}")
    print("")

    # Step 4: Backup
    if backup:
        timestamp = datetime.now().strftime("%Y%m%d")
        remote_backup = DEFAULT_REMOTE_BACKUP.format(timestamp=timestamp)
        if not await backup_skills(hostname, remote_backup, workspace_dir):
            return False

    print("")
    print("=== 同期完了 ===")
    print(f"ローカル DB を更新しました: {db_path}")
    print("")

    return True


def main():
    """Main entry point with command line arguments."""
    parser = argparse.ArgumentParser(
        description="Sync OpenClaw data from VPS instance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Sync from rokkonch (default settings)
  python3 sync_vps.py rokkonch

  # Sync without backup
  python3 sync_vps.py rokkonch --no-backup

  # Specify custom database path
  python3 sync_vps.py rokkonch --db-path /custom/path/tweets.db

  # Sync from custom VPS
  python3 sync_vps.py user@vps.example.com --workspace-dir /path/to/workspace
        """
    )

    parser.add_argument(
        "hostname",
        help="VPS hostname (as configured in SSH config)"
    )

    parser.add_argument(
        "--db-path",
        help=f"Local database path (default: {DEFAULT_DB_PATH})",
        default=str(DEFAULT_DB_PATH)
    )

    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip creating backup of skills directory"
    )

    parser.add_argument(
        "--workspace-dir",
        default="~/.openclaw/workspace",
        help="Remote workspace directory (default: ~/.openclaw/workspace)"
    )

    args = parser.parse_args()

    # Run sync
    success = asyncio.run(sync_from_vps(
        hostname=args.hostname,
        db_path=args.db_path,
        backup=not args.no_backup,
        workspace_dir=args.workspace_dir
    ))

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()