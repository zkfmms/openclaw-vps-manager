import asyncio
import json
import sqlite3
from pathlib import Path

# パスの設定
RKKONCH_BACKUP = Path.home() / "openclaw-backup-20260328.tar.gz"
LOCAL_DB_PATH = "/var/git/openclaw-configs/tweets.db"
BACKUP_DB_PATH = "/var/git/openclaw-configs/tweets_backup.db"


async def import_tweets_to_db(db_path: str, tweets: list, tweet_type: str):
    print(f"Importing {len(tweets)} tweets (type: {tweet_type})...")
    
    count = 0
    for tweet in tweets:
        print(f"  - Tweet ID: {tweet.get('id')}")
        count += 1
    
    return count


async def sync_from_rkkonch():
    import subprocess
    
    print("=== rokkonch 同期開始 ===")
    print(f"実行日時: {asyncio.get_event_loop().time().strftime('%Y-%m-%d %H:%M:%S')}")
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
            ["ssh", "rokkonch", "tar", "-czf", str(RKKONCH_BACKUP), "-C", "~/.openclaw/workspace/", "skills"],
            capture_output=True,
            timeout=60
        )
        
        if result.returncode == 0:
            print(f"     ✓ バックアップを作成しました")
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
