# -*- coding: utf-8 -*-
"""
OuDiaSecond (.oud2) 形式でダイヤファイルを書き出す最小限のエクスポーター。

.oud2はOuDiaSecondという鉄道ダイヤ作成ソフト独自のテキスト形式で、公式の仕様書は
公開されていない。ユーザーから提供されたサンプルファイル（TK市ダイヤ.oud2 /
運転会作成_分割併合_.oud2）を解析し、以下の構造を確認したうえで実装している。

  FileType=OuDiaSecond.1.15
  Rosen.
    Rosenmei=<路線名>
    Eki. (駅の数だけ繰り返し)
      Ekimei=<駅名>
      ...
      EkiTrack2Cont.
        EkiTrack2. (ホーム線路の数だけ繰り返し)
          TrackName=<n番線>
          TrackRyakusyou=<n>
        .
      .
    .
    Ressyasyubetsu. (列車種別の数だけ繰り返し)
      Syubetsumei=<種別名>
      ...
    .
    Dia.
      DiaName=<ダイヤ名>
      Kudari.
        Ressya. (下り列車の数だけ繰り返し)
          Houkou=Kudari
          Syubetsu=<種別インデックス>
          EkiJikoku=<駅ごとの時刻を,区切りで並べたもの>
        .
      .
      Nobori.
        Ressya. (上り列車の数だけ繰り返し)
          ...
        .
      .
    .
  .
  FileTypeAppComment=...

EkiJikokuの1駅ぶんのエントリは以下のいずれか：
  - 空文字列: その列車はこの駅を通らない（経路の始点より前・終点より後、
    または該当種別がそもそもその駅に来ない「なし」扱い）
  - "1;<時刻>$<番線インデックス>"          … 起点駅（発のみ、停車）
  - "1;<時刻>/$<番線インデックス>"          … 終点駅（着のみ、停車）
  - "1;<着時刻>/<発時刻>$<番線インデックス>" … 中間駅で停車
  - "2$<番線インデックス>"                  … 通過（時刻は記録しない）

停車は常に先頭"1"、通過は常に先頭"2"という固定の記号が使われる
（方向や駅ごとに変わるものではないことを実データの解析で確認済み）。
時刻はH[H]MM[SS]形式（秒が0の場合は秒部分を省略）。

下り(Kudari)はEki.の宣言順（先頭の駅→末尾の駅）でエントリを並べ、
上り(Nobori)は逆順（末尾の駅→先頭の駅）でエントリを並べる
（実データを解析して確認した規則）。

OuDiaSecondの1つのRosen（路線）は駅が一直線に並ぶ構造しか表現できず、
分岐・合流のあるネットワーク全体を1ファイルに収めることはできない。
そのため、路線ごとに別々の.oud2ファイルを生成し、まとめてzipで渡す方式にしている。

列車の分割併合など、より高度な機能には対応していない。
"""

import io
import re
import zipfile

from stations_data import (
    STATIONS,
    RUN_TIMES_SEC,
    SERVICE_TYPES,
    CHIDORI_BRANCH_STATIONS,
    CHIDORI_BRANCH_RUN_TIMES_SEC,
    ITOI_LINE_STATIONS,
    ITOI_LINE_RUN_TIMES_SEC,
    ITOI_LINE_SERVICE_TYPES,
    ITOI_LINE_EXPRESS_RUN_TIMES_SEC,
    TOZAKA_MONORAIL_STATIONS,
    TOZAKA_MONORAIL_RUN_TIMES_SEC,
    TOZAKA_MONORAIL_SERVICE_TYPES,
    TOZAKA_MONORAIL_EXPRESS_STOPS,
    TOZAKA_MONORAIL_EXPRESS_RUN_TIMES_SEC,
    RAPID_LINE_STATIONS,
    RAPID_LINE_RUN_TIMES_SEC,
    RAPID_LINE_SERVICE_TYPES,
    RAPID_LINE_EXPRESS_RUN_TIMES_SEC,
    KANADA_LINE_STATIONS,
    KANADA_LINE_RUN_TIMES_SEC,
    KANADA_LINE_SERVICE_TYPES,
)

CRLF = "\r\n"

