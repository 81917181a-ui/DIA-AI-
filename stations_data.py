# -*- coding: utf-8 -*-
"""
尾羽急本線 路線データ
- 駅情報（設備・停車種別）
- 駅間所要時分（秒）
このファイルはAI（Gemini）にダイヤ作成の前提条件として渡すコンテキストとしても使用する。
"""

# 運行種別（優等度が高い順ではなく、路線図の凡例順）
SERVICE_TYPES = [
    "各停",
    "準急",
    "快速",
    "急行",
    "快速急行",
    "エアポート急行",
    "区間急行",
]

ALL_STOP = SERVICE_TYPES  # 「全種別停車」用のショートカット

# 駅データ（路線順）
# code: 駅ナンバリング（参考値）
# name: 駅名
# facilities: ホーム・線路の設備に関する情報
# stops: 停車する種別のリスト
# notes: 特記事項（折り返し可否、留置線、車庫、季節停車など）
STATIONS = [
    {
        "code": "OB01",
        "name": "尾羽原",
        "facilities": "2面2線（中線は留置線）",
        "stops": ALL_STOP,
        "notes": "路線の起点かつ主要駅。この先（西側）へは進めない。",
    },
    {
        "code": "OB02",
        "name": "井口",
        "facilities": "2面4線（両方面に待避線あり）",
        "stops": [s for s in ALL_STOP if s not in ("快速急行", "エアポート急行")],
        "notes": "快速急行・エアポート急行は通過。",
    },
    {
        "code": "OB03",
        "name": "梅郷",
        "facilities": "2面2線",
        "stops": ["各停"],
        "notes": "",
    },
    {
        "code": "OB04",
        "name": "雲中",
        "facilities": "1面2線（島式ホーム）",
        "stops": ["各停", "準急", "快速"],
        "notes": "",
    },
    {
        "code": "OB05",
        "name": "安越",
        "facilities": "2面4線（両方面へ折り返し可能）",
        "stops": [s for s in ALL_STOP if s != "快速急行"],
        "notes": "快速急行のみ通過。",
    },
    {
        "code": "OB05-1",
        "name": "十川",
        "facilities": "2面2線",
        "stops": ["各停"],
        "notes": "",
    },
    {
        "code": "OB06",
        "name": "千峰",
        "facilities": "2面3線（尾羽原方面に退避線あり）",
        "stops": ["各停", "準急"],
        "notes": "希望がない限り折り返しは行わない。",
    },
    {
        "code": "OB07",
        "name": "南雲谷",
        "facilities": "1面4線（中2線は停車専用）",
        "stops": ["各停"],
        "notes": "千峰との間に留置線あり（南雲谷から留置線まで30秒）。",
    },
    {
        "code": "OB08",
        "name": "雲谷",
        "facilities": "2面3線（尾羽原方面に退避線あり）",
        "stops": ["各停", "準急", "快速", "急行"],
        "notes": "両方面へ折り返し可能。",
    },
    {
        "code": "OB09",
        "name": "長峰",
        "facilities": "2面2線",
        "stops": ["各停", "準急", "快速"],
        "notes": "",
    },
    {
        "code": "OB09-1",
        "name": "西高徳",
        "facilities": "2面2線",
        "stops": ["各停", "快速"],
        "notes": "",
    },
    {
        "code": "OB10",
        "name": "高徳",
        "facilities": "2面4線（両方面へ折り返し可能）",
        "stops": ALL_STOP,
        "notes": "高徳〜明神前間に車庫あり。高徳発車後15秒で入庫可能。",
    },
    {
        "code": "OB11",
        "name": "明神前",
        "facilities": "2面2線",
        "stops": ["各停", "快速", "区間急行"],
        "notes": "",
    },
    {
        "code": "OB12",
        "name": "舞子台",
        "facilities": "2面2線",
        "stops": ["準急", "快速"],
        "notes": "夏季は急行が臨時停車（区間急行は通年停車）。",
    },
    {
        "code": "OB13",
        "name": "紀田",
        "facilities": "6面10線（両方面へ折り返し可能）",
        "stops": ALL_STOP,
        "notes": "",
    },
    {
        "code": "OB13-1",
        "name": "穂",
        "facilities": "2面2線",
        "stops": ["各停", "快速", "区間急行"],
        "notes": "瀬舞方面へ20秒で車両基地入庫可能だが、要望がない限り使用しない。",
    },
    {
        "code": "OB14",
        "name": "瀬舞",
        "facilities": "2面2線",
        "stops": ["各停", "快速", "区間急行"],
        "notes": "",
    },
    {
        "code": "OB15",
        "name": "余美",
        "facilities": "2面2線",
        "stops": ["各停", "快速", "区間急行"],
        "notes": "",
    },
    {
        "code": "OB16",
        "name": "千鳥",
        "facilities": "2面4線（0番線は尾羽原方面へは行けない、4番線は尾羽原方面からの折り返し用）",
        "stops": ALL_STOP,
        "notes": "井問線と直通運転を行う。",
    },
]

