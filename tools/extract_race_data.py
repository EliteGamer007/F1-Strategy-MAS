"""One-off data preparation for F1-Strategy-MAS.

Downloads (or reads from an existing FastF1 cache) the 2026 British Grand Prix
race and writes small CSV/JSON files into data/. The simulator only ever reads
data/, so nobody else needs FastF1, the cache, or the F1-Telemetry-Analysis app.

Usage (from the project root):
    pip install fastf1
    python tools/extract_race_data.py
    python tools/extract_race_data.py --cache "D:/some/other/fastf1/cache"
"""
import argparse
import json
import logging
from pathlib import Path

import fastf1
import numpy as np
import pandas as pd

YEAR = 2026
EVENT = "British Grand Prix"
PREFIX = "silverstone_2026"

# The 4 teams in the simulation, in FastF1's team naming.
TEAMS = {
    "McLaren": "McLaren",
    "Ferrari": "Ferrari",
    "Red Bull Racing": "Red Bull",
    "Mercedes": "Mercedes",
}

# Demo settings (the demo does not copy the real race exactly).
# Hidden tyre-wear level per driver (LOW / NORMAL / HIGH): PIA is HIGH so his tyre report
# changes McLaren's plan; everyone else is NORMAL.
DEMO_WEAR = {"PIA": "HIGH"}
# Different starting tyres so teams need different stop laps (everyone started on Medium in the real race).
DEMO_START_TYRE = {"ANT": "MEDIUM", "LEC": "MEDIUM", "HAM": "HARD", "RUS": "SOFT",
                   "HAD": "MEDIUM", "NOR": "HARD", "VER": "SOFT", "PIA": "MEDIUM"}

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DEFAULT_CACHE = ROOT.parent / "F1-Telemetry-Analysis" / "cache"  # reuse the existing download if present


def rotate(xy, angle):
    rot = np.array([[np.cos(angle), np.sin(angle)], [-np.sin(angle), np.cos(angle)]])
    return np.matmul(xy, rot)


def track_and_corners(session, reference_dir):
    """Same method as the F1-Telemetry-Analysis track map: fastest lap's X/Y, rotated to the official angle.

    Corner positions and the rotation angle come from the MultiViewer API. If that API is unreachable,
    fall back to a previously generated Silverstone layout (same circuit, same coordinate system):
    find the rotation that best overlays our lap on it and snap its corners onto our lap.
    """
    tel = session.laps.pick_fastest().get_telemetry()
    raw = tel.loc[:, ("X", "Y")].to_numpy()
    distance = tel["Distance"].to_numpy()

    try:
        info = session.get_circuit_info()
    except Exception as err:  # noqa: BLE001 - any network failure means "use the fallback"
        print(f"Circuit info API unavailable ({type(err).__name__}); using reference layout in {reference_dir}")
        return track_from_reference(raw, distance, reference_dir)

    angle = info.rotation / 180 * np.pi
    xy = rotate(raw, angle)
    track = pd.DataFrame({"x": xy[:, 0], "y": xy[:, 1], "distance": distance})
    rows = []
    for _, c in info.corners.iterrows():
        offset = rotate(np.array([[500, 0]]), c["Angle"] / 180 * np.pi)[0]
        corner = rotate(np.array([[c["X"], c["Y"]]]), angle)[0]
        label = rotate(np.array([[c["X"] + offset[0], c["Y"] + offset[1]]]), angle)[0]
        rows.append({
            "number": int(c["Number"]), "letter": c["Letter"] or "", "distance": float(c["Distance"]),
            "x": corner[0], "y": corner[1], "label_x": label[0], "label_y": label[1],
        })
    return track, pd.DataFrame(rows), {"corners_source": "MultiViewer circuit info", "rotation_deg": float(info.rotation)}


def track_from_reference(raw, distance, reference_dir):
    from scipy.spatial import cKDTree

    ref_track = pd.read_csv(Path(reference_dir) / "British Grand Prix_2025_track_layout.csv")
    ref_corners = pd.read_csv(Path(reference_dir) / "British Grand Prix_2025_corners.csv").fillna({"Letter": ""})
    tree = cKDTree(ref_track[["x", "y"]].to_numpy())

    def misfit(deg):
        return tree.query(rotate(raw, deg / 180 * np.pi))[0].mean()

    coarse = min(np.arange(0, 360, 1.0), key=misfit)
    best = min(np.arange(coarse - 1, coarse + 1, 0.05), key=misfit)
    xy = rotate(raw, best / 180 * np.pi)
    track = pd.DataFrame({"x": xy[:, 0], "y": xy[:, 1], "distance": distance})

    lap_tree = cKDTree(xy)
    rows = []
    for _, c in ref_corners.iterrows():
        _, idx = lap_tree.query([c["x"], c["y"]])
        rows.append({
            "number": int(c["Number"]), "letter": c["Letter"], "distance": float(distance[idx]),
            "x": c["x"], "y": c["y"], "label_x": c["label_x"], "label_y": c["label_y"],
        })
    meta = {
        "corners_source": "F1-Telemetry-Analysis British Grand Prix 2025 layout, snapped onto the 2026 lap",
        "rotation_deg": round(float(best), 2),
        "mean_overlay_error_m": round(float(misfit(best)) / 10, 2),  # FastF1 X/Y units are 1/10 m
    }
    return track, pd.DataFrame(rows).sort_values("distance"), meta


