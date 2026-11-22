# -*- coding: utf-8 -*-
"""
運転計画（乗務員行路表の簡易版）とダイヤグラム（時刻-距離線図）を生成するモジュール。

- 運転計画: 1本の列車について、停車駅ごとの着時刻・発(通過)時刻を並べたシンプルな
  HTML表。ユーザーから提供されたサンプル画像をもとに、運転時分・車両最高速度・
  速度種別・けん引定数・制限速度・番線・記事・帳票ヘッダー（達第○号や運輸区名など）
  は省いた最小構成にしている。
- ダイヤグラム: 縦軸に駅（物理的な並び順）、横軸に時刻を取り、列車ごとに停車点を
  結んだ線を引く、いわゆる「ダイヤグラム」。Plotlyで生成し、ブラウザ側のフォントで
  描画されるようにすることで、日本語（駅名）が文字化けしない構成にしている
  （サーバー側でフォントを用意する必要がある画像生成ライブラリは使っていない）。
"""

import re

import plotly.graph_objects as go

from oud2_export import (
    LINE_DEFS,
    build_full_day_trains,
    _match_station_indices,
    _parse_time_to_sec,
    expand_generate_spec,
    resolve_line_def,
    expand_custom_dia,
    build_oud2_file,
)
from stations_data import service_color


def _find_line(line_key: str) -> dict:
    return next(d for d in LINE_DEFS if d["key"] == line_key)


def parse_line_key(text: str, default: str = "obakyu_main") -> str:
    """メッセージ中に路線名が含まれていれば、その路線のキーを返す。"""
    for line_def in LINE_DEFS:
        if line_def["line_name"] in text:
            return line_def["key"]
    return default


def parse_hour_range(text: str, default=(6, 9)):
    """「7時から10時」のような指定があれば (開始時, 終了時) を返す。なければdefault。"""
    m = re.search(r"(\d{1,2})\s*時\s*(?:から|〜|-|~)\s*(\d{1,2})\s*時", text)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if 0 <= a < 24 and 0 < b <= 24 and a < b:
            return a, b
    return default


def is_dense_schedule_request(text: str) -> bool:
    """「過密ダイヤ」のような、運転間隔を詰めた高頻度ダイヤを求める発言かどうかを判定する。"""
    return ("過密" in text) or ("高頻度" in text)


def parse_headway_sec(text: str, default: int = 120):
    """「3分間隔」のような指定があれば秒数を返す。なければdefault（デフォルト2分）。"""
    m = re.search(r"(\d{1,3})\s*分\s*(?:間隔|おき|ごと)", text)
    if m:
        minutes = int(m.group(1))
        if 1 <= minutes <= 120:
            return minutes * 60
    return default


def parse_train_number(text: str):
    """メッセージ中に列車番号らしき数字列があれば返す。"""
    m = re.search(r"(\d{4,6})", text)
    return m.group(1) if m else None


def _sec_to_hhmm(total_seconds) -> str:
    total_seconds = int(round(total_seconds))
    h, rem = divmod(total_seconds, 3600)
    m, s = divmod(rem, 60)
    if s == 0:
        return f"{h}:{m:02d}"
    return f"{h}:{m:02d}:{s:02d}"