# 代表ダイヤ生成のデフォルト値
DEFAULT_START_SEC = 6 * 3600  # 6:00:00始発
DEFAULT_DWELL_SEC = 20        # 中間停車駅での停車時間（秒）

_SERVICE_COLORS = [
    "00000000", "000000FF", "0000FF00", "00FF0000",
    "00FF8000", "00808080", "00800080",
]


def _parse_track_count(facilities: str) -> int:
    """「2面4線」のような設備文字列からホーム線路の本数を取り出す。読み取れなければ2本とする。"""
    m = re.search(r"面(\d+)線", facilities or "")
    if m:
        return max(1, int(m.group(1)))
    return 2


def format_oud2_time(total_seconds) -> str:
    """0時からの経過秒を OuDiaSecond の時刻表記（H[H]MM[SS]）に変換する。"""
    total_seconds = int(round(total_seconds))
    h, rem = divmod(total_seconds, 3600)
    m, s = divmod(rem, 60)
    if s == 0:
        return f"{h}{m:02d}"
    return f"{h}{m:02d}{s:02d}"


def _append_eki_blocks(lines: list, stations: list):
    for station in stations:
        track_count = _parse_track_count(station.get("facilities", ""))
        lines.append("Eki.")
        lines.append(f"Ekimei={station['name']}")
        lines.append("Ekijikokukeisiki=Jikokukeisiki_Hatsuchaku")
        lines.append("Ekikibo=Ekikibo_Ippan")
        lines.append("DownMain=1")
        lines.append("UpMain=2")
        lines.append("EkiTrack2Cont.")
        for i in range(1, track_count + 1):
            lines.append("EkiTrack2.")
            lines.append(f"TrackName={i}番線")
            lines.append(f"TrackRyakusyou={i}")
            lines.append(".")
        lines.append(".")
        lines.append(".")


def _append_ressyasyubetsu_blocks(lines: list, service_types: list):
    for i, name in enumerate(service_types):
        lines.append("Ressyasyubetsu.")
        lines.append(f"Syubetsumei={name}")
        lines.append(f"Ryakusyou={name[:2]}")
        lines.append("JikokuhyouMojiColor=00000000")
        lines.append("JikokuhyouFontIndex=0")
        lines.append("JikokuhyouBackColor=00FFFFFF")
        lines.append(f"DiagramSenColor={_SERVICE_COLORS[i % len(_SERVICE_COLORS)]}")
        lines.append("DiagramSenStyle=SenStyle_Jissen")
        lines.append("StopMarkDrawType=EStopMarkDrawType_DrawOnStop")
        lines.append(".")


def _station_platform_index(stations: list, station_idx: int, direction: str) -> int:
    """
    駅の設備（番線数）をもとに、方向ごとに使う番線インデックス（0始まり）を決める。
    下りは0番目、上りは2番線以上ある駅なら1番目、1線しかない駅は0番目を使う。
    """
    track_count = _parse_track_count(stations[station_idx].get("facilities", ""))
    if direction == "Kudari":
        return 0
    return 1 if track_count > 1 else 0


# 停車しない駅を「なし（経路に含まれない）」として扱う種別名。
# 各路線の「最も基本的な種別」（各駅停車・普通）はその性質上、停まらない駅には
# そもそも来ない（なし扱い）と考え、それ以外の種別（快速・急行など）は
# 物理的にはその駅を通るが停まらないだけなので「通過」として扱う。
NONE_INSTEAD_OF_PASS_SERVICES = {"各停", "普通"}


def _ekijikoku_field(stations: list, direction: str, stops: dict, service: str) -> str:
    """
    stations: この路線の駅リスト（順序が物理的な並び順）
    stops: {駅インデックス(0-based, stationsの並び順): (着時刻sec or None, 発時刻sec or None)}
           通過する駅は (None, None) を、経路に含まれない駅はキー自体を省略する。
    service: 列車種別名。停まらない駅を「なし」にするか「通過」にするかの判定に使う。
    """
    n = len(stations)
    order = range(n) if direction == "Kudari" else range(n - 1, -1, -1)
    use_none = service in NONE_INSTEAD_OF_PASS_SERVICES

    entries = []
    for idx in order:
        if idx not in stops:
            entries.append("")
            continue
        arr, dep = stops[idx]
        platform = _station_platform_index(stations, idx, direction)
        if arr is None and dep is None:
            if use_none:
                entries.append("")  # 「なし」：この種別はそもそもこの駅に来ない扱い
            else:
                entries.append(f"2${platform}")  # 「通過」：先頭固定"2"、時刻なし
        elif arr is None and dep is not None:
            entries.append(f"1;{format_oud2_time(dep)}${platform}")  # 起点
        elif arr is not None and dep is None:
            entries.append(f"1;{format_oud2_time(arr)}/${platform}")  # 終点
        else:
            entries.append(
                f"1;{format_oud2_time(arr)}/{format_oud2_time(dep)}${platform}"
            )  # 中間停車
    return ",".join(entries)


