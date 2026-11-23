# -*- coding: utf-8 -*-
"""
Discordアカウントでのログイン（OAuth2）と、許可したユーザーだけを通す仕組み。BOTは不要。

流れ:
  1. 未ログインのときは「Discordでログイン」ボタンだけを出す。
  2. Discordで連携を許可すると、このサイトに戻ってくる（?code=...&state=...）。
  3. DiscordのユーザーID・ユーザー名を取得し、Firestoreの許可リストに入っている人だけ通す。
  4. ログイン成功・拒否・アクセスは、ユーザー名・ID・IP・ブラウザ情報つきでWebhookに送る。

必要な環境変数（Render）:
  DISCORD_CLIENT_ID      DiscordのDeveloper Portalで作ったApplicationのClient ID
  DISCORD_CLIENT_SECRET  同じ画面のClient Secret
  DISCORD_REDIRECT_URI   このサイトのURL（Developer PortalのOAuth2 > Redirectsにも同じものを登録）
  ADMIN_DISCORD_IDS      管理者のDiscord ID（カンマ区切り）。常に許可され、画面から許可リストを編集できる
  ALLOWED_DISCORD_IDS    （任意）最初から許可するDiscord ID（カンマ区切り）
  LOGIN_WEBHOOK_URL      （任意）アクセス履歴の送り先。未設定なら QUESTION_WEBHOOK_URL → DISCORD_WEBHOOK_URL
  OAUTH_STATE_SECRET     （任意）ログインの署名用の秘密の文字列。未設定ならClient Secretを使う
  AUTH_REQUIRED          true にすると、上の設定が足りないときはサイトを開けなくする（既定は設定が無ければ認証なし）

許可リストはFirestoreのコレクション obakyu_allowed_users に、ドキュメントID＝DiscordのユーザーIDで保存する。
"""
import hashlib
import hmac
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import streamlit as st

CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET", "").strip()
REDIRECT_URI = os.environ.get("DISCORD_REDIRECT_URI", "").strip()
STATE_SECRET = os.environ.get("OAUTH_STATE_SECRET", "").strip() or CLIENT_SECRET
AUTH_REQUIRED = os.environ.get("AUTH_REQUIRED", "").strip().lower() in ("1", "true", "yes", "on")

ALLOWED_COLLECTION = "obakyu_allowed_users"
AUTH_COLLECTION = "obakyu_auth"
AUTH_TTL_SECONDS = 7 * 24 * 60 * 60
STATE_MAX_AGE_SECONDS = 10 * 60
ALLOWED_CACHE_SECONDS = 60

JST = timezone(timedelta(hours=9))
DISCORD_API = "https://discord.com/api"
USER_AGENT = "DiscordBot (https://obakyu-dia-ai, 1.0)"


def _parse_ids(text: str) -> list:
    ids = []
    for part in (text or "").replace("\n", ",").replace(" ", ",").split(","):
        part = part.strip()
        if part.isdigit() and part not in ids:
            ids.append(part)
    return ids


ADMIN_IDS = _parse_ids(os.environ.get("ADMIN_DISCORD_IDS", ""))
INITIAL_ALLOWED_IDS = _parse_ids(os.environ.get("ALLOWED_DISCORD_IDS", ""))


def _webhook_url() -> str:
    return (
        os.environ.get("LOGIN_WEBHOOK_URL", "").strip()
        or os.environ.get("QUESTION_WEBHOOK_URL", "").strip()
        or os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    )


def auth_enabled() -> bool:
    return bool(CLIENT_ID and CLIENT_SECRET and REDIRECT_URI)


def now_jst_str() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")


# ---------------------------------------------------------------------------
# Webhook（アクセス履歴）
# ---------------------------------------------------------------------------
def _post_webhook(url: str, content: str):
    try:
        payload = json.dumps({"content": content[:1900], "allowed_mentions": {"parse": []}}).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload, method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "obakyu-dia-ai/1.0"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"[auth] ウェブフックへの送信に失敗しました: {type(e).__name__}: {e}", flush=True)


def _clean(text, limit=200) -> str:
    text = str(text or "").replace("`", "'").replace("\n", " ").strip()
    return text[:limit]


