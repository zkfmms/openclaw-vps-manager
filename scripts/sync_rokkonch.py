#!/usr/bin/env python3
\"\"\"
rokkonch とローカル DB を同期するスクリプト
\"\"\"
import asyncio
import json
from pathlib import Path
import sys
import os

# パスの設定
RKKONCH_BACKUP = Path.home() / "openclaw-backup-20260328.tar.gz"
LOCAL_DB_PATH = "/var/git/openclaw-configs/tweets.db"
BACKUP_DB_PATH = "/var/git/openclaw-configs/tweets_backup.db"


async def import_tweets_to_db(db_path: str, tweets: list, tweet_type: str):
    \"\"\"
ツイートを DB にインポート
    \"\"\"
    # services/git_manager.py から UnifiedTweetDB を使用
    # ここでは仮実装として簡易に実装
    
    print(f"Importing {len(tweets)} tweets (type: {tweet_type})...")
    
    for tweet in tweets:
        print(f"  - Tweet ID: {tweet.get('id')}")
    
    return len(tweets)


async def sync_from_rkkonch():
    \"\"\"
rokkonch からデータを同期
    \"\"\"
    import subprocess
    
    print("Step 1: Checking rokkonch status...")
    
    # rokkonch の生存確認
    try:
        result = subprocess.run(
            ["ssh", "rokkonch", "echo", "alive"],
            capture_output=True,
            timeout=10
        )
        if result.returncode == 0:
            print("✓ rokkonch is alive")
        else:
            print("✗ rokkonch is not reachable")
            return False
    except Exception as e:
        print(f"✗ Failed to check rokkonch: {e}")
        return False
    
    print("\nStep 2: Collecting rokkonch data...")
    
    # JSON ファイルを収集
    try:
        result = subprocess.run(
            ["ssh", "rokkonch", "cat", "~/.openclaw/workspace/my_tweets.json"],
            capture_output=True,
            timeout=30
        )
        
        if result.returncode == 0:
            my_tweets = json.loads(result.stdout)
            print(f"✓ Found {len(my_tweets)} tweets")
        else:
            print(f"✗ Failed to read tweets: {result.stderr}")
            return False
    except Exception as e:
        print(f"✗ Failed to read tweets: {e}")
        return False
    
    # リプライを収集
    try:
        result = subprocess.run(
            ["ssh", "rokkonch", "cat", "~/.openclaw/workspace/replies_to_target.json"],
            capture_output=True,
            timeout=30
        )
        
        if result.returncode == 0:
            replies = json.loads(result.stdout)
            print(f"✓ Found {len(replies)} replies")
        else:
            print(f"✗ Failed to read replies: {result.stderr}")
            return False
    except Exception as e:
        print(f"✗ Failed to read replies: {e}")
        return False
    
    print("\nStep 3: Importing to local DB...")
    
    # ローカル DB にインポート
    import_count = await import_tweets_to_db(LOCAL_DB_PATH, my_tweets, "my_tweet")
    replies_count = await import_tweets_to_db(LOCAL_DB_PATH, replies, "reply")
    
    print(f"\nImport summary:")
    print(f"  - my_tweets: {import_count}")
    print(f"  - replies: {replies_count}")
    print(f"  - Total: {import_count + replies_count}")
    
    return True


if __name__ == "__main__":
    asyncio.run(sync_from_rkkonch())
