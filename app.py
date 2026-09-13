# -*- coding: utf-8 -*-
"""
鉄道ダイヤ作成AIアプリ（尾羽急本線）

- 画面最下部に固定された入力バー（st.chat_input）、プレースホルダーは「こんにちは！」
- セッション管理とタイムスタンプにより、ブラウザを開いてから最長6時間チャット履歴を保持
- Gemini APIを使ってダイヤ（運行計画）作成を支援
"""

import os
import json
import uuid
import time
import threading
import urllib.request
from datetime import datetime, timedelta, timezone

import streamlit as st
import pandas as pd
import google.generativeai as genai
import firebase_admin
from firebase_admin import credentials, firestore

from stations_data import build_line_context_text, SERVICE_TYPES

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60  # 7日間
MODEL_NAME = "gemini-3.6-flash"

# Renderの自動スリープ防止用（10分ごとに自分自身へアクセスする）
KEEP_ALIVE_INTERVAL_SECONDS = 10 * 60  # 10分
KEEP_ALIVE_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://dia-ai-y9bz.onrender.com")

SYSTEM_PROMPT_TEMPLATE = """あなたは鉄道ダイヤ（運行計画）作成を支援するAIアシスタントです。
以下の路線データをもとに、ユーザーの要望に応じたダイヤ案・時刻表・運行パターンの
提案や質問への回答を行ってください。

# 制約条件・注意事項
- 各駅の設備（線路数・折り返し可否・留置線・車庫の有無）を必ず考慮すること。
- 各駅の停車種別（どの種別がその駅に停まるか）を厳守すること。
- 駅間所要時分（秒）をもとに、現実的な時刻を計算すること。
- ダイヤを提示する際は、可能であれば駅名・時刻・種別を含む表形式（Markdownテーブル）で示すこと。
- 不明な点や前提条件が不足している場合は、仮定をおいたうえで明示すること。

{line_context}
"""


# ---------------------------------------------------------------------------
# セッション・チャット履歴（Cloud Firestore）まわり
# ---------------------------------------------------------------------------
DEFAULT_TITLE = "新しいチャット"
SESSIONS_COLLECTION = "obakyu_sessions"
CONVERSATIONS_COLLECTION = "obakyu_conversations"

_firebase_lock = threading.Lock()
_firestore_client = None


def get_firestore_client():
    """
    環境変数 FIREBASE_CREDENTIALS_JSON（サービスアカウントJSONの中身を1行文字列にしたもの）
    からFirestoreクライアントを初期化して返す。未設定ならNoneを返す。
    """
    global _firestore_client
    with _firebase_lock:
        if _firestore_client is not None:
            return _firestore_client

        cred_json = os.environ.get("FIREBASE_CREDENTIALS_JSON", "").strip()
        if not cred_json:
            return None

        if not firebase_admin._apps:
            cred_dict = json.loads(cred_json)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)

        _firestore_client = firestore.client()
        return _firestore_client


def ensure_session(db, session_id: str):
    """
    セッションがなければ作成する。
    戻り値: (created_at: float, expires_at: datetime) のタプル。
    """
    doc_ref = db.collection(SESSIONS_COLLECTION).document(session_id)
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        return data["created_at"], data["expires_at"]

    now = time.time()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=SESSION_TTL_SECONDS)
    doc_ref.set({"created_at": now, "expires_at": expires_at})
    return now, expires_at


def cleanup_expired(db):
    """作成から6時間を過ぎたセッションと、そのセッションに属するチャットを削除する。"""
    now_dt = datetime.now(timezone.utc)
    expired_docs = list(
        db.collection(SESSIONS_COLLECTION).where("expires_at", "<", now_dt).stream()
    )
    for doc in expired_docs:
        session_id = doc.id
        convs = db.collection(CONVERSATIONS_COLLECTION).where(
            "session_id", "==", session_id
        ).stream()
        for c in convs:
            c.reference.delete()
        doc.reference.delete()


def load_conversations(db, session_id: str) -> list:
    docs = db.collection(CONVERSATIONS_COLLECTION).where(
        "session_id", "==", session_id
    ).stream()
    result = []
    for d in docs:
        data = d.to_dict()
        result.append(
            {
                "conversation_id": d.id,
                "title": data.get("title", DEFAULT_TITLE),
                "created_at": data.get("created_at", 0),
                "updated_at": data.get("updated_at", 0),
            }
        )
    result.sort(key=lambda c: c["updated_at"], reverse=True)
    return result