def _append_ressya(
    lines: list, stations: list, direction: str, service_index: int,
    service_name: str, train_number: str, stops: dict,
):
    lines.append("Ressya.")
    lines.append(f"Houkou={direction}")
    lines.append(f"Syubetsu={service_index}")
    if train_number:
        lines.append(f"Ressyabangou={train_number}")
    lines.append(f"EkiJikoku={_ekijikoku_field(stations, direction, stops, service_name)}")
    lines.append(".")


def _append_dia_block(
    lines: list, stations: list, service_types: list, dia_name: str,
    kudari_trains: list, nobori_trains: list,
):
    lines.append("Dia.")
    lines.append(f"DiaName={dia_name}")
    lines.append("Kudari.")
    for t in kudari_trains:
        _append_ressya(
            lines, stations, "Kudari", t["service_index"], service_types[t["service_index"]],
            t.get("train_number", ""), t["stops"],
        )
    lines.append(".")
    lines.append("Nobori.")
    for t in nobori_trains:
        _append_ressya(
            lines, stations, "Nobori", t["service_index"], service_types[t["service_index"]],
            t.get("train_number", ""), t["stops"],
        )
    lines.append(".")
    lines.append(".")


def build_oud2_file(
    line_name: str, dia_name: str, stations: list, service_types: list,
    kudari_trains: list, nobori_trains: list,
) -> str:
    """
    stations: この路線の駅リスト（各要素は最低限 "name" キーを持つ辞書。"facilities"は任意）
    service_types: この路線の運行種別名のリスト
    kudari_trains / nobori_trains: [{"service_index": int, "train_number": str, "stops": {...}}]
    戻り値: UTF-8 BOM付き・CRLF改行の.oud2ファイル本文（文字列）
    """
    lines = [
        "FileType=OuDiaSecond.1.15",
        "Rosen.",
        f"Rosenmei={line_name}",
        "KudariDiaAlias=",
        "NoboriDiaAlias=",
    ]
    _append_eki_blocks(lines, stations)
    _append_ressyasyubetsu_blocks(lines, service_types)
    _append_dia_block(lines, stations, service_types, dia_name, kudari_trains, nobori_trains)
    lines.append(".")  # Rosen.を閉じる
    lines.append("FileTypeAppComment=Generated by 鉄道ダイヤ作成専門AI")
    return "\ufeff" + CRLF.join(lines) + CRLF


# 種別ごとの運転間隔（秒）。数字が小さいほど本数が多い。
DEFAULT_HEADWAY_SEC = {
    "各停": 8 * 60,
    "準急": 12 * 60,
    "快速": 15 * 60,
    "急行": 20 * 60,
    "快速急行": 30 * 60,
    "エアポート急行": 40 * 60,
    "区間急行": 20 * 60,
}
OPERATION_START_SEC = 6 * 3600   # 6:00 始発
OPERATION_END_SEC = 24 * 3600    # 24:00 まで運転


# 種別ごとの運転間隔（秒）のデフォルト値。数字が小さいほど本数が多い。
# 路線ごとに存在する種別だけが参照される。
DEFAULT_HEADWAY_SEC = {
    "各停": 8 * 60,
    "普通": 10 * 60,
    "準急": 12 * 60,
    "快速": 15 * 60,
    "急行": 20 * 60,
    "快速急行": 30 * 60,
    "エアポート急行": 40 * 60,
    "空港快速": 20 * 60,
    "区間急行": 20 * 60,
}
OPERATION_START_SEC = 6 * 3600   # 6:00 始発
OPERATION_END_SEC = 24 * 3600    # 24:00 まで運転


