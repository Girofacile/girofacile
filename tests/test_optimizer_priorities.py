"""Product priorities and additive public diagnostics, entirely offline."""
from copy import deepcopy
from itertools import permutations
from types import SimpleNamespace
import pytest
from app import optimizer as opt
from test_optimizer import offline, deliveries, constant_matrix, ids
from test_agents_feature import env


def test_infeasible_routes_minimize_lateness_before_count():
    rows, matrix = deliveries(2), constant_matrix(2, km=1, minutes=1)
    for row in rows:
        row.update(scarico_mattina_da="08:00", scarico_mattina_a="08:01")
    matrix[0, 1]["min"] = 2
    matrix[2, 1]["min"] = 100
    a = opt._evaluate_fixed_sequence(rows, matrix, [], return_depot=False)
    b = opt._evaluate_fixed_sequence(rows[::-1], matrix, [], return_depot=False)
    assert (a["violations"], a["total_lateness_min"]) == (2, 3)
    assert (b["violations"], b["total_lateness_min"]) == (1, 100)
    result = opt._best_internal_sequence(rows, matrix, [], return_depot=False)
    assert ids(result) == [1, 2]
    assert opt.solution_key(result) < opt.solution_key(b)


def test_equal_lateness_prefers_fewer_violations_then_score():
    a = dict(violations=1, total_lateness_min=10, score=200000)
    b = dict(violations=2, total_lateness_min=10, score=1)
    assert opt.solution_key(a) < opt.solution_key(b)
    assert opt.solution_key(dict(a, score=100)) < opt.solution_key(a)
    # Feasibility cannot be bought with minutes, distance, or score.
    assert opt.solution_key(dict(a, violations=0, total_lateness_min=0, score=1e30, total_km=1e30, total_min=1e30)) < opt.solution_key(a)


@pytest.mark.parametrize("n", [2, 9, 16])
def test_comparator_applies_to_every_search_branch(monkeypatch, n):
    rows = deliveries(n)
    def evaluate(seq, *args, **kwargs):
        feasible = bool(seq) and seq[0]["customer_id"] == n
        return dict(ordered=[dict(d) for d in seq], score=1e8 if feasible else 1,
                    violations=0 if feasible else 1, total_lateness_min=0 if feasible else 10,
                    total_km=1, total_min=1)
    monkeypatch.setattr(opt, "_evaluate_fixed_sequence", evaluate)
    # Large-route search has a score-only evaluator as well as final rendering.
    from app.services.optimizer_search import RouteEvaluator
    def score_only(self, seq, *args, **kwargs):
        self.candidates += 1
        return {**evaluate(seq), '_search_order': tuple(d['_matrix_index'] for d in seq)}
    monkeypatch.setattr(RouteEvaluator, "evaluate", score_only)
    monkeypatch.setattr(opt, "_greedy_sequence", lambda *a, **k: rows[:])
    assert opt._local_optimize_sequence(rows, {}, [])["violations"] == 0
    assert opt._best_internal_sequence(rows, constant_matrix(n), [])["violations"] == 0


@pytest.mark.parametrize("entrypoint", [opt.optimize_route, opt.recalculate_manual_route])
@pytest.mark.parametrize("late", [False, True])
def test_public_timing_and_violation_details(monkeypatch, entrypoint, late):
    rows = deliveries(1)
    rows[0].update(scarico_mattina_da="09:00", scarico_mattina_a="09:10" if late else "10:00", tempo_scarico_min=15)
    monkeypatch.setattr(opt, "build_distance_matrix", lambda *a, **k: constant_matrix(1, 2, 40))
    depot = SimpleNamespace(id=1, user_id=1, lat=45, lon=9, indirizzo="Depot")
    result = entrypoint(None, depot, rows, route_date="2099-01-01")
    row = result["ordered"][0]
    assert (row["arrivo_fisico"], row["attesa_min"], row["inizio_servizio"], row["arrivo_stimato"], row["partenza_stimata"]) == ("08:40",20,"09:00","09:00","09:15")
    assert result["violations_count"] == int(late)
    assert result["total_lateness_min"] == (5 if late else 0)
    assert result["total_wait_min"] == 20
    assert {"ordered", "total_km", "total_min", "return_time", "google_maps_url"} <= result.keys()
    if late:
        detail = result["time_window_violations"][0]
        assert detail["customer_id"] == 1
        assert detail["window"] == {"start":"09:00", "end":"09:10"}
        assert detail["arrivo_fisico"] == "08:40" and detail["fine_servizio"] == "09:15"
        assert detail["lateness_min"] == 5 and detail["warning"]
    else:
        assert result["time_window_violations"] == [] and row["time_window_violation"] is None