def create_conversation(db, session_id: str, expires_at, title: str = DEFAULT_TITLE) -> str:
    now = time.time()
    doc_ref = db.collection(CONVERSATIONS_COLLECTION).document()
    doc_ref.set(
        {
            "session_id": session_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "expires_at": expires_at,
            "messages": [],
        }
    )
    return doc_ref.id


def load_conversation_messages(db, conversation_id: str) -> list:
    doc = db.collection(CONVERSATIONS_COLLECTION).document(conversation_id).get()
    if not doc.exists:
        return []
    return doc.to_dict().get("messages", [])


def save_conversation_messages(db, conversation_id: str, messages: list):
    db.collection(CONVERSATIONS_COLLECTION).document(conversation_id).update(
        {"messages": messages, "updated_at": time.time()}
    )


def rename_conversation(db, conversation_id: str, new_title: str):
    new_title = new_title.strip() or DEFAULT_TITLE
    db.collection(CONVERSATIONS_COLLECTION).document(conversation_id).update(
        {"title": new_title}
    )


# ---------------------------------------------------------------------------
# スリープ防止（10分ごとに自分自身へアクセス）
# ---------------------------------------------------------------------------
_keep_alive_started = False
_keep_alive_lock = threading.Lock()


def _keep_alive_loop():
    while True:
        time.sleep(KEEP_ALIVE_INTERVAL_SECONDS)
        try:
            urllib.request.urlopen(KEEP_ALIVE_URL, timeout=10)
        except Exception:
            # 起動直後やネットワーク一時エラーは無視して継続する
            pass


def start_keep_alive_thread():
    """アプリプロセスにつき1本だけ、自己アクセス用のバックグラウンドスレッドを起動する。"""
    global _keep_alive_started
    with _keep_alive_lock:
        if _keep_alive_started:
            return
        thread = threading.Thread(target=_keep_alive_loop, daemon=True)
        thread.start()
        _keep_alive_started = True


# ---------------------------------------------------------------------------
# Gemini APIキーのフェイルオーバー ＋ Discord通知
# ---------------------------------------------------------------------------
GEMINI_KEY_ENV_VARS = [f"GEMINI_API_KEY_{i}" for i in range(1, 6)]  # GEMINI_API_KEY_1〜5
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

_gemini_key_lock = threading.Lock()
_current_key_slot = 0  # 現在使用中のキーの並び順インデックス


def get_gemini_api_keys() -> list:
    """Renderの環境変数 GEMINI_API_KEY_1〜5 のうち、設定済みのものだけを取得する。"""
    keys = []
    for env_name in GEMINI_KEY_ENV_VARS:
        value = os.environ.get(env_name, "").strip()
        if value:
            keys.append((env_name, value))
    return keys


