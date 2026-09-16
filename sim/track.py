"""Silverstone geometry: where a car is for a given distance, the long straights and the pit lane."""
import numpy as np
import pandas as pd

from sim.model import DATA

STEP_M = 5.0             # the racing line is resampled every 5 m
STRAIGHT_MIN_M = 580.0   # a gap between corners longer than this counts as an overtaking straight
PIT_ENTRY_M = 5680.0     # just after Turn 18, at the start of the main straight
PIT_EXIT_M = 420.0       # just before Turn 1
PIT_BOX_M = 20.0         # the garages sit right after the finish line
PIT_OFFSET = 450.0       # drawing offset of the pit lane from the track (map units = 1/10 m)
PIT_BLEND_M = 80.0       # distance over which the pit lane splits from / joins the track


class Track:
    def __init__(self):
        raw = pd.read_csv(DATA / "silverstone_2026_track.csv")
        corners = pd.read_csv(DATA / "silverstone_2026_corners.csv").sort_values("distance")
        self.length = float(raw["distance"].max())

        # The recorded lap overlaps its start by a few metres: drop those points, close the loop,
        # then resample to even spacing so distance -> position is a simple lookup.
        pts = raw[["x", "y"]].to_numpy()
        while np.dot(pts[-1] - pts[0], pts[1] - pts[0]) > 0:
            pts = pts[:-1]
        pts = np.vstack([pts, pts[:1]])
        arc = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(pts, axis=0).T))])
        arc *= self.length / arc[-1]
        self.s = np.arange(0.0, self.length, STEP_M)
        self.x = np.interp(self.s, arc, pts[:, 0])
        self.y = np.interp(self.s, arc, pts[:, 1])

        self.speed_weight = self._speed_weight()
        # Seconds-per-metre shape of a lap: a car with lap time T moves at (lap_integral / T) * speed_weight m/s.
        self.lap_integral = float(np.sum(STEP_M / self.speed_weight))

        self.corners = corners
        d = corners["distance"].to_numpy()
        gaps = (np.roll(d, -1) - d) % self.length
        self.straights = [(float(a), float((a + g) % self.length)) for a, g in zip(d, gaps) if g > STRAIGHT_MIN_M]

        self.pit_side = self._outside_normal_sign()

    # ------------------------------------------------------------------ geometry
    def _index(self, d):
        return int((d % self.length) / STEP_M) % len(self.s)

    def _speed_weight(self):
        """Relative speed along the lap: slower where the line bends sharply (curvature from heading change)."""
        x, y = self.x / 10.0, self.y / 10.0  # metres
        heading = np.arctan2(np.roll(y, -1) - y, np.roll(x, -1) - x)
        turn = np.abs(np.angle(np.exp(1j * (np.roll(heading, -1) - heading)))) / STEP_M
        window = 12  # 60 m smoothing
        turn = np.convolve(np.concatenate([turn[-window:], turn, turn[:window]]), np.ones(window) / window, "same")[window:-window]
        return 1.0 / (1.0 + 45.0 * turn)

    def _normal(self, i):
        j = (i + 1) % len(self.s)
        dx, dy = self.x[j] - self.x[i - 1], self.y[j] - self.y[i - 1]
        n = np.hypot(dx, dy)
        return -dy / n, dx / n

    def _outside_normal_sign(self):
        """+1 or -1 so that the pit lane is drawn on the outside of the circuit.

        The left-hand normal points inside the loop when the lap runs anticlockwise (positive shoelace area).
        """
        area = np.sum(self.x * np.roll(self.y, -1) - np.roll(self.x, -1) * self.y)
        return -1.0 if area > 0 else 1.0

    def xy(self, d):
        i = self._index(d)
        return float(self.x[i]), float(self.y[i])

    def speed_weight_at(self, d):
        return float(self.speed_weight[self._index(d)])

    # ------------------------------------------------------------------ straights and pit lane
    def straight_at(self, d):
        """Index of the long straight at lap distance d, or None."""
        d %= self.length
        return next((i for i, (a, b) in enumerate(self.straights) if ((a <= d <= b) if a < b else (d >= a or d <= b))), None)

    def pit_progress(self, d):
        """Metres travelled along the pit lane for lap distance d (0 at the entry)."""
        return (d % self.length - PIT_ENTRY_M) % self.length

    @property
    def pit_length(self):
        return (PIT_EXIT_M - PIT_ENTRY_M) % self.length

    def in_pit_zone(self, d):
        return self.pit_progress(d) <= self.pit_length

    def pit_xy(self, d):
        """Position on the pit lane, which runs beside the track and splits off / rejoins smoothly."""
        p = self.pit_progress(d)
        blend = min(1.0, p / PIT_BLEND_M, (self.pit_length - p) / PIT_BLEND_M)
        i = self._index(d)
        nx, ny = self._normal(i)
        off = self.pit_side * PIT_OFFSET * max(0.0, blend)
        return float(self.x[i] + nx * off), float(self.y[i] + ny * off)

    def segment_time(self, start, length, lap_time):
        """Seconds a car on lap time `lap_time` needs to cover `length` metres from lap distance `start`."""
        idx = (np.arange(int(length / STEP_M)) + self._index(start)) % len(self.s)
        return float(np.sum(STEP_M / self.speed_weight[idx])) * lap_time / self.lap_integral

    def nearest_corner(self, d):
        gaps = np.abs(((self.corners["distance"].to_numpy() - d % self.length) + self.length / 2) % self.length - self.length / 2)
        return int(self.corners["number"].iloc[int(np.argmin(gaps))])

    def to_json(self):
        pit = [self.pit_xy(PIT_ENTRY_M + p) for p in np.arange(0.0, self.pit_length + STEP_M, STEP_M)]
        return {
            "x": np.round(self.x, 1).tolist(),
            "y": np.round(self.y, 1).tolist(),
            "corners": [{"number": int(r.number), "x": float(r.label_x), "y": float(r.label_y)} for r in self.corners.itertuples()],
            "pit_lane": [[round(px, 1), round(py, 1)] for px, py in pit],
            "pit_box": list(self.pit_xy(PIT_BOX_M)),
        }
