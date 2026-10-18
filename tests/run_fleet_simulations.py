"""Offline audit of the real automatic fleet planner, not a replacement solver.

Run: python tests/run_fleet_simulations.py
Only input/availability/routing boundaries are mocked. Production insertion and
schedule evaluation stay real. Exact references use an independent simulator.
No production data, database, network, messages or payments are used.
"""
from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import smtplib
import socket
import statistics
import subprocess
import sys
from time import perf_counter, process_time
from types import MappingProxyType, SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["ALLOW_SQLITE_LEGACY"] = "true"
os.environ["APP_ENV"] = "test"
os.environ["BILLING_MODE"] = "disabled"

import requests
from app import optimizer as opt
from app.services import fleet_planning as fleet
from app.schemas.fleet_planning import FleetInput
from fleet_quality_reference import route_replay, plan_metrics, solve_exact
from fleet_simulation_cases import all_cases

STRATEGIES = ("efficient", "balanced")
METRIC_FIELDS = ("served", "mismatches", "used", "km", "minutes", "makespan", "sumsq")
KM_EPS, MIN_EPS = 0.02, 0.11


def forbidden(*args, **kwargs):
    raise AssertionError("Simulation attempted a database/provider/email/network operation")


class NoDatabase:
    def __getattr__(self, name):
        raise AssertionError(f"Unexpected database access: {name}")


class FrozenMatrix(Mapping):
    source = "offline-fixture"

    def __init__(self, matrix):
        self._data = MappingProxyType({
            key: MappingProxyType(dict(value)) for key, value in matrix.items()
        })

    def __getitem__(self, key):
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)


def hhmm(value):
    minute = int(round(value)) % 1440
    return f"{minute // 60:02d}:{minute % 60:02d}"


def clock_distance(text, raw):
    hour, minute = map(int, text.split(":"))
    delta = abs((hour * 60 + minute) - raw % 1440)
    return min(delta, 1440 - delta)


def compact(metrics):
    return {key: deepcopy(metrics[key]) for key in (*METRIC_FIELDS, "orders")}


def key(metrics, mode):
    prefix = (-metrics["served"], metrics["mismatches"])
    if mode == "km":
        return (*prefix, metrics["km"], metrics["minutes"], metrics["used"])
    if mode == "time":
        return (*prefix, metrics["minutes"], metrics["km"], metrics["used"])
    if mode == "efficient":
        return (*prefix, metrics["used"], metrics["minutes"], metrics["km"])
    return (*prefix, -metrics["used"], metrics["makespan"], metrics["sumsq"],
            metrics["minutes"], metrics["km"])


def worse(actual, reference, mode):
    """Ignore differences below public display precision."""
    aa, rr = key(actual, mode), key(reference, mode)
    if mode in ("km", "time"):
        eps = (0, 0, KM_EPS if mode == "km" else MIN_EPS,
               MIN_EPS if mode == "km" else KM_EPS, 0)
    elif mode == "efficient":
        eps = (0, 0, 0, MIN_EPS, KM_EPS)
    else:
        square_eps = max(1, 2 * max(actual["makespan"], reference["makespan"]) *
                         MIN_EPS * max(actual["used"], 1))
        eps = (0, 0, 0, MIN_EPS, square_eps, MIN_EPS, KM_EPS)
    for a, r, tolerance in zip(aa, rr, eps):
        if a > r + tolerance:
            return True
        if a < r - tolerance:
            return False
    return False