# 駅間所要時分（秒）。STATIONS の並び順に対応する隣接区間のリスト。
# 例: RUN_TIMES[0] は STATIONS[0]（尾羽原）-> STATIONS[1]（井口）の所要時分
RUN_TIMES_SEC = [
    100,  # 尾羽原-井口
    60,   # 井口-梅郷
    40,   # 梅郷-雲中
    70,   # 雲中-安越
    90,   # 安越-十川
    90,   # 十川-千峰
    80,   # 千峰-南雲谷
    120,  # 南雲谷-雲谷
    90,   # 雲谷-長峰
    90,   # 長峰-西高徳
    90,   # 西高徳-高徳
    130,  # 高徳-明神前
    90,   # 明神前-舞子台
    80,   # 舞子台-紀田
    80,   # 紀田-穂
    60,   # 穂-瀬舞
    70,   # 瀬舞-余美
    60,   # 余美-千鳥
]

# ---------------------------------------------------------------------------
# 千鳥支線（本郷 - 千鳥、全線単線）
# ---------------------------------------------------------------------------
CHIDORI_BRANCH_STATIONS = [
    {"name": "本郷", "facilities": "2面4線（千鳥支線へは1・4番線からのみ入線可能）", "notes": "井問線と接続。"},
    {"name": "本郷神宮前", "facilities": "1面2線（すれ違い可能）", "notes": ""},
    {"name": "千鳥山道", "facilities": "1面1線", "notes": ""},
    {"name": "奥千鳥", "facilities": "1面2線（片方は千鳥方面からの折り返し用）", "notes": ""},
    {"name": "南千鳥", "facilities": "2面2線（すれ違い可能）", "notes": "問屋町方面への連絡線あり。"},
    {"name": "千鳥", "facilities": "2面4線（0番線は尾羽原方面へは行けない、4番線は尾羽原方面からの折り返し用）", "notes": "尾羽急本線・井問線と接続。"},
]

CHIDORI_BRANCH_RUN_TIMES_SEC = [
    140,  # 本郷-本郷神宮前
    110,  # 本郷神宮前-千鳥山道
    115,  # 千鳥山道-奥千鳥
    80,   # 奥千鳥-南千鳥
    110,  # 南千鳥-千鳥
]

CHIDORI_BRANCH_NOTES = "全線単線。運行種別は普通（各駅停車）のみ。"

# ---------------------------------------------------------------------------
# 井問線（いといせん、井口 - 千鳥）
# ---------------------------------------------------------------------------
ITOI_LINE_SERVICE_TYPES = ["普通", "快速", "急行"]

