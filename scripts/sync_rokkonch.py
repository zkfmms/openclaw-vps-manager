import asyncio
import json
import sqlite3
from pathlib import Path

# パスの設定
LOCAL_DB_PATH = Path.home() / ".openclaw-vps-manager" / "tweets.db"
BACKUP_DB_PATH = Path.home() / ".openclaw-vps-manager" / "tweets_backup.db"
RKKONCH_REMOTE_BACKUP = "~/openclaw-backup-20260328.tar.gz"


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
            scraped_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Insert tweets
    imported_count = 0
    skipped_count = 0

    for tweet in tweets:
        tweet_id = tweet.get('id')
        if not tweet_id:
            continue

        content = tweet.get('content', '')
        user = tweet.get('username', '')
        created_at = tweet.get('timestamp', '')

        try:
            cursor.execute("""
                INSERT OR IGNORE INTO tweets (tweet_id, tweet_type, content, user, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (tweet_id, tweet_type, content, user, created_at))

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


async def sync_from_rkkonch():
    import subprocess
    
    print("=== rokkonch 同期開始 ===")
    from datetime import datetime
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("")
    
    # ステップ1: rokkonch の生存確認
    print("[1/5] rokkonch の生存確認...")
    try:
        result = subprocess.run(
            ["ssh", "rokkonch", "echo", "alive"],
            capture_output=True,
            timeout=10
        )
        if result.returncode == 0:
            print("     ✓ rokkonch is alive")
        else:
            print("     ✗ rokkonch is not reachable")
            print(f"     エラー: {result.stderr}")
            return False
    except Exception as e:
        print(f"     ✗ rokkonch 確証エラー: {e}")
        return False
    
    print("")
    # ステップ2: データ収集
    print("[2/5] rokkonch からツイートデータを収集...")
    
    # my_tweets.json
    print("     my_tweets.json を読み取り...")
    try:
        result = subprocess.run(
            ["ssh", "rokkonch", "cat", "~/.openclaw/workspace/my_tweets.json"],
            capture_output=True,
            timeout=30
        )
        
        if result.returncode == 0:
            my_tweets = json.loads(result.stdout)
            print(f"     ✓ {len(my_tweets)} 件のツイートを取得")
        else:
            print(f"     ✗ 読み取りエラー: {result.stderr}")
            return False
    except Exception as e:
        print(f"     ✗ 読み取りエラー: {e}")
        return False
    
    # replies_to_target.json
    print("     replies_to_target.json を読み取り...")
    try:
        result = subprocess.run(
            ["ssh", "rokkonch", "cat", "~/.openclaw/workspace/replies_to_target.json"],
            capture_output=True,
            timeout=30
        )
        
        if result.returncode == 0:
            replies = json.loads(result.stdout)
            print(f"     ✓ {len(replies)} 件のリプライを取得")
        else:
            print(f"     ✗ 読み取りエラー: {result.stderr}")
            return False
    except Exception as e:
        print(f"     ✗ 読み取りエラー: {e}")
        return False
    
    print("")
    # ステップ3: ローカル DB にインポート
    print("[3/5] データをローカル DB にインポート...")
    
    import_count = await import_tweets_to_db(LOCAL_DB_PATH, my_tweets, "my_tweet")
    replies_count = await import_tweets_to_db(LOCAL_DB_PATH, replies, "reply")
    
    print(f"     インポート済み:")
    print(f"       • my_tweets: {import_count} 件")
    print(f"       • replies: {replies_count} 件")
    print(f"       • 合計: {import_count + replies_count} 件")
    print("")
    
    # ステップ4: バックアップ
    print("[4/5] バックアップを作成...")
    
    try:
        result = subprocess.run(
            ["ssh", "rokkonch", "tar", "-czf", RKKONCH_REMOTE_BACKUP, "-C", "~/.openclaw/workspace/", "skills"],
            capture_output=True,
            timeout=60
        )

        if result.returncode == 0:
            print(f"     ✓ リモートバックアップを作成しました: {RKKONCH_REMOTE_BACKUP}")
        else:
            print(f"     ✗ バックアップ作成エラー: {result.stderr}")
            return False
    except Exception as e:
        print(f"     ✗ バックアップエラー: {e}")
        return False
    
    print("")
    print("=== 同期完了 ===")
    print(f"ローカル DB を更新しました")
    print("")
    
    return True


if __name__ == "__main__":
    asyncio.run(sync_from_rkkonch())
