"""Offline validation of supplied anonymized routes; no real dataset is bundled."""
import argparse
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import io
import json
import math
import os
from pathlib import Path
from statistics import mean, median
import sys
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("ALLOW_SQLITE_LEGACY", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import optimizer


def nonnegative(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{field}: expected a finite nonnegative number")
    return value


def load_scenario(data, allow_synthetic=False):
    if data.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    if data.get("source") != "anonymized_real" and not (allow_synthetic and data.get("source") == "synthetic_test"):
        raise ValueError("source must identify anonymized_real; synthetic_test requires explicit opt-in")
    if not isinstance(data.get("scenario_id"), str) or not data["scenario_id"]:
        raise ValueError("scenario_id is required")
    if not isinstance(data.get("depot"), dict) or not data["depot"].get("id"):
        raise ValueError("depot.id is required")
    if not isinstance(data.get("return_depot"), bool):
        raise ValueError("return_depot must be boolean")
    start = data.get("start_time")
    if not isinstance(start, str) or optimizer.parse_time_value(start) is None:
        raise ValueError("start_time must be a valid time")
    stops = data.get("stops")
    if not isinstance(stops, list) or not 1 <= len(stops) <= 15:
        raise ValueError("stops must contain 1-15 stops")
    ids = [s.get("id") for s in stops]
    if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("stop ids must be unique nonempty strings")
    order = data.get("operator_order")
    if not isinstance(order, list) or len(order) != len(ids) or set(order) != set(ids):
        raise ValueError("operator_order must be an exact permutation of stop ids")
    rows = []
    for i, stop in enumerate(stops, 1):
        row = dict(customer_id=stop["id"], cliente_nome=stop.get("label", stop["id"]),
                   indirizzo=stop["id"], _matrix_index=i, tempo_scarico_min=nonnegative(stop.get("service_min", 0), "service_min"))
        for period in ("mattina", "pomeriggio"):
            a, b = (stop.get(f"scarico_{period}_{suffix}") for suffix in ("da", "a"))
            if (a is None) != (b is None):
                raise ValueError("windows need both start and end")
            if a is not None:
                if not isinstance(a, str) or not isinstance(b, str) or optimizer.parse_time_value(a) is None or optimizer.parse_time_value(b) is None or optimizer.parse_hhmm(a) >= optimizer.parse_hhmm(b):
                    raise ValueError("windows must be valid same-day intervals")
            row.update({f"scarico_{period}_da": a, f"scarico_{period}_a": b})
        for flag in ("ztl", "sponda"):
            if flag in stop and not isinstance(stop[flag], bool):
                raise ValueError(f"{flag} must be boolean")
            row[flag] = stop.get(flag, False)
        rows.append(row)
    n = len(stops) + 1
    for field in ("matrix_km", "matrix_min"):
        matrix = data.get(field)
        if not isinstance(matrix, list) or len(matrix) != n or any(not isinstance(r, list) or len(r) != n for r in matrix):
            raise ValueError(f"{field} must be a complete {n} by {n} matrix")
        for i, row in enumerate(matrix):
            for j, value in enumerate(row):
                nonnegative(value, field)
                if i == j and value != 0:
                    raise ValueError("matrix diagonal must be zero")
    for component in data.get("energy", {}).get("components", []):
        nonnegative(component.get("consumption_per_100km"), "consumption_per_100km")
        nonnegative(component.get("price_per_unit"), "price_per_unit")
    lookup = {row["customer_id"]: row for row in rows}
    matrix = {(i, j): {"km": data["matrix_km"][i][j], "min": data["matrix_min"][i][j]}
              for i in range(n) for j in range(n) if i != j}
    return [lookup[i] for i in order], matrix


def evaluate_scenario(data, allow_synthetic=False):
    rows, matrix = load_scenario(data, allow_synthetic)
    def forbidden(*args, **kwargs):
        raise AssertionError("Real-route runner must stay offline")
    with ExitStack() as stack, redirect_stdout(io.StringIO()):
        for name in ("osrm_route", "geocode", "google_route_matrix", "google_route_polyline", "build_distance_matrix"):
            stack.enter_context(patch.object(optimizer, name, forbidden))
        stack.enter_context(patch.object(optimizer.requests.sessions.Session, "request", forbidden))
        options = dict(start_time=data["start_time"], return_depot=data["return_depot"])
        operator = optimizer._evaluate_fixed_sequence(deepcopy(rows), matrix, [], **options)
        actual = optimizer._best_internal_sequence(deepcopy(rows), matrix, [], **options)
    keys = ("total_km", "total_min", "violations_count", "total_lateness_min", "total_wait_min", "score")
    result = {"scenario_id": data["scenario_id"], "source": data["source"],
              "operator": {k: operator[k] for k in keys}, "girofacile": {k: actual[k] for k in keys},
              "optimized_order": [d["customer_id"] for d in actual["ordered"]]}
    for name in ("km", "min"):
        a, b = operator[f"total_{name}"], actual[f"total_{name}"]
        result[f"delta_{name}"] = b - a
        result[f"delta_{name}_pct"] = 100 * (b - a) / a if a else None
    old, new = optimizer.solution_key(operator), optimizer.solution_key(actual)
    result["outcome"] = "improved" if new < old else "worsened" if new > old else "unchanged"
    result["feasibility_regression"] = operator["violations"] == 0 and actual["violations"] > 0
    result["violations_increased"] = actual["violations"] > operator["violations"]
    energy = data.get("energy", {})
    components = energy.get("components", [])
    result["energy_cost"] = None
    if components:
        unit_cost = sum(c["consumption_per_100km"] * c["price_per_unit"] / 100 for c in components)
        result["energy_cost"] = {"currency": energy.get("currency", "EUR"),
                                 "operator": operator["total_km"] * unit_cost,
                                 "girofacile": actual["total_km"] * unit_cost}
    return result


def summarize(records):
    summary = {"count": len(records), **{k: sum(r["outcome"] == k for r in records) for k in ("improved", "unchanged", "worsened")},
               "feasibility_regressions": sum(r["feasibility_regression"] for r in records),
               "violations_increased": sum(r["violations_increased"] for r in records)}
    for key in ("delta_km", "delta_km_pct", "delta_min", "delta_min_pct"):
        values = [r[key] for r in records if r[key] is not None]
        summary[key] = {"mean": mean(values) if values else None, "median": median(values) if values else None,
                        "best": min(values) if values else None, "worst": max(values) if values else None}
    summary["best_km_scenario"] = min(records, key=lambda r: r["delta_km"])["scenario_id"] if records else None
    summary["worst_km_scenario"] = max(records, key=lambda r: r["delta_km"])["scenario_id"] if records else None
    return summary


def run_dataset(root, split, allow_synthetic=False):
    if split not in ("development", "validation"):
        raise ValueError("Choose development or validation explicitly")
    directory = Path(root) / split
    if not directory.is_dir():
        raise ValueError(f"Dataset directory does not exist: {directory}")
    records = []
    seen = set()
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if data.get("split") != split or data.get("scenario_id") in seen:
            raise ValueError(f"Wrong split or duplicate scenario id: {path.name}")
        seen.add(data.get("scenario_id"))
        records.append(evaluate_scenario(data, allow_synthetic))
    return {"split": split, "records": records, "summary": summarize(records),
            "note": "No real routes supplied" if not records else "Saved matrices only; no live routing"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).parent / "fixtures/optimizer_real")
    parser.add_argument("--split", required=True, choices=("development", "validation"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-synthetic", action="store_true", help="Test examples only, not real validation")
    args = parser.parse_args()
    report = run_dataset(args.root, args.split, args.allow_synthetic)
    text = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)