ITOI_LINE_STATIONS = [
    {
        "name": "井口",
        "facilities": "尾羽急本線と同じ構造（本線の副本線から井問線へ、井問線から来ると副本線に出る）",
        "stops": ITOI_LINE_SERVICE_TYPES,
        "notes": "尾羽急本線と接続。",
    },
    {"name": "上井口", "facilities": "2面2線", "stops": ["普通"], "notes": ""},
    {"name": "参田町", "facilities": "2面2線", "stops": ["普通", "快速"], "notes": ""},
    {
        "name": "東本郷",
        "facilities": "2面2線",
        "stops": ["普通"],
        "notes": "普通のうち一部は通過（全便停車ではない）。",
    },
    {
        "name": "本郷",
        "facilities": "2面4線（副本線から千鳥支線へ入線可能）",
        "stops": ITOI_LINE_SERVICE_TYPES,
        "notes": "千鳥支線と接続。",
    },
    {
        "name": "西問屋町",
        "facilities": "1面2線",
        "stops": ["普通"],
        "notes": "普通のうち一部は通過（全便停車ではない）。",
    },
    {
        "name": "問屋町",
        "facilities": "2面4線（中2線は通過線）",
        "stops": ["普通", "快速"],
        "notes": "南千鳥方面（千鳥支線）への連絡線あり。",
    },
    {
        "name": "千鳥",
        "facilities": "2面4線（0番線は尾羽原方面へは行けない、4番線は尾羽原方面からの折り返し用）",
        "stops": ITOI_LINE_SERVICE_TYPES,
        "notes": "尾羽急本線・千鳥支線と接続。",
    },
]

ITOI_LINE_RUN_TIMES_SEC = [
    120,  # 井口-上井口
    80,   # 上井口-参田町
    80,   # 参田町-東本郷
    60,   # 東本郷-本郷
    80,   # 本郷-西問屋町
    110,  # 西問屋町-問屋町
    110,  # 問屋町-千鳥
]

# 急行は東本郷・西問屋町などを通過するため、区間ごとの直行所要時分が別途定義されている
ITOI_LINE_EXPRESS_RUN_TIMES_SEC = {
    ("井口", "本郷"): 210,
    ("本郷", "千鳥"): 300,
}

ITOI_LINE_NOTES = (
    "井問線は複線（千鳥〜問屋町間は複々線、問屋町〜井口間は複線）。"
    "本郷から千鳥支線へ、千鳥から尾羽急本線へ直通運転が可能。"
    "南千鳥〜問屋町間の連絡線の所要時分は「千鳥〜南千鳥」+「千鳥〜問屋町」-20秒で算出する"
    "（この連絡線でつながっている）。"
    "停車パターン: 普通は各駅停車（東本郷・西問屋町は一部列車のみ停車）、"
    "快速は井口・参田町・本郷・問屋町・千鳥の順に停車、"
    "急行は井口・本郷・千鳥の順に停車。"
)

# ---------------------------------------------------------------------------
# 東阪モノレール（山樺町 - 今台空港、尾羽急本線・井問線とは接続しない独立路線）
# ---------------------------------------------------------------------------
TOZAKA_MONORAIL_SERVICE_TYPES = ["普通", "空港快速"]

TOZAKA_MONORAIL_STATIONS = [
    {"name": "山樺町", "facilities": "2面1線（浜松町駅のような構造）", "notes": ""},
    {"name": "ジオスクエア", "facilities": "2面2線", "notes": ""},
    {"name": "皿具養鶏場前", "facilities": "2面2線", "notes": ""},
    {
        "name": "朱雀島",
        "facilities": "2面4線",
        "notes": (
            "山樺町側に朱雀車庫があり、山樺町からの電車が空港方面へ折り返し可能。"
            "出庫にかかる時間は30秒。途中駅で待避が可能なのは朱雀島のみ。"
        ),
    },
    {"name": "流通センター", "facilities": "2面2線", "notes": ""},
    {"name": "みやこ橋", "facilities": "2面2線", "notes": ""},
    {"name": "巴海岸公園", "facilities": "2面2線", "notes": ""},
    {"name": "今台空港", "facilities": "1面2線", "notes": ""},
]

# 普通の駅間所要時分（秒）。上り・下りとも同じ（⇅で同一時分と指定されている）。
TOZAKA_MONORAIL_RUN_TIMES_SEC = [
    110,  # 山樺町-ジオスクエア
    100,  # ジオスクエア-皿具養鶏場前
    70,   # 皿具養鶏場前-朱雀島
    60,   # 朱雀島-流通センター
    80,   # 流通センター-みやこ橋
    70,   # みやこ橋-巴海岸公園
    120,  # 巴海岸公園-今台空港
]