def test_two_windows_and_midnight_diagnostics():
    rows = deliveries(1)
    rows[0].update(scarico_mattina_da="00:00", scarico_mattina_a="00:05",
                   scarico_pomeriggio_da="01:00", scarico_pomeriggio_a="02:00", tempo_scarico_min=10,
                   ztl=True, sponda=True)
    result = opt._best_internal_sequence(rows, constant_matrix(1), [], start_time="00:00")
    stop = result["ordered"][0]
    assert stop["arrivo_fisico"] == "00:05" and stop["inizio_servizio"] == "01:00"
    assert result["total_wait_min"] == 55
    assert result["violations_count"] == 0 and result["time_window_violations"] == []
    assert "ZTL" in stop["warning"] and "Sponda" in stop["warning"]


@pytest.mark.parametrize("endpoint", ["optimize", "recalculate-manual"])
def test_http_diagnostics_survive_save_and_reload(env, monkeypatch, endpoint):
    from app.models import Deposit
    from app.routers import routes
    client, db, user, *_ = env
    client.app.include_router(routes.router)
    user.has_time_windows = True
    deposit = Deposit(user_id=user.id, nome="Test", indirizzo="Depot", lat=45, lon=9)
    db.add(deposit); db.commit()
    monkeypatch.setattr(opt, "build_distance_matrix", lambda *a, **k: constant_matrix(1, 2, 40))
    data = dict(nome="Test", data_giro="2099-01-01", orario_partenza="08:00", deposit_id=deposit.id,
                consegne=[dict(cliente_nome="Client", indirizzo="Test", lat=45.1,lon=9.1,
                scarico_mattina_da="09:00",scarico_mattina_a="09:10",tempo_scarico_min=15)])
    response = client.post('/api/routes/'+endpoint,json=data)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["violations_count"] == 1 and payload["total_lateness_min"] == 5
    assert payload["status"] == "bozza"
    from app.models import RoutePlan
    saved = routes.serialize_route(db.get(RoutePlan, payload["id"]))
    for key in ("violations_count", "total_lateness_min", "total_wait_min", "time_window_violations"):
        assert saved[key] == payload[key]
    for key in ("arrivo_fisico", "inizio_servizio", "arrivo_stimato", "partenza_stimata", "attesa_min"):
        assert saved["consegne"][0][key] == payload["consegne"][0][key]

@pytest.mark.parametrize("n", [3, 9, 15])
def test_exact_fallback_recovers_feasible_chain_missed_by_seeds(n):
    rows = deliveries(n)
    matrix = constant_matrix(n, km=1, minutes=100)
    for i, row in enumerate(rows, 1):
        row.update(scarico_mattina_da="08:00", scarico_mattina_a=opt.fmt_hhmm(480 + i), tempo_scarico_min=0)
        matrix[i-1, i]["min"] = 1
    bad = opt._evaluate_fixed_sequence(rows[::-1], matrix, [], return_depot=False)
    result = opt._feasible_fallback(rows, matrix, [], None, False, "08:00", bad)
    assert result["violations"] == 0
    assert ids(result) == list(range(1, n+1))
    assert result["total_min"] == n
    assert [d["inizio_servizio"] for d in result["ordered"]] == [opt.fmt_hhmm(480+i) for i in range(1,n+1)]


def test_exact_fallback_matches_independent_feasibility_enumeration():
    # Independent fixed-window simulator, without optimizer candidate evaluation.
    import random
    rng = random.Random(93)
    for _ in range(15):
        rows = deliveries(4)
        matrix = constant_matrix(4)
        for leg in matrix.values(): leg["min"] = rng.randint(1, 9)
        closes = [rng.randint(4, 30) for _ in rows]
        for row, close in zip(rows, closes):
            row.update(scarico_mattina_da="08:00", scarico_mattina_a=opt.fmt_hhmm(480+close), tempo_scarico_min=2)
        feasible = False
        for order in permutations(range(4)):
            clock, previous = 0, 0
            valid = True
            for i in order:
                clock += matrix[previous, i+1]["min"] + 2
                valid = valid and clock <= closes[i]
                previous = i+1
            feasible |= valid
        best = opt._evaluate_fixed_sequence(rows, matrix, [], return_depot=False)
        result = opt._feasible_fallback(rows, matrix, [], None, False, "08:00", best)
        assert (result["violations"] == 0) == feasible


def test_existing_database_adds_diagnostics_column_idempotently(env):
    import ast
    from pathlib import Path
    import sqlalchemy
    from app.database import Base
    _, db, user, *_ = env
    user_id = user.id
    engine = db.get_bind()
    db.close()
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text("ALTER TABLE deliveries DROP COLUMN optimizer_details"))
    tree = ast.parse(Path("app/main.py").read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "migrate_database")
    namespace = {**vars(sqlalchemy), "Base": Base, "engine": engine}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "app/main.py", "exec"), namespace)
    namespace["migrate_database"]()
    namespace["migrate_database"]()
    assert "optimizer_details" in {c["name"] for c in sqlalchemy.inspect(engine).get_columns("deliveries")}
    from app.models import User
    assert db.get(User, user_id) is not None
