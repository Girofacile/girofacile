from run_pyvrp_r104_benchmark import load_instance, prepare, verify


def test_official_instance_uses_nine_vehicles_and_preserves_solomon_window_semantics():
    raw, provenance = load_instance()
    assert raw['name'] == 'R104' and len(raw['demand']) == 101
    assert provenance['benchmark_vehicles'] == 9 and int(raw['capacity']) == 200
    rows, vehicles, matrix, limits = prepare(raw, 9)
    assert len(rows) == 100 and len(vehicles) == 9 and limits == [230] * 9
    # Solomon limits the START of service, while GiroFacile limits its completion.
    from app.optimizer import parse_hhmm
    assert parse_hhmm(rows[0]['scarico_mattina_a']) == int(raw['time_window'][1, 1] + raw['service_time'][1])
    assert matrix[0, 1]['km'] == float(raw['edge_weight'][0, 1])


def test_checker_detects_duplicate_customers_and_handles_missing_solver_answer():
    raw, _ = load_instance()
    bad = verify(raw, [[0, 0]], 9)
    assert 'duplicate-customer' in bad['independent_errors'] and bad['served'] == 1
    assert verify(raw, None, 9)['independent_errors'] == ['no-feasible-solver-answer']
