"""Offline before/after report. Run from repo: python tests/run_optimizer_benchmark.py.

Baseline code is read from the immutable Punto 1 Git commit, not copied/changed.
All external routing/geocoding paths fail. No database or network is used.
"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter
from copy import deepcopy
from functools import lru_cache

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("ALLOW_SQLITE_LEGACY", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import optimizer as after
from optimizer_benchmark import deliveries, metric_matrix, exact_reference
from optimizer_scenarios import directed_case, reordered, independent_window_reference
from test_optimizer import GRID

BASE = "81f512189916f5e7e091c6956689fa5be38eb1b9"
source = subprocess.check_output(["git", "show", BASE + ":app/optimizer.py"]).decode("utf-8")
spec = importlib.util.spec_from_loader("app._optimizer_before", loader=None)
before = importlib.util.module_from_spec(spec)
exec(compile(source, BASE + ":app/optimizer.py", "exec"), before.__dict__)


def forbidden(*args, **kwargs):
    raise AssertionError("Offline benchmark attempted external access")


for module in (before, after):
    for name in ("osrm_route", "geocode", "google_route_matrix", "google_route_polyline"):
        setattr(module, name, forbidden)
after.requests.sessions.Session.request = forbidden


def measure(function):
    start = perf_counter()
    with contextlib.redirect_stdout(io.StringIO()):
        result = function()
    return {key: result[key] for key in ("total_km", "total_min", "score", "violations", "total_wait")} | {"runtime_ms": round((perf_counter() - start) * 1000, 3)}


@lru_cache(None)
def reference(n, kind, back):
    if kind == "grid":
        return exact_reference(n, metric_matrix(GRID[:n+1]), back)
    rows, matrix = directed_case(n, kind == "windows")
    return (independent_window_reference(rows, matrix, back) if kind == "windows"
            else exact_reference(n, matrix, back))


def compare(n, kind, back=True, order="forward"):
    if kind == "grid":
        rows, matrix = deliveries(n), metric_matrix(GRID[:n+1])
    else:
        rows, matrix = directed_case(n, kind == "windows")
    rows = reordered(rows, order)
    ref = reference(n, kind, back)
    results = {name: measure(lambda m=module: m._best_internal_sequence(deepcopy(rows), matrix, [], return_depot=back))
               for name, module in (("before", before), ("after", after))}
    for result in results.values():
        for key in ("total_km", "total_min", "score"):
            result[key + "_gap_pct"] = 100 * (result[key] - ref[key]) / ref[key] if ref[key] else None
    assert results["after"]["score"] <= results["before"]["score"]
    assert results["after"]["violations"] <= results["before"]["violations"]
    if kind == "windows":
        assert ref["violations"] == results["after"]["violations"] == 0
    return dict(n=n, kind=kind, return_depot=back, input_order=order,
                reference_kind="feasible_witness_not_optimum" if kind == "windows" else "exact_additive_optimum",
                reference=ref, **results)


def ablation(n):
    rows, matrix = deliveries(n), metric_matrix(GRID[:n+1])
    seed = after._greedy_sequence(rows, matrix, [])
    variants = {}
    for name, seeds, relocation in (("legacy", [seed], False),
                                     ("relocation_only", [seed], True),
                                     ("multistart_only", [seed, rows, seed[::-1]], False),
                                     ("combined", [seed, rows, seed[::-1]], True)):
        variants[name] = measure(lambda seeds=seeds, relocation=relocation:
            min([after._local_optimize_sequence(s, matrix, [], relocate=relocation) for s in seeds], key=lambda r: r["score"]))
    return dict(n=n, variants=variants)


if __name__ == "__main__":
    records = [compare(n, "grid") for n in (5, 8, 9, 10, 12, 15)]
    records += [compare(n, kind, back, order) for kind in ("directed", "windows")
                for n in (9, 10, 12, 15) for back in (False, True)
                for order in ("forward", "reverse", "interleaved")]
    output = dict(baseline_commit=BASE, timing="One wall-clock sample per variant; includes search only, not oracle/import. No timing assertions.",
                  records=records, ablation=[ablation(n) for n in (9, 10, 12, 15)])
    Path("docs/optimizer-benchmark-results.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    for row in records[:6]:
        print(row["n"], row["before"], row["after"])
    print("Scenarios:", len(records), "all score/feasibility comparisons passed")