def lap_table(session):
    laps = session.laps
    out = pd.DataFrame({
        "driver": laps["Driver"],
        "team": laps["Team"],
        "lap": laps["LapNumber"].astype(int),
        "lap_time_s": laps["LapTime"].dt.total_seconds().round(3),
        "compound": laps["Compound"],
        "tyre_age": laps["TyreLife"],
        "stint": laps["Stint"],
        "pit_in": laps["PitInTime"].notna(),
        "pit_out": laps["PitOutTime"].notna(),
        "track_status": laps["TrackStatus"],
        "position": laps["Position"],
        "accurate": laps["IsAccurate"],
    })
    # A "clean" lap is usable for fitting tyre wear: green flag, no pit stop, accurate timing.
    out["clean"] = (out["track_status"] == "1") & ~out["pit_in"] & ~out["pit_out"] & out["accurate"] & out["lap_time_s"].notna()
    return out


def track_status_periods(laps):
    """Laps run under Safety Car (4) or Virtual Safety Car (6/7), from the race leader's laps."""
    leader = laps[laps["position"] == 1].sort_values("lap")
    periods = []
    for code, name in [("4", "SAFETY_CAR"), ("6", "VSC"), ("7", "VSC_ENDING")]:
        flagged = leader[leader["track_status"].fillna("").str.contains(code)]["lap"].tolist()
        if flagged:
            periods.append({"status": name, "laps": flagged})
    return periods


def teams_json(session):
    res = session.results
    teams = []
    for fastf1_name, short in TEAMS.items():
        sub = res[res["TeamName"] == fastf1_name].sort_values("GridPosition")
        teams.append({
            "name": short,
            "color": "#" + str(sub["TeamColor"].iloc[0]),
            "drivers": [
                {
                    "code": r["Abbreviation"],
                    "name": r["LastName"],
                    "number": str(r["DriverNumber"]),
                    "real_grid": int(r["GridPosition"]) if pd.notna(r["GridPosition"]) else None,
                    "real_finish": int(r["Position"]) if pd.notna(r["Position"]) else None,
                    "wear_level": DEMO_WEAR.get(r["Abbreviation"], "NORMAL"),
                    "start_tyre": DEMO_START_TYRE[r["Abbreviation"]],
                }
                for _, r in sub.iterrows()
            ],
        })
    return teams


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", default=str(DEFAULT_CACHE if DEFAULT_CACHE.exists() else ROOT / ".fastf1_cache"))
    parser.add_argument("--reference", default=str(ROOT.parent / "F1-Telemetry-Analysis" / "data"),
                        help="folder with a saved Silverstone layout, used only if the circuit info API is unreachable")
    args = parser.parse_args()

    logging.getLogger("fastf1").setLevel(logging.WARNING)
    Path(args.cache).mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(args.cache)
    DATA.mkdir(exist_ok=True)

    session = fastf1.get_session(YEAR, EVENT, "R")
    session.load(laps=True, telemetry=True, weather=True, messages=True)

    track, corners, track_meta = track_and_corners(session, args.reference)
    laps = lap_table(session)
    weather = session.weather_data

    track.to_csv(DATA / f"{PREFIX}_track.csv", index=False)
    corners.to_csv(DATA / f"{PREFIX}_corners.csv", index=False)
    laps.to_csv(DATA / f"{PREFIX}_laps.csv", index=False)
    (DATA / "teams.json").write_text(json.dumps(teams_json(session), indent=2))

    clean = laps[laps["clean"]]
    summary = {
        "event": f"{YEAR} {EVENT}",
        "date": str(session.event["EventDate"].date()),
        "total_laps": int(laps["lap"].max()),
        "lap_length_m": round(float(track["distance"].max()), 1),
        "median_clean_lap_s": round(float(clean["lap_time_s"].median()), 3),
        "compounds_used": laps["compound"].value_counts().to_dict(),
        "rainfall": bool(weather["Rainfall"].any()),
        "air_temp_c": round(float(weather["AirTemp"].mean()), 1),
        "track_temp_c": round(float(weather["TrackTemp"].mean()), 1),
        "neutralised_laps": track_status_periods(laps),
        "track": track_meta,
        "source": f"FastF1 {fastf1.__version__}",
    }
    (DATA / f"{PREFIX}_summary.json").write_text(json.dumps(summary, indent=2))

    print(json.dumps(summary, indent=2))
    for f in sorted(DATA.iterdir()):
        print(f"{f.name:40s} {f.stat().st_size / 1024:8.1f} KB")


if __name__ == "__main__":
    main()