def comparisons(actual, references, strategy):
    if not references:
        return {}
    coverage = references["km"]["served"]
    km_ref, time_ref = references["km"], references["time"]
    comparable = coverage == actual["served"] and actual["mismatches"] == km_ref["mismatches"]
    distance_gap = max(0, actual["km"] - km_ref["km"]) if comparable else None
    duration_gap = max(0, actual["minutes"] - time_ref["minutes"]) if comparable else None
    witnesses = []
    for mode, ref in references.items():
        if ref["served"] != actual["served"] or ref["mismatches"] > actual["mismatches"]:
            continue
        if (ref["km"] <= actual["km"] + KM_EPS
            and ref["minutes"] <= actual["minutes"] + MIN_EPS
            and (ref["km"] < actual["km"] - KM_EPS
                 or ref["minutes"] < actual["minutes"] - MIN_EPS)):
            witnesses.append(mode)
    return {
        "maximum_served": coverage,
        "missed_feasible_stops": max(0, coverage - actual["served"]),
        "distance_gap_km": distance_gap,
        "distance_gap_pct": (100 * distance_gap / km_ref["km"]
                             if distance_gap is not None and km_ref["km"] else None),
        "duration_gap_min": duration_gap,
        "duration_gap_pct": (100 * duration_gap / time_ref["minutes"]
                            if duration_gap is not None and time_ref["minutes"] else None),
        "strategy_reference_better": worse(actual, references[strategy], strategy),
        "simultaneous_improvement_witnesses": witnesses,
    }


def execute(case, strategy):
    """Invoke production distribute(), replacing only isolated boundaries."""
    start_min = case.get("start_min", 480)
    resources = case["resources"]
    vehicles = [SimpleNamespace(
        id=i+1, nome=f"Mezzo simulato {i+1}", targa=f"TEST-{i+1}",
        capacita_kg=r.get("capacita_kg"), capacita_colli=r.get("capacita_colli"),
        ha_sponda=bool(r.get("ha_sponda")), accesso_ztl=bool(r.get("accesso_ztl")),
        alimentazione=r.get("alimentazione", "gasolio"),
        consumo_primario_100km=10, consumo_l_100km=10, consumo_kwh_100km=25,
    ) for i, r in enumerate(resources)]
    drivers = [SimpleNamespace(id=i+1, nome=f"Autista simulato {i+1}", cognome="")
               for i in range(len(resources))]
    depot = SimpleNamespace(id=1, user_id=1, indirizzo="Deposito fittizio",
                            lat=45.46, lon=9.19)
    user = SimpleNamespace(id=1)
    data = FleetInput.model_validate({
        "nome": "Simulazione offline", "data_giro": "2099-01-15",
        "orario_partenza": hhmm(start_min), "deposit_id": 1,
        "rientro_deposito": case["return_depot"], "strategy": strategy,
        "resources": [{
            "vehicle_id": i+1, "driver_id": i+1,
            "max_minutes": r["max_minutes"],
            "driver_schedule": r.get("driver_schedule") or {},
        } for i, r in enumerate(resources)],
        "consegne": case["stops"],
    })
    matrix = FrozenMatrix(case["matrix"])
    calls = []

    def input_fixture(db, company, settings):
        return depot, [d.model_dump(mode="json") for d in settings.consegne], vehicles, drivers

    def matrix_fixture(db, user_id, points, keys, **kwargs):
        assert len(points) == len(case["stops"]) + 1
        assert len(keys) == len(points)
        calls.append(len(points))
        return matrix

    with ExitStack() as stack:
        stack.enter_context(patch.object(fleet, "input_state", input_fixture))
        stack.enter_context(patch.object(fleet, "work_limits", lambda *args: [
            min(r["max_minutes"], r.get("available_minutes", r["max_minutes"]))
            for r in resources
        ]))
        stack.enter_context(patch.object(opt, "geocode_deposit",
                                        lambda *args: {"lat": depot.lat, "lon": depot.lon}))
        stack.enter_context(patch.object(opt, "build_distance_matrix", matrix_fixture))
        stack.enter_context(patch.object(requests.sessions.Session, "request", forbidden))
        stack.enter_context(patch.object(requests, "get", forbidden))
        stack.enter_context(patch.object(socket.socket, "connect", forbidden))
        stack.enter_context(patch.object(smtplib, "SMTP", forbidden))
        wall, cpu = perf_counter(), process_time()
        output = fleet.distribute(NoDatabase(), user, data)
        elapsed_ms = (perf_counter() - wall) * 1000
        cpu_ms = (process_time() - cpu) * 1000
    assert calls == [len(case["stops"]) + 1], "Expected exactly one matrix request"

    orders = [[] for _ in resources]
    errors, assigned = [], []
    for route in output["routes"]:
        resource, sequence = route["resource"], route["stop_indexes"]
        if orders[resource]:
            errors.append("Resource repeated in result")
        orders[resource] = sequence
        assigned.extend(sequence)
        replayed = route_replay(case, resource, sequence)
        if not replayed["feasible"]:
            errors.append(f"Resource {resource}: {replayed.get('errors')}")
            continue
        actual = route["result"]
        if abs(actual["total_km"] - replayed["km"]) > 0.011:
            errors.append(f"Distance mismatch on resource {resource}")
        if abs(actual["total_min"] - replayed["minutes"]) > 0.051:
            errors.append(f"Duration mismatch on resource {resource}")
        if clock_distance(actual["return_time"], replayed["end"]) > 0.501:
            errors.append(f"Return clock mismatch on resource {resource}")
        if not (len(actual["ordered"]) == len(sequence) == len(replayed["timings"])):
            errors.append(f"Stop count mismatch on resource {resource}")
        for saved, timing in zip(actual["ordered"], replayed["timings"]):
            if saved.get("customer_id") != case["stops"][timing["index"]]["customer_id"]:
                errors.append(f"Stop identity mismatch on resource {resource}")
            if clock_distance(saved["arrivo_stimato"], timing["service_start"]) > 0.501:
                errors.append(f"Service ETA mismatch on resource {resource}")
            if clock_distance(saved["partenza_stimata"], timing["service_end"]) > 0.501:
                errors.append(f"Service completion mismatch on resource {resource}")
            if abs(float(saved.get("attesa_min") or 0) - timing["wait"]) > 0.051:
                errors.append(f"Waiting mismatch on resource {resource}")
    unassigned = [row["index"] for row in output["unassigned"]]
    if sorted(assigned + unassigned) != list(range(len(case["stops"]))):
        errors.append("Stop missing or duplicated between routes and unassigned list")
    if len(set(assigned)) != len(assigned):
        errors.append("Stop assigned more than once")
    if any(not row.get("reason") for row in output["unassigned"]):
        errors.append("Unassigned stop has no reason")
    metrics = plan_metrics(case, orders)
    if not metrics.get("feasible", False):
        errors.append("Independent plan validation rejected the result")
    return {
        "metrics": compact(metrics), "invariant_errors": errors,
        "runtime_ms": elapsed_ms, "cpu_ms": cpu_ms, "matrix_requests": len(calls),
        "external_requests": 0, "unassigned": output["unassigned"], "warnings": output["warnings"],
    }