def _compute_stops_for_service(
    stations: list, run_times_sec: list, service: str, direction: str,
    start_sec: int, dwell_sec: int, express_times: dict = None,
) -> dict:
    """
    指定した路線・種別・方向・始発時刻の列車1本ぶんの{駅インデックス: (着, 発)}を計算する。

    express_times: {(種別名, 停車駅A, 停車駅B): 秒} の形式で、AからBまでの直行所要時分を
                    個別指定できる（急行等が途中駅を通過して普通より速く走る場合に使う）。
                    指定がない区間は、各駅間の所要時分（run_times_sec）を素直に積み上げる。
    """
    express_times = express_times or {}
    n = len(stations)
    seq = list(range(n)) if direction == "Kudari" else list(range(n - 1, -1, -1))

    stops = {}
    t = start_sec
    last_stop_pos = None
    for pos, idx in enumerate(seq):
        station = stations[idx]
        if pos > 0:
            prev_idx = seq[pos - 1]
            seg_index = min(idx, prev_idx)
            t += run_times_sec[seg_index]

        stops_here = service in station["stops"]
        if not stops_here:
            stops[idx] = (None, None)
            continue

        # 直前の停車駅からこの駅までの直行所要時分が個別指定されていれば、
        # 積み上げ計算のtを上書きする（急行等の通過運転を正しく反映するため）
        if last_stop_pos is not None and express_times:
            prev_idx2 = seq[last_stop_pos]
            key = (service, stations[prev_idx2]["name"], station["name"])
            if key in express_times:
                prev_dep = stops[prev_idx2][1]
                t = prev_dep + express_times[key]

        if pos == 0:
            stops[idx] = (None, t)
        elif pos == n - 1:
            stops[idx] = (t, None)
        else:
            arr = t
            dep = t + dwell_sec
            stops[idx] = (arr, dep)
            t = dep
        last_stop_pos = pos

    return stops


def build_full_day_trains(
    stations: list,
    run_times_sec: list,
    service_types: list,
    express_times: dict = None,
    start_sec: int = OPERATION_START_SEC,
    end_sec: int = OPERATION_END_SEC,
    dwell_sec: int = DEFAULT_DWELL_SEC,
    headways: dict = None,
):
    """種別・方向ごとに、始発から終電まで運転間隔どおりに列車を並べた終日ダイヤを生成する。"""
    headways = headways or {}
    kudari_trains = []
    nobori_trains = []

    for service_index, service in enumerate(service_types):
        headway = headways.get(service, DEFAULT_HEADWAY_SEC.get(service, 20 * 60))

        seq = 1
        t = start_sec
        while t < end_sec:
            stops = _compute_stops_for_service(
                stations, run_times_sec, service, "Kudari", t, dwell_sec, express_times
            )
            train_number = f"{service_index + 1}0{seq:03d}"
            kudari_trains.append(
                {"service_index": service_index, "train_number": train_number, "stops": stops}
            )
            seq += 1
            t += headway

        seq = 1
        t = start_sec
        while t < end_sec:
            stops = _compute_stops_for_service(
                stations, run_times_sec, service, "Nobori", t, dwell_sec, express_times
            )
            train_number = f"{service_index + 1}5{seq:03d}"
            nobori_trains.append(
                {"service_index": service_index, "train_number": train_number, "stops": stops}
            )
            seq += 1
            t += headway

    return kudari_trains, nobori_trains


def _tozaka_stations_with_stops() -> list:
    """東阪モノレールは駅データに"stops"が無いため、ここで組み立てる。"""
    result = []
    for st in TOZAKA_MONORAIL_STATIONS:
        stops = list(TOZAKA_MONORAIL_SERVICE_TYPES) if st["name"] in TOZAKA_MONORAIL_EXPRESS_STOPS else ["普通"]
        result.append({**st, "stops": stops})
    return result


def _tozaka_express_times() -> dict:
    times = {}
    for i in range(len(TOZAKA_MONORAIL_EXPRESS_STOPS) - 1):
        a = TOZAKA_MONORAIL_EXPRESS_STOPS[i]
        b = TOZAKA_MONORAIL_EXPRESS_STOPS[i + 1]
        times[("空港快速", a, b)] = TOZAKA_MONORAIL_EXPRESS_RUN_TIMES_SEC[i]
    return times


