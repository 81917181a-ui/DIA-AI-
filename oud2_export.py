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
  - 空文字列: その列車はこの駅を通らない（経路の始点より前・終点より後）
  - "<本線番号>;<時刻>$<番線インデックス>"          … 起点駅（発のみ）
  - "<本線番号>;<時刻>/$<番線インデックス>"          … 終点駅（着のみ）
  - "<本線番号>;<着時刻>/<発時刻>$<番線インデックス>" … 中間駅で停車
  - "<本線番号>$<番線インデックス>"                  … 通過（時刻は記録しない）

時刻はH[H]MM[SS]形式（秒が0の場合は秒部分を省略）。

下り(Kudari)はEki.の宣言順（先頭の駅→末尾の駅）でエントリを並べ、
上り(Nobori)は逆順（末尾の駅→先頭の駅）でエントリを並べる
（実データを解析して確認した規則）。

列車の分割併合など、より高度な機能には対応していない。
"""

import re

from stations_data import STATIONS, RUN_TIMES_SEC, SERVICE_TYPES

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
    m = re.search(r"面(\d+)線", facilities)
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


def _append_eki_blocks(lines: list):
    for station in STATIONS:
        track_count = _parse_track_count(station["facilities"])
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


def _append_ressyasyubetsu_blocks(lines: list):
    for i, name in enumerate(SERVICE_TYPES):
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


def _station_platform_index(station_idx: int, direction: str) -> int:
    """
    駅の設備（番線数）をもとに、方向ごとに使う番線インデックス（0始まり）を決める。
    下りは0番目、上りは2番線以上ある駅なら1番目、1線しかない駅は0番目を使う。
    """
    track_count = _parse_track_count(STATIONS[station_idx]["facilities"])
    if direction == "Kudari":
        return 0
    return 1 if track_count > 1 else 0


def _ekijikoku_field(direction: str, stops: dict) -> str:
    """
    stops: {駅インデックス(0-based, STATIONSの並び順): (着時刻sec or None, 発時刻sec or None)}
           通過する駅は (None, None) を、経路に含まれない駅はキー自体を省略する。
    """
    main_track = "1" if direction == "Kudari" else "2"
    n = len(STATIONS)
    order = range(n) if direction == "Kudari" else range(n - 1, -1, -1)

    entries = []
    for idx in order:
        if idx not in stops:
            entries.append("")
            continue
        arr, dep = stops[idx]
        platform = _station_platform_index(idx, direction)
        if arr is None and dep is None:
            # 通過駅は「経路に含まれない」場合と同じ空欄で表現する
            # （main_track$platform 形式で表現しようとしたところ、OuDiaSecondで
            #  「停車だが時刻未設定」という壊れた状態として解釈されたため）
            entries.append("")
        elif arr is None and dep is not None:
            entries.append(f"{main_track};{format_oud2_time(dep)}${platform}")  # 起点
        elif arr is not None and dep is None:
            entries.append(f"{main_track};{format_oud2_time(arr)}/${platform}")  # 終点
        else:
            entries.append(
                f"{main_track};{format_oud2_time(arr)}/{format_oud2_time(dep)}${platform}"
            )  # 中間停車
    return ",".join(entries)


def _append_ressya(lines: list, direction: str, service_index: int, train_number: str, stops: dict):
    lines.append("Ressya.")
    lines.append(f"Houkou={direction}")
    lines.append(f"Syubetsu={service_index}")
    if train_number:
        lines.append(f"Ressyabangou={train_number}")
    lines.append(f"EkiJikoku={_ekijikoku_field(direction, stops)}")
    lines.append(".")


def _append_dia_block(lines: list, dia_name: str, kudari_trains: list, nobori_trains: list):
    lines.append("Dia.")
    lines.append(f"DiaName={dia_name}")
    lines.append("Kudari.")
    for t in kudari_trains:
        _append_ressya(lines, "Kudari", t["service_index"], t.get("train_number", ""), t["stops"])
    lines.append(".")
    lines.append("Nobori.")
    for t in nobori_trains:
        _append_ressya(lines, "Nobori", t["service_index"], t.get("train_number", ""), t["stops"])
    lines.append(".")
    lines.append(".")


def build_oud2_file(line_name: str, dia_name: str, kudari_trains: list, nobori_trains: list) -> str:
    """
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
    _append_eki_blocks(lines)
    _append_ressyasyubetsu_blocks(lines)
    _append_dia_block(lines, dia_name, kudari_trains, nobori_trains)
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