def permuted(case, permutation):
    result = deepcopy(case)
    nodes = [0] + [index+1 for index in permutation]
    result["stops"] = [deepcopy(case["stops"][index]) for index in permutation]
    result["matrix"] = {(i, j): dict(case["matrix"][nodes[i], nodes[j]])
                        for i in range(len(nodes)) for j in range(len(nodes)) if i != j}
    return result


def remap_references(references, permutation):
    inverse = {old: new for new, old in enumerate(permutation)}
    result = deepcopy(references)
    for metrics in result.values():
        metrics["orders"] = [[inverse[index] for index in order] for order in metrics["orders"]]
    return result


def canonical(case, actual):
    return [[case["stops"][index]["customer_id"] for index in order]
            for order in actual["metrics"]["orders"]]


def stats(values):
    values = sorted(value for value in values if value is not None)
    if not values:
        return {"count": 0, "median": None, "p95": None, "max": None}
    return {"count": len(values), "median": statistics.median(values),
            "p95": values[max(0, math.ceil(len(values) * .95) - 1)], "max": values[-1]}


def summarize(records, cases, deterministic, reorder_changes):
    base = [row for row in records if row["stage"] == "base"]
    report = {
        "unique_scenarios": len(cases), "base_runs": len(base), "total_runs": len(records),
        "exact_scenarios": sum(bool(case.get("exact")) for case in cases),
        "exact_base_runs": sum(bool(row.get("reference")) for row in base),
        "matrix_requests": sum(row["actual"]["matrix_requests"] for row in records),
        "external_requests": sum(row["actual"]["external_requests"] for row in records),
        "invariant_errors": sum(len(row["actual"]["invariant_errors"]) for row in records),
        "deterministic_repeats": len(deterministic),
        "determinism_failures": [row for row in deterministic if not row["identical"]],
        "reordered_runs": sum(row["stage"] == "reordered" for row in records),
        "input_order_changes": reorder_changes, "strategies": {},
        "stress_runtime_ms": stats([row["actual"]["runtime_ms"] for row in base if not row.get("reference")]),
    }
    for strategy in STRATEGIES:
        rows = [row for row in base if row["strategy"] == strategy]
        exact = [row for row in rows if row.get("reference")]
        cc = [row["comparison"] for row in exact]
        report["strategies"][strategy] = {
            "runs": len(rows), "exact_runs": len(exact),
            "missed_feasible_cases": sum(row["missed_feasible_stops"] > 0 for row in cc),
            "missed_feasible_stops": sum(row["missed_feasible_stops"] for row in cc),
            "worse_than_strategy_reference": sum(row["strategy_reference_better"] for row in cc),
            "simultaneous_improvement_cases": sum(bool(row["simultaneous_improvement_witnesses"]) for row in cc),
            "distance_gap_pct": stats([row["distance_gap_pct"] for row in cc]),
            "duration_gap_pct": stats([row["duration_gap_pct"] for row in cc]),
            "runtime_ms": stats([row["actual"]["runtime_ms"] for row in rows]),
            "unassigned_stops": sum(len(row["actual"]["unassigned"]) for row in rows),
        }
    return report


