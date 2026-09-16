"""Turn the real 2026 British GP laps into the numbers the simulator uses (data/race_model.json).

Every value is tagged "data" (measured from the laps) or "hand" (set by us, with the reason),
so we can defend each number in the presentation.

Usage (from the project root, after tools/extract_race_data.py):
    python tools/fit_model.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REAL_LAPS = 52
SIM_LAPS = 20
SCALE = REAL_LAPS / SIM_LAPS  # a 20-lap race must "wear" like the real 52-lap race


def load_laps():
    laps = pd.read_csv(DATA / "silverstone_2026_laps.csv", dtype={"track_status": str})
    return laps.sort_values(["driver", "lap"])


def fit_pace(laps):
    """Least squares: lap_time = driver_intercept + fuel*lap + compound_offset + compound_wear*tyre_age."""
    clean = laps[laps["clean"] & (laps["lap"] > 1) & (laps["lap"] < 47)].copy()
    clean = clean[clean["lap_time_s"] < clean.groupby("driver")["lap_time_s"].transform("median") + 2.0]  # drop traffic laps
    drivers = sorted(clean["driver"].unique())
    compounds = ["SOFT", "MEDIUM", "HARD"]
    rows = []
    for r in clean.itertuples():
        rows.append([float(r.driver == d) for d in drivers] + [r.lap]
                    + [float(r.compound == c) for c in compounds[1:]]
                    + [r.tyre_age if r.compound == c else 0.0 for c in compounds])
    coef, *_ = np.linalg.lstsq(np.array(rows), clean["lap_time_s"].to_numpy(), rcond=None)
    n = len(drivers)
    base = float(np.median(coef[:n]))
    return {
        "laps_used": int(len(clean)),
        "laps_per_compound": clean["compound"].value_counts().to_dict(),
        "base_lap_s": base,
        "driver_offset_s": {d: round(float(c) - base, 3) for d, c in zip(drivers, coef[:n])},
        "fuel_s_per_lap": float(coef[n]),
        "wear_s_per_lap": dict(zip(compounds, map(float, coef[n + 3:n + 6]))),
    }


def green_pit_loss(laps):
    """Time lost by a stop = in-lap + out-lap - 2 x the driver's normal lap, green-flag stops only."""
    normal = laps[laps["clean"] & (laps["lap"] < 47)].groupby("driver")["lap_time_s"].median()
    losses = []
    for driver, g in laps.groupby("driver"):
        g = g.set_index("lap")
        for lap in g.index[g["pit_in"]]:
            if lap + 1 not in g.index or driver not in normal:
                continue
            both = g.loc[[lap, lap + 1]]
            if both["lap_time_s"].isna().any() or not set("".join(both["track_status"])) <= {"1", "2"}:
                continue
            losses.append(both["lap_time_s"].sum() - 2 * normal[driver])
    return float(np.median(losses)), len(losses)


def main():
    laps = load_laps()
    fit = fit_pace(laps)
    pit_loss, pit_n = green_pit_loss(laps)
    medium_wear = fit["wear_s_per_lap"]["MEDIUM"]

    model = {
        "race": {"laps": SIM_LAPS, "real_laps": REAL_LAPS, "scale": round(SCALE, 2),
                 "note": "20 laps instead of 52; wear and fuel are multiplied by 52/20 so strategy matters the same way"},
        "base_lap_s": {"value": round(fit["base_lap_s"], 2), "source": "data", "note": "median driver pace on clean laps"},
        "driver_pace_offset_s": {"value": fit["driver_offset_s"], "source": "data",
                                 "note": "each driver's pace compared with the median driver (negative = faster)"},
        "fuel_s_per_lap": {"value": round(fit["fuel_s_per_lap"] * SCALE, 3), "source": "data",
                           "note": f"real race {fit['fuel_s_per_lap']:.3f} s/lap, scaled"},
        "tyres": {
            "MEDIUM": {"offset_s": 0.0, "wear_s_per_lap": round(medium_wear * SCALE, 3), "life_laps": 12, "source": "data",
                       "note": f"real race {medium_wear:.3f} s/lap from {fit['laps_per_compound'].get('MEDIUM', 0)} clean laps, scaled"},
            "SOFT": {"offset_s": -0.6, "wear_s_per_lap": round(2.0 * medium_wear * SCALE, 3), "life_laps": 7, "source": "hand",
                     "note": f"only {fit['laps_per_compound'].get('SOFT', 0)} clean Soft laps; faster than Medium, wears about 2x"},
            "HARD": {"offset_s": 0.4, "wear_s_per_lap": round(0.6 * medium_wear * SCALE, 3), "life_laps": 18, "source": "hand",
                     "note": "Hard and Medium pace cannot be separated in this race; slower than Medium, wears about 0.6x"},
            "WET": {"offset_s": 2.5, "wear_s_per_lap": round(medium_wear * SCALE, 3), "life_laps": 15, "source": "hand",
                    "note": "the real race was dry; used only after the rain command"},
        },
        "pit_loss_s": {"value": round(pit_loss, 1), "source": "data", "note": f"median of {pit_n} green-flag stops"},
        "safety_car": {"laps": 3, "lap_time_factor": 1.4, "pit_loss_s": 10.0, "source": "hand"},
        "rain": {"dry_tyre_penalty_s": 6.0, "wet_tyre_on_dry_track_penalty_s": 3.0, "source": "hand"},
        "traffic": {"within_s": 1.0, "penalty_s": 0.3, "overtake_min_advantage_s": 0.5, "source": "hand"},
        "lap_noise_s": {"value": 0.15, "source": "hand"},
        "raw_fit": fit,
    }
    (DATA / "race_model.json").write_text(json.dumps(model, indent=2))
    print(json.dumps({k: v for k, v in model.items() if k != "raw_fit"}, indent=2))


if __name__ == "__main__":
    main()