def user_label(user: dict) -> str:
    if not user or not user.get("id"):
        return "未ログイン"
    name = user.get("display") or user.get("username") or ""
    uname = f" (@{user['username']})" if user.get("username") and user.get("username") != name else ""
    return f"{name}{uname} / ID {user['id']}"


def send_event(kind: str, user: dict, ip: str, session_id: str, extra: str = ""):
    """ログイン成功・拒否・アクセスなどを、時刻（日本時間）・ユーザー・IPつきでWebhookとログに残す。"""
    try:
        headers = st.context.headers
        ua = headers.get("User-Agent", "")
        lang = headers.get("Accept-Language", "")
    except Exception:
        ua, lang = "", ""
    lines = [
        f"{kind} {now_jst_str()}",
        f"ユーザー: {_clean(user.get('display') or '-')} (@{_clean(user.get('username') or '-')})",
        f"ID: `{_clean(user.get('id') or '-')}`",
        f"IP: `{_clean(ip)}`",
        f"ブラウザ: `{_clean(ua, 160)}`",
        f"言語: `{_clean(lang, 40)}` / セッション: `{_clean(session_id)[:8]}`",
    ]
    if extra:
        lines.append(extra)
    message = "\n".join(lines)
    print(f"[auth] {kind} id={user.get('id') or '-'} user={user.get('username') or '-'} ip={ip} sid={session_id[:8]}", flush=True)
    url = _webhook_url()
    if url:
        threading.Thread(target=_post_webhook, args=(url, message), daemon=True).start()


