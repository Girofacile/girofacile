"""Offline before/after campaign on identical inputs and a hash-pinned baseline."""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import patch
import run_fleet_simulations as audit

ROOT = Path(__file__).resolve().parents[1]
BASELINE_COMMIT = "1c4bb0969dc14b9da454d5a22019e1cd5e758ab4"
BASELINE_BLOB = "ec600f0b77f30be69b2796e603c5d9ad117ca88f"
BASELINE_FILE = ROOT / "tests/fixtures/fleet_planning_before_20261018.py"
FIELDS = ("served", "mismatches", "used", "km", "minutes", "makespan", "sumsq")


def load_baseline(path):
    source = Path(path).read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(source)).encode() + b"\0" + source).hexdigest()
    if blob != BASELINE_BLOB:
        raise ValueError(f"Baseline does not match {BASELINE_COMMIT}: {blob}")
    module = ModuleType("app.services._fleet_audit_before_20261018")
    module.__package__ = "app.services"
    module.__file__ = str(Path(path).resolve())
    sys.modules[module.__name__] = module
    try:
        exec(compile(source, module.__file__, "exec"), module.__dict__)
    except BaseException:
        sys.modules.pop(module.__name__, None)
        raise
    return module, dict(commit=BASELINE_COMMIT, source_path="app/services/fleet_planning.py",
                        snapshot_path=str(Path(path).resolve()), git_blob_sha1=blob,
                        sha256=hashlib.sha256(source).hexdigest(),
                        scope="frozen distribution service; shared optimizer/scheduler from checkout")


def row_key(row):
    return row["case_id"], row["strategy"], row["stage"], tuple(row.get("permutation") or ())


def index_rows(result):
    rows = {}
    for row in result["runs"]:
        identity = row_key(row)
        if identity in rows:
            raise ValueError(f"Duplicate run identity: {identity}")
        rows[identity] = row
    return rows


def compare_results(before, after):
    previous, current = index_rows(before), index_rows(after)
    if previous.keys() != current.keys():
        raise ValueError("Before/after run identities differ")
    pairs = []
    for identity, row in previous.items():
        updated = current[identity]
        for field in ("family", "seed", "stops", "resources", "return_depot"):
            if row.get(field) != updated.get(field):
                raise ValueError(f"Scenario changed between implementations: {identity}, {field}")
        aa, bb = row["actual"]["metrics"], updated["actual"]["metrics"]
        pairs.append(dict(
            case_id=row["case_id"], strategy=row["strategy"], stage=row["stage"],
            permutation=row.get("permutation"), before=deepcopy(aa), after=deepcopy(bb),
            delta={field: bb[field] - aa[field] for field in FIELDS},
            coverage_regression=bb["served"] < aa["served"],
            objective_regression=audit.worse(bb, aa, row["strategy"]),
            objective_improvement=audit.worse(aa, bb, row["strategy"]),
            before_runtime_ms=row["actual"]["runtime_ms"],
            after_runtime_ms=updated["actual"]["runtime_ms"]))
    summary = dict(paired_runs=len(pairs),
                   paired_base_runs=sum(row["stage"] == "base" for row in pairs),
                   total_engine_runs=len(previous) + len(current),
                   coverage_regressions=sum(row["coverage_regression"] for row in pairs),
                   objective_regressions=sum(row["objective_regression"] for row in pairs),
                   objective_improvements=sum(row["objective_improvement"] for row in pairs),
                   before=deepcopy(before["summary"]), after=deepcopy(after["summary"]),
                   strategies={})
    for strategy in audit.STRATEGIES:
        rows = [row for row in pairs if row["stage"] == "base" and row["strategy"] == strategy]
        equal = [row for row in rows if row["before"]["served"] == row["after"]["served"]
                 and row["before"]["mismatches"] == row["after"]["mismatches"]]
        summary["strategies"][strategy] = dict(
            paired_base_runs=len(rows),
            coverage_improved_cases=sum(row["delta"]["served"] > 0 for row in rows),
            extra_served_stops=sum(max(0, row["delta"]["served"]) for row in rows),
            coverage_regressions=sum(row["coverage_regression"] for row in rows),
            objective_improvements=sum(row["objective_improvement"] for row in rows),
            objective_regressions=sum(row["objective_regression"] for row in rows),
            equipment_mismatches_before=sum(row["before"]["mismatches"] for row in rows),
            equipment_mismatches_after=sum(row["after"]["mismatches"] for row in rows),
            equal_service_cases=len(equal),
            equal_service_km_before=sum(row["before"]["km"] for row in equal),
            equal_service_km_after=sum(row["after"]["km"] for row in equal),
            equal_service_minutes_before=sum(row["before"]["minutes"] for row in equal),
            equal_service_minutes_after=sum(row["after"]["minutes"] for row in equal),
            runtime_ms_before=audit.stats([row["before_runtime_ms"] for row in rows]),
            runtime_ms_after=audit.stats([row["after_runtime_ms"] for row in rows]))
    return dict(summary=summary, pairs=pairs)


