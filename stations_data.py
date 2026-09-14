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

    return "\n".join(lines)