def notify_discord(message: str):
    """DiscordのWebhookへ通知を送る（DISCORD_WEBHOOK_URL未設定なら何もしない）。"""
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        payload = json.dumps({"content": message}).encode("utf-8")
        req = urllib.request.Request(
            DISCORD_WEBHOOK_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        # 通知自体の失敗でアプリを止めない
        pass


def _build_model(api_key: str):
    genai.configure(api_key=api_key)
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(line_context=build_line_context_text())
    return genai.GenerativeModel(MODEL_NAME, system_instruction=system_prompt)


def call_gemini_with_failover(history: list, user_message: str) -> str:
    """
    GEMINI_API_KEY_1〜5を順番に試し、エラーが出たキーはスキップして
    次のキーに自動で切り替える。切り替え発生時・全滅時はDiscordへ通知する。
    """
    global _current_key_slot

    keys = get_gemini_api_keys()
    if not keys:
        return "GEMINI_API_KEY_1〜5 のいずれも設定されていません。"

    gemini_history = []
    for m in history:
        role = "user" if m["role"] == "user" else "model"
        gemini_history.append({"role": role, "parts": [m["content"]]})

    with _gemini_key_lock:
        start_slot = _current_key_slot % len(keys)

    last_error = None
    for offset in range(len(keys)):
        slot = (start_slot + offset) % len(keys)
        env_name, api_key = keys[slot]
        try:
            model = _build_model(api_key)
            chat = model.start_chat(history=gemini_history)
            response = chat.send_message(user_message)

            with _gemini_key_lock:
                if slot != _current_key_slot:
                    _current_key_slot = slot
                    notify_discord(
                        f"⚠️ Gemini APIキーを切り替えました。現在使用中: **{env_name}**"
                    )

            return response.text

        except Exception as e:
            last_error = e
            notify_discord(
                f"🔴 **{env_name}** でエラーが発生しました。次のAPIキーに切り替えます。\n"
                f"エラー内容: {e}"
            )
            continue

    notify_discord("🔴🔴 登録済みのGemini APIキーが全て利用できませんでした。")
    return f"登録済みのAPIキーすべてでエラーが発生しました。最後のエラー: {last_error}"


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------
def main():
    st.set_page_config(page_title="尾羽急本線 ダイヤ作成AI", page_icon="🚃", layout="wide")

    start_keep_alive_thread()

    db = get_firestore_client()
    if db is None:
        st.error(
            "FIREBASE_CREDENTIALS_JSON が設定されていません。"
            "Renderの環境変数にFirebaseサービスアカウントの認証情報（JSON）を設定してください。"
        )
        return

    cleanup_expired(db)

    # --- セッションID（URLクエリパラメータで維持し、ブラウザを開き直しても6時間以内なら復元）---
    query_params = st.query_params
    session_id = query_params.get("sid")
    if not session_id:
        session_id = str(uuid.uuid4())
        st.query_params["sid"] = session_id

    _, session_expires_at = ensure_session(db, session_id)
    conversations = load_conversations(db, session_id)

    # 現在選択中のチャットがなければ、既存の最新チャット or 新規チャットを選択
    if "current_conversation_id" not in st.session_state or not any(
        c["conversation_id"] == st.session_state["current_conversation_id"] for c in conversations
    ):
        if conversations:
            st.session_state["current_conversation_id"] = conversations[0]["conversation_id"]
        else:
            new_id = create_conversation(db, session_id, session_expires_at)
            st.session_state["current_conversation_id"] = new_id
            conversations = load_conversations(db, session_id)

    current_id = st.session_state["current_conversation_id"]

    # --- サイドバー：チャット一覧（新規作成・切り替え・名前変更） ---
    with st.sidebar:
        if st.button("＋ 新しいチャット", use_container_width=True):
            new_id = create_conversation(db, session_id, session_expires_at)
            st.session_state["current_conversation_id"] = new_id
            st.rerun()

        st.divider()

        for conv in conversations:
            if st.button(conv["title"], key=f"select_{conv['conversation_id']}", use_container_width=True):
                st.session_state["current_conversation_id"] = conv["conversation_id"]
                st.rerun()

        st.divider()
        current_conv = next((c for c in conversations if c["conversation_id"] == current_id), None)
        if current_conv:
            new_title = st.text_input(
                "チャット名を変更",
                value=current_conv["title"],
                key=f"rename_{current_id}",
            )
            if new_title.strip() and new_title.strip() != current_conv["title"]:
                rename_conversation(db, current_id, new_title)
                st.rerun()

    if not get_gemini_api_keys():
        st.warning(
            "GEMINI_API_KEY_1〜GEMINI_API_KEY_5 が1つも設定されていません。"
            "Render の環境変数に少なくとも1つ設定してください。"
        )

    # --- これまでの会話を表示 ---
    messages = load_conversation_messages(db, current_id)
    for msg in messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # --- 入力バー（画面最下部に固定・プレースホルダー「こんにちは！」）---
    user_input = st.chat_input(placeholder="こんにちは！")

    if user_input:
        messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            if not get_gemini_api_keys():
                reply = "GEMINI_API_KEY_1〜5 が未設定のため応答できません。"
                st.markdown(reply)
            else:
                with st.spinner("ダイヤを検討しています..."):
                    try:
                        reply = call_gemini_with_failover(messages[:-1], user_input)
                    except Exception as e:
                        reply = f"エラーが発生しました: {e}"
                st.markdown(reply)

        messages.append({"role": "assistant", "content": reply})
        save_conversation_messages(db, current_id, messages)

        # 最初のやり取りの場合、チャット名をユーザーの発言から自動でつける
        if current_conv and current_conv["title"] == DEFAULT_TITLE and len(messages) <= 2:
            auto_title = user_input.strip()[:20] or DEFAULT_TITLE
            rename_conversation(db, current_id, auto_title)

        st.rerun()


if __name__ == "__main__":
    main()