# 空港快速の停車駅（山樺町・朱雀島・巴海岸公園・今台空港のみ。朱雀島は要望があれば停車、
# 通常は通過）。ジオスクエア・皿具養鶏場前・流通センター・みやこ橋は通過。
TOZAKA_MONORAIL_EXPRESS_STOPS = ["山樺町", "朱雀島", "巴海岸公園", "今台空港"]

# 空港快速の停車駅間の直行所要時分（秒）。停車駅の並び順に対応する。
TOZAKA_MONORAIL_EXPRESS_RUN_TIMES_SEC = [
    120,  # 山樺町-朱雀島
    135,  # 朱雀島-巴海岸公園
    210,  # 巴海岸公園-今台空港
]

TOZAKA_MONORAIL_NOTES = (
    "尾羽急本線・井問線とは接続しない独立した路線（モノレール）。"
    "普通は全駅に停車。空港快速はジオスクエア・皿具養鶏場前・流通センター・"
    "みやこ橋を通過し、朱雀島は要望があれば停車（通常は通過）。"
)

# ---------------------------------------------------------------------------
# 尾羽急高速線（千鳥 - 金田）
# ---------------------------------------------------------------------------
RAPID_LINE_SERVICE_TYPES = ["各停", "急行", "快速急行"]

RAPID_LINE_STATIONS = [
    {
        "name": "千鳥",
        "facilities": "尾羽急本線・千鳥支線・井問線と共通（各路線データを参照）",
        "stops": RAPID_LINE_SERVICE_TYPES,
        "notes": "尾羽急本線・千鳥支線・井問線と接続。",
    },
    {"name": "問屋町", "facilities": "2面4線", "stops": ["各停"], "notes": "井問線の問屋町と同一駅。"},
    {"name": "問屋蔵前", "facilities": "2面6線（中2線は通過線）", "stops": ["各停"], "notes": ""},
    {"name": "赤堀大沢", "facilities": "2面4線（中2線は通過線）", "stops": ["各停"], "notes": ""},
    {
        "name": "赤堀",
        "facilities": "2面4線",
        "stops": ["各停", "急行"],
        "notes": "赤堀アリーナ方面への支線があり、所要時分は70秒（詳細未設定）。",
    },
    {"name": "新赤堀", "facilities": "2面3線（中線あり）", "stops": ["各停"], "notes": ""},
    {"name": "塚野", "facilities": "2面2線", "stops": ["各停"], "notes": "塚野側から金田線へ入線可能。"},
    {
        "name": "金田",
        "facilities": "2面4線（真ん中は通過線）",
        "stops": RAPID_LINE_SERVICE_TYPES,
        "notes": "金田線と接続。",
    },
]

# 各停の駅間所要時分（秒）
RAPID_LINE_RUN_TIMES_SEC = [
    115,  # 千鳥-問屋町
    75,   # 問屋町-問屋蔵前
    75,   # 問屋蔵前-赤堀大沢
    90,   # 赤堀大沢-赤堀
    120,  # 赤堀-新赤堀
    60,   # 新赤堀-塚野
    100,  # 塚野-金田
]

# 急行・快速急行は上記以外の駅を通過するため、区間ごとの直行所要時分を別途定義
RAPID_LINE_EXPRESS_RUN_TIMES_SEC = {
    ("快速急行", "千鳥", "金田"): 415,
    ("急行", "千鳥", "赤堀"): 250,
    ("急行", "赤堀", "金田"): 190,
}

RAPID_LINE_NOTES = (
    "尾羽急高速線。千鳥方面で尾羽急本線・千鳥支線・井問線と、金田方面で金田線と接続。"
    "各停は全駅に停車、急行は千鳥・赤堀・金田のみ、快速急行は千鳥・金田のみ停車。"
    "塚野から金田線へ入線可能。"
)

# ---------------------------------------------------------------------------
# 金田線（金田 - 金田新都心）
# ---------------------------------------------------------------------------
KANADA_LINE_SERVICE_TYPES = ["各停", "急行", "快速急行"]