def render_comparison(comparison):
    summary = comparison["summary"]
    before, after = summary["before"], summary["after"]
    lines = [
        "# Distribuzione multi-mezzo: confronto prima/dopo", "",
        f"Baseline: {BASELINE_COMMIT}; checkout: {comparison['metadata']['after_commit']}.",
        f"Coppie confrontate: **{summary['paired_runs']}**; esecuzioni totali: **{summary['total_engine_runs']}**.",
        "Stesse matrici, input, strategie, permutazioni e ripetizioni; nessun dato operativo o provider.",
        "Sponda e ZTL rimangono preferenze con avviso.", "",
        "| Strategia | Casi con più consegne | Consegne recuperate | Miglioramenti obiettivo | Regressioni |",
        "|---|---:|---:|---:|---:|"]
    for strategy, values in summary["strategies"].items():
        lines.append(f"| {strategy} | {values['coverage_improved_cases']} | "
                     f"{values['extra_served_stops']} | {values['objective_improvements']} | "
                     f"{values['objective_regressions']} |")
    lines += ["",
        f"Regressioni di copertura: **{summary['coverage_regressions']}**. "
        f"Regressioni dell'obiettivo: **{summary['objective_regressions']}**.",
        f"Errori invarianti prima/dopo: **{before['invariant_errors']} / {after['invariant_errors']}**. "
        f"Richieste esterne: **{before['external_requests']} / {after['external_requests']}**.", "",
        "| Strategia | Casi con consegne fattibili escluse prima/dopo | Peggiore del riferimento esatto prima/dopo |",
        "|---|---:|---:|"]
    for strategy in audit.STRATEGIES:
        aa, bb = before["strategies"][strategy], after["strategies"][strategy]
        lines.append(f"| {strategy} | {aa['missed_feasible_cases']} / {bb['missed_feasible_cases']} | "
                     f"{aa['worse_than_strategy_reference']} / {bb['worse_than_strategy_reference']} |")
    lines += ["", "| Caso | Strategia | Consegnate prima/dopo | km prima/dopo | minuti cumulativi prima/dopo |",
              "|---|---|---:|---:|---:|"]
    for row in comparison["examples"]:
        aa, bb = row["before"], row["after"]
        lines.append(f"| {row['case_id']} | {row['strategy']} | {aa['served']} / {bb['served']} | "
                     f"{aa['km']:.2f} / {bb['km']:.2f} | {aa['minutes']:.1f} / {bb['minutes']:.1f} |")
    lines += ["",
        "Km e minuti indicano risparmi diretti solo a parità di servizio e compatibilità. "
        "I minuti sono la somma delle durate dei giri, non il completamento di calendario della flotta. "
        "Le strategie hanno priorità diverse; gli scenari non stimano risparmi medi commerciali.",
        "Per i casi grandi la ricerca ha un budget: non certifica un ottimo globale. "
        "I tempi del nucleo con dati isolati non sono uno SLA di produzione.",
        "La baseline congela il servizio; optimizer e calendario condivisi sono quelli del checkout, "
        "identificati nei metadati. Gli output before/ e after/ contengono tutti i piani e i riferimenti.", "",
        "    python tests/run_fleet_before_after.py", ""]
    return "\n".join(lines)


def run_implementation(module, output, label, provenance):
    renderer = audit.markdown
    def labelled_report(summary, examples, metadata):
        metadata["fleet_implementation"] = label
        metadata["fleet_implementation_provenance"] = provenance
        if label == "before":
            metadata["engine_sha256"]["app/services/fleet_planning.py"] = provenance["sha256"]
        return renderer(summary, examples, metadata)
    with patch.object(audit, "fleet", module), patch.object(audit, "markdown", labelled_report), \
         patch.object(sys, "argv", ["run_fleet_simulations.py", "--output-dir", str(output)]):
        code = audit.main()
    return code, json.loads((output / "results.json").read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-file", type=Path, default=BASELINE_FILE)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "test-results/fleet-simulations")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    baseline, provenance = load_baseline(args.baseline_file)
    current = audit.fleet
    before_code, before = run_implementation(baseline, output / "before", "before", provenance)
    after_code, after = run_implementation(current, output / "after", "after", {
        "source_path": "app/services/fleet_planning.py",
        "sha256": hashlib.sha256((ROOT / "app/services/fleet_planning.py").read_bytes()).hexdigest()})
    comparison = compare_results(before, after)
    comparison["metadata"] = dict(
        baseline=provenance, after_commit=after["metadata"]["tested_commit"],
        before_metadata=before["metadata"], after_metadata=after["metadata"],
        same_policy="sponda/ZTL soft; coverage then equipment then strategy objective")
    examples = {row["case_id"] for row in after["examples"]}
    comparison["examples"] = [row for row in comparison["pairs"]
                              if row["stage"] == "base" and row["case_id"] in examples]
    report = render_comparison(comparison)
    (output / "comparison.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "report.md").write_text(report, encoding="utf-8")
    print("FLEET_BEFORE_AFTER_SUMMARY " + json.dumps(comparison["summary"], ensure_ascii=False), flush=True)
    print("FLEET_BEFORE_AFTER_EXAMPLES " + json.dumps(comparison["examples"], ensure_ascii=False), flush=True)
    print("FLEET_BEFORE_AFTER_REPORT " + json.dumps(
        dict(markdown=report, metadata=comparison["metadata"]), ensure_ascii=False), flush=True)
    summary = comparison["summary"]
    return int(bool(before_code or after_code or summary["coverage_regressions"]
                    or summary["objective_regressions"]))


if __name__ == "__main__":
    raise SystemExit(main())