# ---------------------------------------------------------------------------
# 署名つきstate（ログイン画面に戻ってきたときの正当性確認。セッションを失っても検証できる）
# ---------------------------------------------------------------------------
def _sign(payload: str) -> str:
    return hmac.new(STATE_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def make_state(session_id: str) -> str:
    payload = f"{session_id}.{int(time.time())}"
    return f"{payload}.{_sign(payload)}"


def parse_state(state: str):
    """正しければ session_id を返す。偽造・期限切れならNone。"""
    try:
        session_id, ts, sig = state.rsplit(".", 2)
        if not hmac.compare_digest(sig, _sign(f"{session_id}.{ts}")):
            return None
        if time.time() - int(ts) > STATE_MAX_AGE_SECONDS or int(ts) > time.time() + 60:
            return None
        return session_id
    except Exception:
        return None


def authorize_url(session_id: str) -> str:
    query = urllib.parse.urlencode(
        {
            "client_id": CLIENT_ID,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": "identify",
            "state": make_state(session_id),
            "prompt": "none",
        }
    )
    return f"https://discord.com/oauth2/authorize?{query}"


def _http_json(url: str, data: dict = None, headers: dict = None):
    body = urllib.parse.urlencode(data).encode("utf-8") if data is not None else None
    all_headers = {"User-Agent": USER_AGENT}
    if body is not None:
        all_headers["Content-Type"] = "application/x-www-form-urlencoded"
    all_headers.update(headers or {})
    req = urllib.request.Request(url, data=body, headers=all_headers, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_discord_user(code: str) -> dict:
    """認可コードをアクセストークンに換えて、Discordのユーザー情報（ID・ユーザー名・表示名）を取得する。"""
    token = _http_json(
        f"{DISCORD_API}/oauth2/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
    )
    me = _http_json(f"{DISCORD_API}/users/@me", headers={"Authorization": f"Bearer {token['access_token']}"})
    return {
        "id": str(me.get("id", "")),
        "username": me.get("username", ""),
        "display": me.get("global_name") or me.get("username", ""),
    }


# ---------------------------------------------------------------------------
# 許可リスト（Firestore）
# ---------------------------------------------------------------------------
@st.cache_data(ttl=ALLOWED_CACHE_SECONDS, show_spinner=False)
def _load_allowed(_db) -> dict:
    allowed = {uid: {"note": "環境変数 ALLOWED_DISCORD_IDS", "role": "user"} for uid in INITIAL_ALLOWED_IDS}
    try:
        for doc in _db.collection(ALLOWED_COLLECTION).stream():
            data = doc.to_dict() or {}
            allowed[doc.id] = {"note": data.get("note", ""), "role": data.get("role", "user")}
    except Exception as e:
        print(f"[auth] 許可リストの読み込みに失敗しました: {type(e).__name__}: {e}", flush=True)
    for uid in ADMIN_IDS:
        allowed[uid] = {"note": allowed.get(uid, {}).get("note") or "管理者（環境変数）", "role": "admin"}
    return allowed


def clear_allowed_cache():
    _load_allowed.clear()


def is_allowed(db, discord_id: str) -> bool:
    return bool(discord_id) and discord_id in _load_allowed(db)


def is_admin(db, discord_id: str) -> bool:
    return bool(discord_id) and _load_allowed(db).get(discord_id, {}).get("role") == "admin"


def add_allowed(db, discord_id: str, note: str = "", added_by: str = "", role: str = "user"):
    db.collection(ALLOWED_COLLECTION).document(str(discord_id)).set(
        {
            "note": note,
            "role": role,
            "added_by": added_by,
            "added_at": datetime.now(timezone.utc),
        }
    )
    clear_allowed_cache()


def remove_allowed(db, discord_id: str):
    db.collection(ALLOWED_COLLECTION).document(str(discord_id)).delete()
    clear_allowed_cache()


# ---------------------------------------------------------------------------
# ログイン状態の保存（ブラウザを再読み込みしても、同じsidなら期限内はログインしたまま）
# ---------------------------------------------------------------------------
def _save_login(db, session_id: str, user: dict):
    now = datetime.now(timezone.utc)
    db.collection(AUTH_COLLECTION).document(session_id).set(
        {
            "discord_id": user["id"],
            "username": user["username"],
            "display": user["display"],
            "created_at": now,
            "expires_at": now + timedelta(seconds=AUTH_TTL_SECONDS),
        }
    )


def _load_login(db, session_id: str):
    try:
        doc = db.collection(AUTH_COLLECTION).document(session_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        expires = data.get("expires_at")
        if expires is not None and expires < datetime.now(timezone.utc):
            return None
        return {"id": data.get("discord_id", ""), "username": data.get("username", ""), "display": data.get("display", "")}
    except Exception as e:
        print(f"[auth] ログイン状態の読み込みに失敗しました: {type(e).__name__}: {e}", flush=True)
        return None


def logout(db, session_id: str):
    try:
        db.collection(AUTH_COLLECTION).document(session_id).delete()
    except Exception:
        pass
    st.session_state.pop("auth_user", None)


# ---------------------------------------------------------------------------
# 画面
# ---------------------------------------------------------------------------
def _show_login_page(session_id: str, message: str = ""):
    st.title("🚃 鉄道ダイヤ作成専門AI")
    st.write("このサイトは、許可されたDiscordアカウントのかただけがご利用いただけます。")
    if message:
        st.warning(message)
    st.link_button("Discordでログイン", authorize_url(session_id), type="primary")
    st.caption(
        "ボタンを押すとDiscordの画面が開きます。「認証」を押すと戻ってきます。"
        "（取得するのは、ユーザー名とIDだけです。パスワードや、メッセージ、フレンドなどは見ません。）"
    )


def _handle_callback(db, session_id: str, ip: str):
    """?code=&state= で戻ってきたときの処理。ログインが済んだらユーザーを返す。"""
    params = st.query_params
    code = params.get("code")
    state = params.get("state")
    error = params.get("error")
    if not (code and state) and not error:
        return None, ""

    state_sid = parse_state(state) if state else None
    for key in ("code", "state", "error", "error_description"):
        if key in st.query_params:
            del st.query_params[key]

    if error:
        return None, "Discordでの連携が許可されませんでした。もう一度お試しください。"
    if not state_sid:
        return None, "ログインの有効期限が切れたか、不正なリクエストでした。もう一度お試しください。"

    try:
        user = fetch_discord_user(code)
    except Exception as e:
        print(f"[auth] Discordからのユーザー取得に失敗しました: {type(e).__name__}: {e}", flush=True)
        return None, "Discordからユーザー情報を取得できませんでした。時間を置いてもう一度お試しください。"

    if not user["id"] or not is_allowed(db, user["id"]):
        send_event("🚫 **ログイン拒否（許可されていないアカウント）**", user, ip, state_sid)
        st.session_state["auth_event_logged"] = True  # 拒否の記録とは別に「未ログインのアクセス」を重ねて送らない
        return None, (
            "このDiscordアカウントは許可されていません。"
            f"ご利用の希望がある場合は、管理者にこのID「{user['id']}」をお伝えください。"
        )

    _save_login(db, state_sid, user)
    st.session_state["auth_user"] = user
    st.session_state["auth_event_logged"] = True
    send_event("✅ **ログイン成功**", user, ip, state_sid)
    st.query_params["sid"] = state_sid
    st.rerun()
    return user, ""


def require_login(db, session_id: str, ip: str):
    """
    ログイン済みで許可されているユーザー（dict）を返す。そうでなければログイン画面などを描画してNoneを返す。
    認証の設定（環境変数）が無いときは、AUTH_REQUIREDがtrueでなければ認証なしで通す。
    """
    if not auth_enabled():
        if AUTH_REQUIRED:
            st.error("ログインの設定が完了していません（DISCORD_CLIENT_ID / DISCORD_CLIENT_SECRET / DISCORD_REDIRECT_URI）。管理者にご連絡ください。")
            return None
        if not st.session_state.get("auth_warned"):
            st.session_state["auth_warned"] = True
            print("[auth] Discordログインの環境変数が未設定のため、認証なしで動いています", flush=True)
        return {"id": "", "username": "", "display": "（認証なし）"}

    # ① すでにこのブラウザセッションでログイン済み
    user = st.session_state.get("auth_user")
    if user and is_allowed(db, user["id"]):
        return user
    if user:  # 許可リストから外された
        logout(db, session_id)

    # ② Discordから戻ってきた直後
    user, message = _handle_callback(db, session_id, ip)
    if user:
        return user

    # ③ ブラウザを開き直した（同じsidで、期限内にログイン済み）
    saved = _load_login(db, session_id)
    if saved and is_allowed(db, saved["id"]):
        st.session_state["auth_user"] = saved
        if not st.session_state.get("auth_event_logged"):
            st.session_state["auth_event_logged"] = True
            send_event("🌐 **アクセス（ログイン済み）**", saved, ip, session_id)
        return saved

    # ④ 未ログイン：ログイン画面だけ出す
    if not st.session_state.get("auth_event_logged"):
        st.session_state["auth_event_logged"] = True
        send_event("👀 **アクセス（未ログイン）**", {}, ip, session_id)
    _show_login_page(session_id, message)
    return None


def render_account_sidebar(db, user: dict, session_id: str):
    """サイドバーにログイン中のアカウントと、ログアウト・（管理者のみ）許可リストの管理を出す。"""
    if not user or not user.get("id"):
        return
    st.caption(f"ログイン中: {user.get('display') or user.get('username')}")
    if st.button("ログアウト", key="auth_logout"):
        logout(db, session_id)
        st.rerun()

    if not is_admin(db, user["id"]):
        return
    with st.expander("👑 許可するユーザーの管理"):
        allowed = _load_allowed(db)
        st.caption(f"許可中: {len(allowed)}人")
        for uid, info in sorted(allowed.items()):
            cols = st.columns([5, 2])
            role = "（管理者）" if info.get("role") == "admin" else ""
            cols[0].markdown(f"`{uid}` {info.get('note') or ''} {role}")
            if uid not in ADMIN_IDS and uid not in INITIAL_ALLOWED_IDS:
                if cols[1].button("削除", key=f"auth_del_{uid}"):
                    remove_allowed(db, uid)
                    send_event("➖ **許可を削除**", user, "-", session_id, f"対象ID: `{uid}`")
                    st.rerun()
        with st.form("auth_add_form", clear_on_submit=True):
            new_id = st.text_input("追加するDiscordユーザーID（数字）")
            new_note = st.text_input("メモ（名前など）")
            if st.form_submit_button("追加"):
                new_id = new_id.strip()
                if not new_id.isdigit():
                    st.error("IDは数字だけで入力してください。")
                else:
                    add_allowed(db, new_id, new_note.strip(), added_by=user["id"])
                    send_event("➕ **許可を追加**", user, "-", session_id, f"対象ID: `{new_id}` メモ: {_clean(new_note)}")
                    st.rerun()
