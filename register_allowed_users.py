# -*- coding: utf-8 -*-
"""
許可するDiscordユーザーIDを、まとめてFirestoreに登録するスクリプト。
（サイト上の「👑 許可するユーザーの管理」からも1人ずつ追加できます）

使い方（環境変数 FIREBASE_CREDENTIALS_JSON に、アプリと同じ認証情報が入っている状態で）:
  python register_allowed_users.py 123456789012345678:田中 234567890123456789:佐藤
  python register_allowed_users.py --file ids.txt          # 1行に「ID」または「ID:メモ」
  python register_allowed_users.py --admin 123456789012345678:自分   # 管理者として登録
  python register_allowed_users.py --remove 234567890123456789       # 許可を削除
  python register_allowed_users.py --list                             # 登録済みの一覧
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import firebase_admin
from firebase_admin import credentials, firestore

COLLECTION = "obakyu_allowed_users"


def get_db():
    cred_json = os.environ.get("FIREBASE_CREDENTIALS_JSON", "").strip()
    if not cred_json:
        sys.exit("環境変数 FIREBASE_CREDENTIALS_JSON が設定されていません。")
    try:
        app = firebase_admin.get_app()
    except ValueError:
        app = firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
    return firestore.client(app)


def parse_entry(text: str):
    text = text.strip()
    if not text or text.startswith("#"):
        return None
    uid, _, note = text.partition(":")
    uid = uid.strip()
    if not uid.isdigit():
        print(f"スキップ（IDは数字のみ）: {text}")
        return None
    return uid, note.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("entries", nargs="*", help="ID または ID:メモ")
    parser.add_argument("--file", help="IDを1行ずつ書いたファイル")
    parser.add_argument("--admin", action="store_true", help="管理者として登録する")
    parser.add_argument("--remove", action="store_true", help="許可を削除する")
    parser.add_argument("--list", action="store_true", help="登録済みの一覧を表示する")
    args = parser.parse_args()

    db = get_db()
    col = db.collection(COLLECTION)

    if args.list:
        for doc in col.stream():
            d = doc.to_dict() or {}
            print(f"{doc.id}\t{d.get('role', 'user')}\t{d.get('note', '')}")
        return

    entries = list(args.entries)
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            entries += f.read().splitlines()

    count = 0
    for raw in entries:
        parsed = parse_entry(raw)
        if not parsed:
            continue
        uid, note = parsed
        if args.remove:
            col.document(uid).delete()
            print(f"削除: {uid}")
        else:
            col.document(uid).set(
                {
                    "note": note,
                    "role": "admin" if args.admin else "user",
                    "added_by": "script",
                    "added_at": datetime.now(timezone.utc),
                }
            )
            print(f"登録: {uid} {note} {'(管理者)' if args.admin else ''}")
        count += 1
    print(f"{count}件を処理しました。")


if __name__ == "__main__":
    main()