# ---------------------------------------------------------------------------
# 運転計画（行路表の簡易版）
# ---------------------------------------------------------------------------
def build_untenkeikaku_html(line_key: str = "obakyu_main", train_number: str = None, direction: str = "Kudari"):
    """
    指定した列車1本ぶんの、停車駅・着時刻・発(通過)時刻だけのシンプルな運転計画表を
    HTMLで生成する。train_numberを指定しない場合は、その路線・方向の最初の列車を使う。
    戻り値: (HTML文字列をUTF-8エンコードしたbytes, 実際に使われた列車番号, 実際の方向)
    """
    line_def = _find_line(line_key)
    stations = line_def["stations"]
    kudari, nobori = build_full_day_trains(
        stations=stations,
        run_times_sec=line_def["run_times_sec"],
        service_types=line_def["service_types"],
        express_times=line_def.get("express_times"),
        one_way=line_def.get("one_way", False),
    )

    train = None
    used_direction = direction
    if train_number:
        for cand_direction, trains in (("Kudari", kudari), ("Nobori", nobori)):
            found = next((t for t in trains if t["train_number"] == str(train_number)), None)
            if found:
                train = found
                used_direction = cand_direction
                break

    if train is None:
        trains = kudari if used_direction == "Kudari" else nobori
        train = trains[0]

    n = len(stations)
    order = range(n) if used_direction == "Kudari" else range(n - 1, -1, -1)

    rows = []
    for idx in order:
        if idx not in train["stops"]:
            continue
        arr, dep = train["stops"][idx]
        if arr is None and dep is None:
            continue  # 通過駅はこの簡易版では省略する
        arr_str = _sec_to_hhmm(arr) if arr is not None else ""
        dep_str = _sec_to_hhmm(dep) if dep is not None else ""
        rows.append((stations[idx]["name"], arr_str, dep_str))

    service_name = line_def["service_types"][train["service_index"]]
    direction_label = "下り" if used_direction == "Kudari" else "上り"

    html_rows = "\n".join(
        f'<tr><td class="station">{name}</td><td class="time">{arr}</td><td class="time">{dep}</td></tr>'
        for name, arr, dep in rows
    )

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>運転計画 {train['train_number']}</title>
<style>
  body {{ font-family: "Hiragino Sans", "Noto Sans JP", "Yu Gothic", sans-serif; margin: 24px; color: #111; }}
  h1 {{ font-size: 20px; margin-bottom: 4px; }}
  .sub {{ color: #555; margin-bottom: 16px; }}
  .trainno {{
    font-size: 40px; font-weight: bold; text-align: center;
    border: 2px solid #000; padding: 10px; width: 260px; margin-bottom: 16px;
  }}
  table {{ border-collapse: collapse; width: 100%; max-width: 480px; }}
  th, td {{ border: 1px solid #000; padding: 6px 14px; }}
  th {{ background: #eee; text-align: center; }}
  td.station {{ text-align: left; font-weight: bold; white-space: nowrap; }}
  td.time {{ text-align: center; font-variant-numeric: tabular-nums; font-size: 18px; }}
</style>
</head>
<body>
  <h1>運転計画</h1>
  <div class="sub">{line_def['line_name']}　{direction_label}　<b style="color:{service_color(service_name)}">{service_name}</b></div>
  <div class="trainno">{train['train_number']}</div>
  <table>
    <tr><th>停車駅名</th><th>着</th><th>発(通)</th></tr>
    {html_rows}
  </table>
</body>
</html>"""
    return html.encode("utf-8"), train["train_number"], used_direction


# ---------------------------------------------------------------------------
# ダイヤグラム
# ---------------------------------------------------------------------------
_PALETTE = ["black", "red", "green", "blue", "orange", "purple", "brown", "teal"]


def build_diagram_figure(
    line_key: str = "obakyu_main", hour_start: int = 6, hour_end: int = 9, headway_sec: int = None,
):
    """
    縦軸=駅（物理的な並び順）、横軸=時刻のダイヤグラム（Plotlyの図）を作る。
    下りは実線、上りは点線で描き、種別ごとに色分けする。
    headway_secを指定すると、全種別の運転間隔をその秒数に統一する
    （「過密ダイヤ」を見たい場合に使う）。
    """
    line_def = _find_line(line_key)
    stations = line_def["stations"]
    n = len(stations)
    names = [s["name"] for s in stations]

    headways = None
    if headway_sec:
        headways = {name: headway_sec for name in line_def["service_types"]}

    kudari, nobori = build_full_day_trains(
        stations=stations,
        run_times_sec=line_def["run_times_sec"],
        service_types=line_def["service_types"],
        express_times=line_def.get("express_times"),
        one_way=line_def.get("one_way", False),
        headways=headways,
    )

    color_map = {
        name: service_color(name, i) for i, name in enumerate(line_def["service_types"])
    }

    x_min, x_max = hour_start * 3600, hour_end * 3600
    fig = go.Figure()

    def add_trains(trains: list, dash: str):
        for train in trains:
            xs, ys = [], []
            for idx in range(n):
                if idx not in train["stops"]:
                    continue
                arr, dep = train["stops"][idx]
                if arr is None and dep is None:
                    continue
                t = arr if arr is not None else dep
                xs.append(t)
                ys.append(idx)
                if arr is not None and dep is not None and dep != arr:
                    xs.append(dep)
                    ys.append(idx)
            if not xs:
                continue
            if max(xs) < x_min or min(xs) > x_max:
                continue
            service = line_def["service_types"][train["service_index"]]
            fig.add_trace(
                go.Scatter(
                    x=xs, y=ys, mode="lines",
                    line=dict(color=color_map.get(service, "black"), width=1, dash=dash),
                    name=f"{service} {train['train_number']}",
                    hoverinfo="name",
                    showlegend=False,
                    legendgroup=service,
                )
            )

    add_trains(kudari, "solid")
    add_trains(nobori, "dot")

    # 凡例（種別と色の対応）。実際に図に描かれた種別だけを出す
    drawn = {tr.legendgroup for tr in fig.data}
    for name in line_def["service_types"]:
        if name not in drawn:
            continue
        fig.add_trace(
            go.Scatter(
                x=[None], y=[None], mode="lines", name=name, legendgroup=name,
                line=dict(color=color_map[name], width=3), showlegend=True, hoverinfo="skip",
            )
        )

    tick_vals = list(range(x_min, x_max + 1, 600))
    fig.update_yaxes(
        tickmode="array", tickvals=list(range(n)), ticktext=names,
        autorange="reversed",
    )
    fig.update_xaxes(
        tickmode="array", tickvals=tick_vals,
        ticktext=[_sec_to_hhmm(v) for v in tick_vals],
        tickangle=45, range=[x_min, x_max],
    )
    dense_label = f"・運転間隔{headway_sec // 60}分に統一" if headway_sec else ""
    fig.update_layout(
        title=(
            f"{line_def['line_name']} ダイヤグラム "
            f"（{hour_start}:00〜{hour_end}:00、実線=下り・点線=上り{dense_label}）"
        ),
        height=max(500, n * 22),
        margin=dict(l=140, r=20, t=60, b=90),
        plot_bgcolor="white",
        showlegend=True,
        legend=dict(title=dict(text="種別"), orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(showgrid=True, gridcolor="#ddd")
    fig.update_yaxes(showgrid=True, gridcolor="#ddd")
    return fig


# ---------------------------------------------------------------------------
# 運転表（スタフ）
# ---------------------------------------------------------------------------
def is_untenhyou_request(text: str) -> bool:
    """「運転表にして」「スタフ作って」のような指示かどうかを判定する。"""
    return ("運転表" in text) or ("スタフ" in text)


def parse_time_unit(text: str, default: str = "sec") -> str:
    """「分単位」「秒単位」の指定があれば読み取る。なければdefault（秒単位）。"""
    if "秒単位" in text:
        return "sec"
    if "分単位" in text:
        return "min"
    return default


def _format_untenhyou_time(value, unit: str) -> str:
    sec = _parse_time_to_sec(value) if isinstance(value, str) else value
    if sec is None:
        return ""
    sec = int(round(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if unit == "min":
        return f"{h}:{m:02d}"
    return f"{h}:{m:02d}:{s:02d}"


def _resolve_train_rows(line_def: dict, train: dict, direction: str, indices: list):
    """
    DIA_JSONの停車駅（通過駅は含まれない）から、経路の始点〜終点まで全駅ぶんの行
    （駅名, 到着時刻文字列またはNone, 発車時刻文字列またはNone, 備考）を組み立てる。
    通過駅は時刻なし・備考「通過」で埋める。
    """
    stations = line_def["stations"]
    name_time = {idx: train["stops"][pos] for pos, idx in enumerate(indices)}
    lo, hi = min(indices), max(indices)
    order = range(lo, hi + 1) if direction == "Kudari" else range(hi, lo - 1, -1)

    rows = []
    for idx in order:
        name = stations[idx]["name"]
        if idx in name_time:
            stop = name_time[idx]
            rows.append((name, stop.get("arrival"), stop.get("departure"), ""))
        else:
            rows.append((name, None, None, "通過"))
    return rows


def _rows_from_internal_train(line_def: dict, train: dict, direction: str):
    """
    build_full_day_trains（内部形式、秒数ベース）で作られた列車1本から、
    運転表の行（駅名, 着時刻sec, 発時刻sec, 備考）を組み立てる。
    通過駅も含めて、経路上の全駅ぶんの行を返す。
    """
    stations = line_def["stations"]
    n = len(stations)
    order = range(n) if direction == "Kudari" else range(n - 1, -1, -1)

    rows = []
    for idx in order:
        if idx not in train["stops"]:
            continue
        arr, dep = train["stops"][idx]
        name = stations[idx]["name"]
        if arr is None and dep is None:
            rows.append((name, None, None, "通過"))
        else:
            rows.append((name, arr, dep, ""))
    return rows


def _infos_from_internal_trains(line_def: dict, kudari_trains: list, nobori_trains: list):
    """generate展開後の内部形式の列車一覧から、編成割り当て用のinfosリストを作る。"""
    infos = []
    for direction, trains in (("Kudari", kudari_trains), ("Nobori", nobori_trains)):
        for train in trains:
            rows = _rows_from_internal_train(line_def, train, direction)
            stop_rows = [r for r in rows if r[3] != "通過"]
            if not stop_rows:
                continue
            origin_idx = next(idx for idx in train["stops"] if train["stops"][idx] != (None, None))
            # 上の1行はdictの走査順に依存するため、実際の始点・終点は行の並び(rows)から取り直す
            origin_name, origin_arr, origin_dep, _ = stop_rows[0]
            terminus_name, terminus_arr, terminus_dep, _ = stop_rows[-1]

            n = len(line_def["stations"])
            order = list(range(n)) if direction == "Kudari" else list(range(n - 1, -1, -1))
            stop_indices = [idx for idx in order if idx in train["stops"] and train["stops"][idx] != (None, None)]

            infos.append(
                {
                    "train_number": str(train.get("train_number") or ""),
                    "service": line_def["service_types"][train["service_index"]],
                    "destination": terminus_name,
                    "rows": rows,
                    "origin_idx": stop_indices[0],
                    "origin_time": origin_dep if origin_dep is not None else origin_arr,
                    "terminus_idx": stop_indices[-1],
                    "terminus_time": terminus_arr if terminus_arr is not None else terminus_dep,
                    "internal": train,
                    "direction": direction,
                    "duty": train.get("duty", ""),
                }
            )
    return infos


def _annotate_refuge_notes(line_def: dict, infos: list) -> None:
    """
    運転表の「通過待ち等」の欄に、待避（通過待ち・追い越し待ち）の内容を書き込む。
    待避する列車の駅には「準急(02B-01)通過待ち」のように、追い越す列車の通過駅には
    「通過（各停 01A-01を追い越し）」のように入れる。
    """
    from oud2_export import _refuge_stations, _train_timeline

    refuge = _refuge_stations(line_def)
    run_times = line_def["run_times_sec"]
    n = len(line_def["stations"])
    by_dir = {"Kudari": [], "Nobori": []}
    for info in infos:
        if info.get("internal") is not None:
            by_dir[info["direction"]].append(info)

    for direction, group in by_dir.items():
        tls = {id(i): _train_timeline(i["internal"]["stops"], direction, run_times) for i in group}
        order = list(range(n)) if direction == "Kudari" else list(range(n - 1, -1, -1))
        notes = {}  # (id(info), idx) -> [文字列]

        def count_stops(t, lo, hi):
            return sum(1 for k, v in t["stops"].items() if lo <= k <= hi and v != (None, None))

        for s_info in group:
            s_t = s_info["internal"]
            for idx, (arr, dep) in s_t["stops"].items():
                if arr is None or dep is None or direction not in refuge.get(idx, ()):
                    continue
                if dep - arr < 60:
                    continue
                for f_info in group:
                    if f_info is s_info:
                        continue
                    f_t = f_info["internal"]
                    tl_f = tls[id(f_info)]
                    if idx not in tl_f:
                        continue
                    lo = max(min(s_t["stops"]), min(f_t["stops"]))
                    hi = min(max(s_t["stops"]), max(f_t["stops"]))
                    if lo >= hi or count_stops(f_t, lo, hi) >= count_stops(s_t, lo, hi):
                        continue
                    f_arr, f_dep = tl_f[idx]
                    if not (arr - 30 <= f_arr <= dep):
                        continue
                    passes = f_t["stops"][idx] == (None, None)
                    f_label = f"{f_info['service']}({f_info['train_number']})"
                    s_label = f"{s_info['service']} {s_info['train_number']}"
                    notes.setdefault((id(s_info), idx), []).append(
                        f"{f_label}{'通過待ち' if passes else '追い越し待ち'}"
                    )
                    if passes:
                        notes.setdefault((id(f_info), idx), []).append(f"{s_label}を追い越し")

        for info in group:
            idxs = [i for i in order if i in info["internal"]["stops"]]
            new_rows = []
            for k, row in enumerate(info["rows"]):
                name, arr, dep, note = row
                extra = notes.get((id(info), idxs[k])) if k < len(idxs) else None
                if extra:
                    note = (note + " " if note else "") + "、".join(extra) if note != "通過" else "通過（" + "、".join(extra) + "）"
                new_rows.append((name, arr, dep, note))
            info["rows"] = new_rows


def assign_formations(infos: list, min_turnback_sec: int = 180):
    """
    編成（運用）ごとの列車グループを返す。全列車に運用番号（"duty"）が付いていれば、その運用番号で
    分ける（運用番号の順）。付いていなければ、到着駅＝次の発車駅・折り返し時間の条件から推定する。
    """
    if infos and all(i.get("duty") for i in infos):
        groups = {}
        for i in infos:
            groups.setdefault(i["duty"], []).append(i)
        return [
            sorted(trains, key=lambda x: x["origin_time"] if x["origin_time"] is not None else 0)
            for _, trains in sorted(groups.items())
        ]
    return _assign_formations(infos, min_turnback_sec=min_turnback_sec)


def _assign_formations(infos: list, min_turnback_sec: int = 180):
    """
    到着駅＝次の列車の発車駅、かつ折り返しに最低min_turnback_sec秒あることを条件に、
    列車どうしを同じ「編成」としてつなげる（貪欲法による簡易的な推定）。
    """
    infos_sorted = sorted(infos, key=lambda x: x["origin_time"] if x["origin_time"] is not None else 0)

    formations = []  # [[info, info, ...], ...]
    available = []   # [(station_idx, avail_time, formation_index), ...]

    for info in infos_sorted:
        best_i, best_avail = None, None
        if info["origin_time"] is not None:
            for i, (st_idx, avail_time, f_idx) in enumerate(available):
                if st_idx != info["origin_idx"] or avail_time is None:
                    continue
                if avail_time + min_turnback_sec <= info["origin_time"]:
                    if best_avail is None or avail_time > best_avail:
                        best_avail, best_i = avail_time, i

        if best_i is not None:
            _, _, f_idx = available[best_i]
            formations[f_idx].append(info)
            available[best_i] = (info["terminus_idx"], info["terminus_time"], f_idx)
        else:
            f_idx = len(formations)
            formations.append([info])
            available.append((info["terminus_idx"], info["terminus_time"], f_idx))

    return formations


def build_untenhyou_html(custom_dia: dict, time_unit: str = "sec", min_turnback_sec: int = 180):
    """
    チャットで実際に作られたダイヤ（DIA_JSON）から、編成（運用）単位でつなげた
    運転表（スタフ）のHTMLを1ファイルで生成する。画面には「列車番号・種別・行き先」の
    ヘッダーと、「駅名・着時刻・発時刻・通過待ち等」の表を列車ごとに並べ、印刷時に
    1列車＝1ページで改ページされるようにしている（番線の列は含めない）。

    戻り値: (HTML文字列をUTF-8エンコードしたbytes, 編成数, 列車数)
    """
    # 複数路線の直通ダイヤ（"route"あり）にも対応する
    line_def = resolve_line_def(custom_dia)

    if custom_dia.get("generate"):
        kudari_trains, nobori_trains = expand_generate_spec(custom_dia["generate"], line_def)
        infos = _infos_from_internal_trains(line_def, kudari_trains, nobori_trains)
        try:
            _annotate_refuge_notes(line_def, infos)
        except Exception:
            pass  # 備考の追加に失敗しても、運転表そのものは出す
        formations = assign_formations(infos, min_turnback_sec=min_turnback_sec)
        return _render_untenhyou_html(formations, time_unit), len(formations), len(infos)

    infos = []
    for train in custom_dia.get("trains", []):
        direction = train.get("direction") if train.get("direction") in ("Kudari", "Nobori") else "Kudari"
        stops = train.get("stops") or []
        if not stops:
            continue
        try:
            indices = _match_station_indices(line_def["stations"], train, direction)
        except ValueError:
            continue

        rows = _resolve_train_rows(line_def, train, direction, indices)
        origin_time = _parse_time_to_sec(stops[0].get("departure") or stops[0].get("arrival"))
        terminus_time = _parse_time_to_sec(stops[-1].get("arrival") or stops[-1].get("departure"))

        infos.append(
            {
                "train_number": str(train.get("train_number") or ""),
                "service": train.get("service", ""),
                "destination": rows[-1][0],
                "rows": rows,
                "origin_idx": indices[0],
                "origin_time": origin_time,
                "terminus_idx": indices[-1],
                "terminus_time": terminus_time,
                "duty": str(train.get("duty") or "").strip(),
            }
        )

    formations = assign_formations(infos, min_turnback_sec=min_turnback_sec)
    return _render_untenhyou_html(formations, time_unit), len(formations), len(infos)


def build_formation_oud2_zip(custom_dia: dict, min_turnback_sec: int = 180):
    """
    チャットで作られたダイヤ（DIA_JSON）を、編成（運用）ごとに別々の.oud2ファイルへ分け、
    1つのzipにまとめて返す。1ファイルには、その編成が走る列車（往復すべて）だけが入る。

    編成の分け方: 全列車に運用番号（"duty"）があればそれで分け、なければ運転表と同じ推定
    （到着駅＝次の発車駅、折り返し時間min_turnback_sec秒以上）でつなげる。

    戻り値: (zipのbytes, ファイル数, 列車数, ファイル名のリスト)
    """
    import io
    import zipfile

    line_def, kudari_trains, nobori_trains = expand_custom_dia(custom_dia)
    infos = _infos_from_internal_trains(line_def, kudari_trains, nobori_trains)
    if not infos:
        raise ValueError("列車が1本もないため、.oud2に分けられません。")
    formations = assign_formations(infos, min_turnback_sec=min_turnback_sec)

    buf = io.BytesIO()
    names = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f_no, trains_in_formation in enumerate(formations, start=1):
            duty = trains_in_formation[0].get("duty") or ""
            label = duty if duty else f"編成{f_no:02d}"
            file_name = f"{label}.oud2"
            if file_name in names:  # 念のため重複を避ける
                file_name = f"{label}_{f_no:02d}.oud2"
            ks = [i["internal"] for i in trains_in_formation if i["direction"] == "Kudari"]
            ns = [i["internal"] for i in trains_in_formation if i["direction"] == "Nobori"]
            ks.sort(key=lambda t: min((v for pair in t["stops"].values() for v in pair if v is not None), default=0))
            ns.sort(key=lambda t: min((v for pair in t["stops"].values() for v in pair if v is not None), default=0))
            text = build_oud2_file(
                line_def["line_name"], label, line_def["stations"], line_def["service_types"], ks, ns
            )
            zf.writestr(file_name, text.encode("utf-8"))
            names.append(file_name)
    return buf.getvalue(), len(formations), len(infos), names


def _render_untenhyou_html(formations: list, time_unit: str = "sec") -> bytes:
    """編成ごとにグループ化されたinfosのリストから、運転表の最終的なHTML(bytes)を組み立てる。"""
    sheets = []
    for f_idx, trains_in_formation in enumerate(formations, start=1):
        for duty_idx, info in enumerate(trains_in_formation, start=1):
            rows_html = "\n".join(
                f'<tr><td class="station">{name}</td>'
                f'<td class="time">{_format_untenhyou_time(arr, time_unit)}</td>'
                f'<td class="time">{_format_untenhyou_time(dep, time_unit)}</td>'
                f'<td class="note">{note}</td></tr>'
                for name, arr, dep, note in info["rows"]
            )
            sheets.append(f"""<section class="sheet">
  <div class="formation-label">編成{f_idx} - 第{duty_idx}運用</div>
  <table class="headertable">
    <tr><th>列車番号</th><th>種別</th><th>行き先</th></tr>
    <tr><td class="big">{info['train_number']}</td><td class="big" style="color:{service_color(info['service'])}">{info['service']}</td><td class="big">{info['destination']}</td></tr>
  </table>
  <table class="maintable">
    <tr><th>駅名</th><th>着時刻</th><th>発時刻</th><th>通過待ち等</th></tr>
    {rows_html}
  </table>
</section>""")

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>運転表</title>
<style>
  body {{ font-family: "Hiragino Sans", "Noto Sans JP", "Yu Gothic", sans-serif; margin: 0; color: #111; }}
  .sheet {{
    page-break-after: always; break-after: page;
    padding: 24px; box-sizing: border-box;
  }}
  .sheet:last-child {{ page-break-after: auto; break-after: auto; }}
  .formation-label {{ font-size: 14px; color: #555; margin-bottom: 6px; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 10px; }}
  th, td {{ border: 1px solid #000; padding: 6px 8px; text-align: center; }}
  th {{ background: #eee; }}
  .headertable .big {{ font-size: 22px; font-weight: bold; padding: 10px; }}
  .maintable td.station {{ text-align: left; font-weight: bold; white-space: nowrap; }}
  .maintable td.time {{ font-variant-numeric: tabular-nums; }}
  @media print {{
    .sheet {{ padding: 12mm; }}
  }}
</style>
</head>
<body>
{''.join(sheets)}
</body>
</html>"""
    return html.encode("utf-8")