KANADA_LINE_STATIONS = [
    {
        "name": "金田",
        "facilities": "地下駅",
        "stops": KANADA_LINE_SERVICE_TYPES,
        "notes": "駅番号OK01。尾羽急高速線と接続（塚野側から入線）。",
    },
    {"name": "鵲橋", "facilities": "", "stops": ["各停"], "notes": "駅番号OK01-1。"},
    {"name": "金田市", "facilities": "", "stops": ["各停"], "notes": "駅番号OK02。"},
    {"name": "金田空港", "facilities": "", "stops": ["各停", "急行"], "notes": "駅番号OK03。"},
    {
        "name": "金田新都心",
        "facilities": "",
        "stops": KANADA_LINE_SERVICE_TYPES,
        "notes": "駅番号OK04。",
    },
]

KANADA_LINE_RUN_TIMES_SEC = [
    180,  # 金田-鵲橋
    120,  # 鵲橋-金田市
    90,   # 金田市-金田空港
    90,   # 金田空港-金田新都心
]

KANADA_LINE_NOTES = (
    "金田で尾羽急高速線と接続。各停は全駅に停車、"
    "急行は金田・金田空港・金田新都心のみ、快速急行は金田・金田新都心のみ停車。"
)


def build_line_context_text() -> str:
    """AI（Gemini）にダイヤ作成の前提条件として渡すテキストを組み立てる。"""
    lines = ["# 尾羽急本線 路線データ", ""]
    lines.append(f"運行種別: {', '.join(SERVICE_TYPES)}")
    lines.append("")
    lines.append("## 駅一覧（起点から終点の順）")
    for i, st in enumerate(STATIONS):
        lines.append(
            f"- {st['code']} {st['name']}: 設備={st['facilities']} / "
            f"停車種別={'・'.join(st['stops'])}"
            + (f" / 備考={st['notes']}" if st["notes"] else "")
        )

    lines.append("")
    lines.append("## 駅間所要時分（秒）")
    for i in range(len(STATIONS) - 1):
        a = STATIONS[i]["name"]
        b = STATIONS[i + 1]["name"]
        lines.append(f"- {a} - {b}: {RUN_TIMES_SEC[i]}秒")

    # --- 千鳥支線 ---
    lines.append("")
    lines.append("# 千鳥支線 路線データ（本郷 - 千鳥）")
    lines.append(CHIDORI_BRANCH_NOTES)
    lines.append("")
    lines.append("## 駅一覧（本郷から千鳥の順）")
    for st in CHIDORI_BRANCH_STATIONS:
        lines.append(
            f"- {st['name']}: 設備={st['facilities']}"
            + (f" / 備考={st['notes']}" if st["notes"] else "")
        )
    lines.append("")
    lines.append("## 駅間所要時分（秒）")
    for i in range(len(CHIDORI_BRANCH_STATIONS) - 1):
        a = CHIDORI_BRANCH_STATIONS[i]["name"]
        b = CHIDORI_BRANCH_STATIONS[i + 1]["name"]
        lines.append(f"- {a} - {b}: {CHIDORI_BRANCH_RUN_TIMES_SEC[i]}秒")

    # --- 井問線 ---
    lines.append("")
    lines.append("# 井問線（いといせん）路線データ（井口 - 千鳥）")
    lines.append(f"運行種別: {', '.join(ITOI_LINE_SERVICE_TYPES)}")
    lines.append(ITOI_LINE_NOTES)
    lines.append("")
    lines.append("## 駅一覧（井口から千鳥の順）")
    for st in ITOI_LINE_STATIONS:
        lines.append(
            f"- {st['name']}: 設備={st['facilities']} / "
            f"停車種別={'・'.join(st['stops'])}"
            + (f" / 備考={st['notes']}" if st["notes"] else "")
        )
    lines.append("")
    lines.append("## 駅間所要時分（秒）")
    for i in range(len(ITOI_LINE_STATIONS) - 1):
        a = ITOI_LINE_STATIONS[i]["name"]
        b = ITOI_LINE_STATIONS[i + 1]["name"]
        lines.append(f"- {a} - {b}: {ITOI_LINE_RUN_TIMES_SEC[i]}秒")
    lines.append("")
    lines.append("## 急行の区間直行所要時分（秒）")
    for (a, b), sec in ITOI_LINE_EXPRESS_RUN_TIMES_SEC.items():
        lines.append(f"- {a} - {b}: {sec}秒")

    # --- 東阪モノレール ---
    lines.append("")
    lines.append("# 東阪モノレール 路線データ（山樺町 - 今台空港）")
    lines.append(f"運行種別: {', '.join(TOZAKA_MONORAIL_SERVICE_TYPES)}")
    lines.append(TOZAKA_MONORAIL_NOTES)
    lines.append("")
    lines.append("## 駅一覧（山樺町から今台空港の順、普通は全駅停車）")
    for st in TOZAKA_MONORAIL_STATIONS:
        lines.append(
            f"- {st['name']}: 設備={st['facilities']}"
            + (f" / 備考={st['notes']}" if st["notes"] else "")
        )
    lines.append("")
    lines.append("## 普通の駅間所要時分（秒）")
    for i in range(len(TOZAKA_MONORAIL_STATIONS) - 1):
        a = TOZAKA_MONORAIL_STATIONS[i]["name"]
        b = TOZAKA_MONORAIL_STATIONS[i + 1]["name"]
        lines.append(f"- {a} - {b}: {TOZAKA_MONORAIL_RUN_TIMES_SEC[i]}秒")
    lines.append("")
    lines.append(f"## 空港快速の停車駅: {'・'.join(TOZAKA_MONORAIL_EXPRESS_STOPS)}")
    lines.append("## 空港快速の停車駅間の直行所要時分（秒）")
    for i in range(len(TOZAKA_MONORAIL_EXPRESS_STOPS) - 1):
        a = TOZAKA_MONORAIL_EXPRESS_STOPS[i]
        b = TOZAKA_MONORAIL_EXPRESS_STOPS[i + 1]
        lines.append(f"- {a} - {b}: {TOZAKA_MONORAIL_EXPRESS_RUN_TIMES_SEC[i]}秒")

    # --- 尾羽急高速線 ---
    lines.append("")
    lines.append("# 尾羽急高速線 路線データ（千鳥 - 金田）")
    lines.append(f"運行種別: {', '.join(RAPID_LINE_SERVICE_TYPES)}")
    lines.append(RAPID_LINE_NOTES)
    lines.append("")
    lines.append("## 駅一覧（千鳥から金田の順）")
    for st in RAPID_LINE_STATIONS:
        lines.append(
            f"- {st['name']}: 設備={st['facilities']} / "
            f"停車種別={'・'.join(st['stops'])}"
            + (f" / 備考={st['notes']}" if st["notes"] else "")
        )
    lines.append("")
    lines.append("## 各停の駅間所要時分（秒）")
    for i in range(len(RAPID_LINE_STATIONS) - 1):
        a = RAPID_LINE_STATIONS[i]["name"]
        b = RAPID_LINE_STATIONS[i + 1]["name"]
        lines.append(f"- {a} - {b}: {RAPID_LINE_RUN_TIMES_SEC[i]}秒")
    lines.append("")
    lines.append("## 急行・快速急行の区間直行所要時分（秒）")
    for (service, a, b), sec in RAPID_LINE_EXPRESS_RUN_TIMES_SEC.items():
        lines.append(f"- [{service}] {a} - {b}: {sec}秒")

    # --- 金田線 ---
    lines.append("")
    lines.append("# 金田線 路線データ（金田 - 金田新都心）")
    lines.append(f"運行種別: {', '.join(KANADA_LINE_SERVICE_TYPES)}")
    lines.append(KANADA_LINE_NOTES)
    lines.append("")
    lines.append("## 駅一覧（金田から金田新都心の順）")
    for st in KANADA_LINE_STATIONS:
        lines.append(
            f"- {st['name']}: 設備={st['facilities'] or '未設定'} / "
            f"停車種別={'・'.join(st['stops'])}"
            + (f" / 備考={st['notes']}" if st["notes"] else "")
        )
    lines.append("")
    lines.append("## 各停の駅間所要時分（秒）")
    for i in range(len(KANADA_LINE_STATIONS) - 1):
        a = KANADA_LINE_STATIONS[i]["name"]
        b = KANADA_LINE_STATIONS[i + 1]["name"]
        lines.append(f"- {a} - {b}: {KANADA_LINE_RUN_TIMES_SEC[i]}秒")

    return "\n".join(lines)
