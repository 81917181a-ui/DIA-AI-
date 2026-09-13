# -*- coding: utf-8 -*-
"""
鉄道ダイヤ作成AIアプリ（尾羽急本線）

- 画面最下部に固定された入力バー（st.chat_input）、プレースホルダーは「こんにちは！」
- セッション管理とタイムスタンプにより、ブラウザを開いてから最長6時間チャット履歴を保持
- Gemini APIを使ってダイヤ（運行計画）作成を支援
"""

import os
import json
import sqlite3
import uuid
import time
import threading
import urllib.request
from datetime import datetime, timezone

import streamlit as st
import pandas as pd
import google.generativeai as genai

from stations_data import build_line_context_text, SERVICE_TYPES

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
SESSION_TTL_SECONDS = 6 * 60 * 60  # 6時間
DB_PATH = os.path.join(os.path.dirname(__file__), "sessions.db")
MODEL_NAME = "gemini-2.0-flash"

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
# セッション（SQLite）まわり
# ---------------------------------------------------------------------------
def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            messages TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def load_session(conn: sqlite3.Connection, session_id: str):
    row = conn.execute(
        "SELECT created_at, updated_at, messages FROM sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    created_at, updated_at, messages_json = row
    now = time.time()
    if now - created_at > SESSION_TTL_SECONDS:
        # 6時間経過したセッションは破棄する
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()
        return None
    return {
        "created_at": created_at,
        "updated_at": updated_at,
        "messages": json.loads(messages_json),
    }


def save_session(conn: sqlite3.Connection, session_id: str, created_at: float, messages: list):
    conn.execute(
        """
        INSERT INTO sessions (session_id, created_at, updated_at, messages)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            updated_at = excluded.updated_at,
            messages = excluded.messages
        """,
        (session_id, created_at, time.time(), json.dumps(messages, ensure_ascii=False)),
    )
    conn.commit()


def cleanup_expired_sessions(conn: sqlite3.Connection):
    cutoff = time.time() - SESSION_TTL_SECONDS
    conn.execute("DELETE FROM sessions WHERE created_at < ?", (cutoff,))
    conn.commit()


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

    conn = get_db_connection()
    cleanup_expired_sessions(conn)

    # --- セッションID（URLクエリパラメータで維持し、ブラウザを開き直しても6時間以内なら復元）---
    query_params = st.query_params
    session_id = query_params.get("sid")
    if not session_id:
        session_id = str(uuid.uuid4())
        st.query_params["sid"] = session_id

    if "messages" not in st.session_state:
        existing = load_session(conn, session_id)
        if existing:
            st.session_state["messages"] = existing["messages"]
            st.session_state["created_at"] = existing["created_at"]
        else:
            st.session_state["messages"] = []
            st.session_state["created_at"] = time.time()

    st.title("🚃 尾羽急本線 ダイヤ作成AI")
    st.caption(
        "路線データ（駅設備・停車種別・駅間所要時分）をもとに、ダイヤ作成を支援します。"
        "チャット履歴はブラウザを開いてから最長6時間保持されます。"
    )

    if not get_gemini_api_keys():
        st.warning(
            "GEMINI_API_KEY_1〜GEMINI_API_KEY_5 が1つも設定されていません。"
            "Render の環境変数に少なくとも1つ設定してください。"
        )

    # --- これまでの会話を表示 ---
    for msg in st.session_state["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # --- 入力バー（画面最下部に固定・プレースホルダー「こんにちは！」）---
    user_input = st.chat_input(placeholder="こんにちは！")

    if user_input:
        st.session_state["messages"].append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            if not get_gemini_api_keys():
                reply = "GEMINI_API_KEY_1〜5 が未設定のため応答できません。"
                st.markdown(reply)
            else:
                with st.spinner("ダイヤを検討しています..."):
                    try:
                        reply = call_gemini_with_failover(
                            st.session_state["messages"][:-1],
                            user_input,
                        )
                    except Exception as e:
                        reply = f"エラーが発生しました: {e}"
                st.markdown(reply)

        st.session_state["messages"].append({"role": "assistant", "content": reply})
        save_session(
            conn,
            session_id,
            st.session_state["created_at"],
            st.session_state["messages"],
        )

    # --- サイドバー：路線データの確認・リセット ---
    with st.sidebar:
        st.subheader("路線データ")
        st.write(f"運行種別: {', '.join(SERVICE_TYPES)}")

        keys = get_gemini_api_keys()
        if keys:
            slot = _current_key_slot % len(keys)
            st.caption(f"登録済みAPIキー: {len(keys)}個 / 使用中: {keys[slot][0]}")
        else:
            st.caption("登録済みAPIキー: 0個")

        if st.button("チャット履歴をリセット"):
            st.session_state["messages"] = []
            st.session_state["created_at"] = time.time()
            save_session(conn, session_id, st.session_state["created_at"], [])
            st.rerun()

        remaining = SESSION_TTL_SECONDS - (time.time() - st.session_state["created_at"])
        remaining_h = max(0, remaining) / 3600
        st.caption(f"このセッションの残り保持時間: 約{remaining_h:.1f}時間")


if __name__ == "__main__":
    main()