def markdown(summary, examples, metadata):
    before=metadata.get("fleet_implementation")=="before"
    method=("Baseline congelata: inserimento progressivo senza riallocazione globale."
            if before else "Ricerca esatta sui piccoli casi e ricerca limitata con raggruppamenti geografici e scambi sui grandi.")
    lines = [
        "# Simulazioni della distribuzione multi-mezzo", "",
        method, "",
        f"Commit eseguito: {metadata['tested_commit']}.",
        f"Generato: {metadata['generated_at_utc']}. Matrici congelate e dati fittizi; nessun dato operativo.", "",
        f"Scenari distinti: **{summary['unique_scenarios']}**. Esecuzioni: **{summary['total_runs']}**; "
        f"casi con riferimento esatto: **{summary['exact_scenarios']}**, con entrambe le strategie.", "",
        "## Metodo", "",
        "- Invocazione reale di app.services.fleet_planning.distribute; ingressi aziendali, disponibilità e matrice sostituiti con fixture isolate.",
        "- Valutatore indipendente per capacità, finestre doppie, scarico, pause, turno, durata massima e rientro.",
        "- Nei casi piccoli: tutte le sequenze per sottoinsieme/risorsa e tutte le assegnazioni, comprese consegne lasciate fuori.",
        "- Riferimenti distinti: copertura massima, dotazioni, poi minimo km / minimo minuti / consolidamento / bilanciamento. Questi ultimi sono riferimenti globali coerenti con le priorità, non la stessa decisione locale a ogni inserimento.",
        "- Nei casi grandi: invarianti, tempi e stabilità; nessuna certificazione di ottimo.", "",
        "## Risultati", "",
        f"Errori degli invarianti: **{summary['invariant_errors']}**. Richieste esterne: **{summary['external_requests']}**. "
        f"Matrici al boundary: **{summary['matrix_requests']}**, una per esecuzione, tutte da fixture.",
        f"Ripetizioni identiche: {summary['deterministic_repeats']}; divergenze: {len(summary['determinism_failures'])}. "
        f"Esecuzioni con selezione riordinata: {summary['reordered_runs']}.", "",
        "| Strategia | Casi esatti | Casi con consegne fattibili lasciate fuori | Peggiore del riferimento globale coerente con la strategia | Testimoni di miglioramento km/tempo |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, values in summary["strategies"].items():
        lines.append(f"| {name} | {values['exact_runs']} | {values['missed_feasible_cases']} | "
                     f"{values['worse_than_strategy_reference']} | {values['simultaneous_improvement_cases']} |")
    lines += ["",
        "I gap usano solo casi con uguale copertura e dotazioni. I riferimenti km e tempo possono scegliere "
        "ripartizioni diverse. I testimoni simultanei sono miglioramenti concreti tra quattro ottimi; "
        "non rappresentano l'intera frontiera di Pareto.", "",
        "## Casi mirati", "",
        "| Caso | Strategia | Consegnate attuali / massimo | km attuali / minimi | minuti attuali / minimi |",
        "|---|---|---:|---:|---:|",
    ]
    for row in examples:
        actual, refs = row["actual"]["metrics"], row["reference"]
        if refs:
            lines.append(f"| {row['case_id']} | {row['strategy']} | {actual['served']} / {refs['km']['served']} | "
                         f"{actual['km']:.2f} / {refs['km']['km']:.2f} | {actual['minutes']:.1f} / {refs['time']['minutes']:.1f} |")
    lines += ["",
        "Non confrontare km/minuti come miglioramento a parità di servizio quando le consegne servite differiscono.", "",
        "## Prestazioni e limiti", "",
        f"Stress: mediana {summary['stress_runtime_ms']['median']:.1f} ms, p95 {summary['stress_runtime_ms']['p95']:.1f} ms, "
        f"massimo {summary['stress_runtime_ms']['max']:.1f} ms per distribuzione.",
        "Tempi del solo motore, senza database/provider, su runner CI: non sono tempi garantiti in produzione.",
        "Il confronto valuta copertura, avvisi e obiettivo di ogni strategia separatamente. "
        "Gli obiettivi non equivalgono alla sola minimizzazione dei km.",
        "Partenza/deposito/giornata comuni; pause fisse dichiarate. Niente ricerca di partenze differenziate "
        "né verifica automatica normativa ore guida. Sponda/ZTL sono preferenze con avviso; volume/pallet "
        "non sono capacità rigide. La campagna usa solo dati fittizi e matrici congelate.",
        "Il benchmark testa il nucleo della distribuzione. Persistenza, autorizzazioni e traffico sono coperti "
        "dai test applicativi separati. Il traffico reale futuro non è certificabile con matrici congelate.", "",
        "## Riproduzione", "",
        "    python -m pytest tests/test_fleet_quality_reference.py tests/test_fleet_planning.py tests/test_driver_schedule.py -q",
        "    python tests/run_fleet_simulations.py", "",
        "L'artifact fleet-simulation-results contiene JSON completo, ordini dei testimoni, semi, famiglie, "
        "matrici dei casi mirati e impronte SHA256 dei file del motore.", "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "test-results" / "fleet-simulations")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    cases = all_cases()
    assert len({case["id"] for case in cases}) == len(cases)
    records, references, baselines = [], {}, {}
    deterministic, reorder_changes = [], []
    started = perf_counter()
    with (output / "runs.jsonl").open("w", encoding="utf-8") as log:
        def record(case, strategy, actual, stage="base", refs=None, permutation=None, variant_name=None):
            row = {
                "case_id": case["id"], "family": case["family"], "seed": case.get("seed"),
                "strategy": strategy, "stage": stage, "variant": variant_name or stage, "stops": len(case["stops"]),
                "resources": len(case["resources"]), "return_depot": case["return_depot"],
                "permutation": permutation, "actual": actual, "reference": refs,
                "comparison": comparisons(actual["metrics"], refs, strategy),
            }
            records.append(row)
            log.write(json.dumps(row, ensure_ascii=False) + "\n")
            log.flush()
            return row

        for index, case in enumerate(cases):
            refs = solve_exact(case) if case.get("exact") else {}
            if refs:
                assert len({(r["served"], r["mismatches"]) for r in refs.values()}) == 1
                for ref in refs.values():
                    replayed_ref = plan_metrics(case, ref["orders"])
                    assert replayed_ref.get("feasible", True), "Reference witness is infeasible"
                    for field in METRIC_FIELDS:
                        assert abs(replayed_ref[field] - ref[field]) <= 1e-7, "Reference metric mismatch"
            references[case["id"]] = refs
            for strategy in STRATEGIES:
                actual = execute(case, strategy)
                baselines[case["id"], strategy] = actual
                record(case, strategy, actual, refs=refs)
            if index % 10 == 0 or index == len(cases)-1:
                print(f"FLEET_PROGRESS {index+1}/{len(cases)} cases; {perf_counter()-started:.1f}s", flush=True)

        selected, per_family = [], Counter()
        for case in cases:
            if not case.get("exact"):
                continue
            if len(selected) < 8 or per_family[case["family"]] < 2:
                selected.append(case)
                per_family[case["family"]] += 1
            if len(selected) == 24:
                break
        assert len(selected) == 24
        for index, case in enumerate(selected):
            for name in ("reverse", "shuffle"):
                permutation = list(range(len(case["stops"])))
                if name == "reverse":
                    permutation.reverse()
                else:
                    random.Random(81000 + index).shuffle(permutation)
                variant = permuted(case, permutation)
                refs = remap_references(references[case["id"]], permutation)
                for strategy in STRATEGIES:
                    actual = execute(variant, strategy)
                    record(variant, strategy, actual, "reordered", refs, permutation, variant_name=name)
                    before, after = baselines[case["id"], strategy]["metrics"], actual["metrics"]
                    changed = any(abs(before[field] - after[field]) > (
                        KM_EPS if field == "km" else MIN_EPS if field in ("minutes", "makespan") else 0
                    ) for field in ("served", "used", "km", "minutes", "makespan"))
                    if changed:
                        reorder_changes.append({"case_id": case["id"], "strategy": strategy,
                                                "order": name, "before": compact(before), "after": compact(after)})
            if index < 12:
                for strategy in STRATEGIES:
                    repeated = execute(case, strategy)
                    original = baselines[case["id"], strategy]
                    identical = canonical(case, repeated) == canonical(case, original) and repeated["metrics"] == original["metrics"]
                    deterministic.append({"case_id": case["id"], "strategy": strategy, "identical": identical})
                    record(case, strategy, repeated, "repeat", references[case["id"]])

    summary = summarize(records, cases, deterministic, reorder_changes)
    summary["total_seconds"] = perf_counter() - started
    summary["input_order_change_count"] = len(reorder_changes)
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    paths = ("app/optimizer.py", "app/services/fleet_planning.py",
             "app/services/driver_schedule.py", "app/services/optimizer_search.py",
             "app/services/fleet_search.py",
             "tests/run_fleet_simulations.py", "tests/fleet_quality_reference.py",
             "tests/fleet_simulation_cases.py")
    metadata = {
        "tested_commit": commit, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "platform": platform.platform(),
        "engine_sha256": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths},
        "scope": "real distribute core; fixture matrix/input/availability; no DB/provider calls",
        "baseline_inspected_commit": "bbf4553d9d7ed47c3f01c3954214206bcf734579",
    }
    examples = [row for row in records if row["stage"] == "base" and row["case_id"] in {
        case["id"] for case in cases[:8]
    }]
    curated = []
    for case in cases[:8]:
        raw = deepcopy(case)
        raw["matrix"] = [{"from": a, "to": b, **leg} for (a, b), leg in case["matrix"].items()]
        curated.append(raw)
    result = {"metadata": metadata, "summary": summary, "examples": examples,
              "curated_inputs": curated, "runs": records}
    report = markdown(summary, examples, metadata)
    (output / "results.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output / "report.md").write_text(report, encoding="utf-8")
    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("FLEET_SIM_SUMMARY " + json.dumps(summary, ensure_ascii=False), flush=True)
    print("FLEET_SIM_EXAMPLES " + json.dumps(examples, ensure_ascii=False), flush=True)
    print("FLEET_SIM_REPORT " + json.dumps({"markdown": report, "metadata": metadata}, ensure_ascii=False), flush=True)
    return 1 if summary["invariant_errors"] or summary["determinism_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