def _chidori_stations_with_stops() -> list:
    """千鳥支線は運行種別が「普通」のみのため、全駅が停車駅になる。"""
    return [{**st, "stops": ["普通"]} for st in CHIDORI_BRANCH_STATIONS]


def _itoi_express_times() -> dict:
    times = {}
    for (a, b), sec in ITOI_LINE_EXPRESS_RUN_TIMES_SEC.items():
        times[("急行", a, b)] = sec
    return times


# 路線ごとの定義一覧。全路線分の.oud2を一括生成する際に使う。
LINE_DEFS = [
    {
        "key": "obakyu_main",
        "line_name": "尾羽急本線",
        "dia_name": "AI生成 終日ダイヤ",
        "stations": STATIONS,
        "service_types": SERVICE_TYPES,
        "run_times_sec": RUN_TIMES_SEC,
        "express_times": {},
    },
    {
        "key": "chidori_branch",
        "line_name": "千鳥支線",
        "dia_name": "AI生成 終日ダイヤ",
        "stations": _chidori_stations_with_stops(),
        "service_types": ["普通"],
        "run_times_sec": CHIDORI_BRANCH_RUN_TIMES_SEC,
        "express_times": {},
    },
    {
        "key": "itoi_line",
        "line_name": "井問線",
        "dia_name": "AI生成 終日ダイヤ",
        "stations": ITOI_LINE_STATIONS,
        "service_types": ITOI_LINE_SERVICE_TYPES,
        "run_times_sec": ITOI_LINE_RUN_TIMES_SEC,
        "express_times": _itoi_express_times(),
    },
    {
        "key": "tozaka_monorail",
        "line_name": "東阪モノレール",
        "dia_name": "AI生成 終日ダイヤ",
        "stations": _tozaka_stations_with_stops(),
        "service_types": TOZAKA_MONORAIL_SERVICE_TYPES,
        "run_times_sec": TOZAKA_MONORAIL_RUN_TIMES_SEC,
        "express_times": _tozaka_express_times(),
    },
    {
        "key": "rapid_line",
        "line_name": "尾羽急高速線",
        "dia_name": "AI生成 終日ダイヤ",
        "stations": RAPID_LINE_STATIONS,
        "service_types": RAPID_LINE_SERVICE_TYPES,
        "run_times_sec": RAPID_LINE_RUN_TIMES_SEC,
        "express_times": RAPID_LINE_EXPRESS_RUN_TIMES_SEC,
    },
    {
        "key": "kanada_line",
        "line_name": "金田線",
        "dia_name": "AI生成 終日ダイヤ",
        "stations": KANADA_LINE_STATIONS,
        "service_types": KANADA_LINE_SERVICE_TYPES,
        "run_times_sec": KANADA_LINE_RUN_TIMES_SEC,
        "express_times": {},
    },
]


def build_oud2_for_line(line_def: dict) -> bytes:
    """LINE_DEFSの1路線ぶんの定義から、終日ダイヤの.oud2ファイルをバイト列で返す。"""
    kudari_trains, nobori_trains = build_full_day_trains(
        stations=line_def["stations"],
        run_times_sec=line_def["run_times_sec"],
        service_types=line_def["service_types"],
        express_times=line_def.get("express_times"),
    )
    text = build_oud2_file(
        line_def["line_name"], line_def["dia_name"],
        line_def["stations"], line_def["service_types"],
        kudari_trains, nobori_trains,
    )
    return text.encode("utf-8")


def build_sample_oud2(line_name: str = "尾羽急本線", dia_name: str = "AI生成 終日ダイヤ") -> bytes:
    """尾羽急本線単体の終日ダイヤの.oud2ファイルをバイト列で返す（後方互換用）。"""
    line_def = next(d for d in LINE_DEFS if d["key"] == "obakyu_main")
    return build_oud2_for_line(line_def)


def build_all_lines_zip() -> bytes:
    """全路線ぶんの終日ダイヤ.oud2ファイルを1つのzipにまとめてバイト列で返す。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for line_def in LINE_DEFS:
            data = build_oud2_for_line(line_def)
            zf.writestr(f"{line_def['key']}.oud2", data)
    return buf.getvalue()