def _build_one_train_stops(service: str, direction: str, start_sec: int, dwell_sec: int) -> dict:
    """指定した種別・方向・始発時刻の列車1本ぶんの{駅インデックス: (着, 発)}を計算する。"""
    n = len(STATIONS)
    stops = {}
    t = start_sec
    station_order = range(n) if direction == "Kudari" else range(n - 1, -1, -1)
    prev_idx = None
    for pos, i in enumerate(station_order):
        station = STATIONS[i]
        if pos > 0:
            seg_index = min(i, prev_idx)
            t += RUN_TIMES_SEC[seg_index]
        stops_here = service in station["stops"]
        if not stops_here:
            stops[i] = (None, None)
        elif pos == 0:
            stops[i] = (None, t)
        elif pos == n - 1:
            stops[i] = (t, None)
        else:
            arr = t
            dep = t + dwell_sec
            stops[i] = (arr, dep)
            t = dep
        prev_idx = i
    return stops


def build_full_day_trains(
    start_sec: int = OPERATION_START_SEC,
    end_sec: int = OPERATION_END_SEC,
    dwell_sec: int = DEFAULT_DWELL_SEC,
    headways: dict = None,
):
    """
    種別・方向ごとに、始発から終電まで運転間隔どおりに列車を並べた終日ダイヤを生成する。
    """
    headways = headways or DEFAULT_HEADWAY_SEC
    kudari_trains = []
    nobori_trains = []

    for service_index, service in enumerate(SERVICE_TYPES):
        headway = headways.get(service, 20 * 60)

        seq = 1
        t = start_sec
        while t < end_sec:
            stops = _build_one_train_stops(service, "Kudari", t, dwell_sec)
            train_number = f"{service_index + 1}0{seq:03d}"
            kudari_trains.append(
                {"service_index": service_index, "train_number": train_number, "stops": stops}
            )
            seq += 1
            t += headway

        seq = 1
        t = start_sec
        while t < end_sec:
            stops = _build_one_train_stops(service, "Nobori", t, dwell_sec)
            train_number = f"{service_index + 1}5{seq:03d}"
            nobori_trains.append(
                {"service_index": service_index, "train_number": train_number, "stops": stops}
            )
            seq += 1
            t += headway

    return kudari_trains, nobori_trains


def build_representative_trains(start_sec: int = DEFAULT_START_SEC, dwell_sec: int = DEFAULT_DWELL_SEC):
    """
    種別ごとに、全線を走る下り・上り列車を1本ずつだけ生成する（軽量版）。
    """
    kudari_trains, nobori_trains = build_full_day_trains(
        start_sec=start_sec,
        end_sec=start_sec + 1,
        dwell_sec=dwell_sec,
        headways={name: 10 ** 9 for name in SERVICE_TYPES},
    )
    return kudari_trains, nobori_trains


def build_sample_oud2(line_name: str = "尾羽急本線", dia_name: str = "AI生成 終日ダイヤ") -> bytes:
    """始発から終電まで、種別ごとの運転間隔どおりに並んだ終日ダイヤの.oud2ファイルをバイト列で返す。"""
    kudari_trains, nobori_trains = build_full_day_trains()
    text = build_oud2_file(line_name, dia_name, kudari_trains, nobori_trains)
    return text.encode("utf-8")
