"""PyVRP propone piani multi-mezzo migliori senza mai violare i vincoli; senza PyVRP nulla cambia.

Ogni giro proposto è ricontrollato con il riferimento indipendente routing_quality_oracle.
"""
import pytest

from fleet_upgrade_cases import _base
from routing_quality_fleet import run_fleet
from routing_quality_oracle import plan_metrics
from app.services import fleet_pyvrp

pytest.importorskip('pyvrp')


@pytest.fixture(scope='module')
def case():
    return _base(2, 'windows_shifts', 2027111211, 'development')


def test_time_budget_scales_with_stops(monkeypatch):
    monkeypatch.setenv('FLEET_PYVRP_SECONDS', '30')
    assert [fleet_pyvrp.seconds_budget(n) for n in (2, 50, 200)] == [1.0, 15.0, 30.0]
    monkeypatch.setenv('FLEET_PYVRP_SECONDS', '0')
    assert fleet_pyvrp.seconds_budget(50) == 0.0


def test_pyvrp_proposal_is_valid_and_never_worse(case, monkeypatch):
    baseline = run_fleet(case, 'efficient', budget=4000)
    monkeypatch.setenv('FLEET_PYVRP_SECONDS', '3')
    improved = run_fleet(case, 'efficient', budget=4000)
    report = improved['diagnostics']['ortools']
    assert report['mode'] == 'pyvrp' and report['feasible'], report
    before, after = plan_metrics(case, baseline['routes']), plan_metrics(case, improved['routes'])
    assert after['feasible'] and after['served'] >= before['served']
    assert after['served'] > before['served'] or after['cost'] <= before['cost'] + 1e-6
    assert improved['external_calls'] == 0 and not improved['mutation_detected']


def test_solver_error_keeps_current_plan(case, monkeypatch):
    baseline = run_fleet(case, 'efficient', budget=4000)
    monkeypatch.setenv('FLEET_PYVRP_SECONDS', '3')
    def broken(*args, **kwargs):
        raise RuntimeError('solutore non disponibile')
    monkeypatch.setattr(fleet_pyvrp, 'improve', broken)
    result = run_fleet(case, 'efficient', budget=4000)
    assert result['diagnostics']['ortools'] == {'status': 'error', 'error': 'RuntimeError'}
    assert result['routes'] == baseline['routes']


def test_balanced_strategy_uses_pyvrp_and_missing_library_skips_it(case, monkeypatch):
    monkeypatch.setenv('FLEET_PYVRP_SECONDS', '3')
    called = []
    monkeypatch.setattr(fleet_pyvrp, 'improve', lambda *a, **k: called.append(a[-1]) or (None, {}))
    run_fleet(case, 'balanced', budget=4000)
    assert called == ['balanced']
    monkeypatch.setattr(fleet_pyvrp, 'available', lambda: False)
    assert run_fleet(case, 'efficient', budget=4000)['diagnostics']['ortools'] == {'status': 'disabled'}
    assert called == ['balanced']


# Piccoli problemi costruiti a mano: chilometri = minuti sulla retta dei punti.
def _line(positions):
    points = [0] + list(positions)
    return {(i, j): {'km': abs(points[i] - points[j]), 'min': abs(points[i] - points[j])}
            for i in range(len(points)) for j in range(len(points))}


def _row(customer_id, morning=None, afternoon=None, service=10, kg=0, colli=0, sponda=False):
    row = dict(customer_id=customer_id, tempo_scarico_min=service, peso_kg=kg, colli=colli,
               sponda=sponda, ztl=False)
    if morning:
        row.update(scarico_mattina_da=morning[0], scarico_mattina_a=morning[1])
    if afternoon:
        row.update(scarico_pomeriggio_da=afternoon[0], scarico_pomeriggio_a=afternoon[1])
    return row


def _vehicle(start='08:00', end='17:00', breaks=(), kg=None, colli=None, sponda=True):
    return dict(driver_schedule={'start': start, 'end': end,
                                 'breaks': [{'start': a, 'end': b} for a, b in breaks]},
                capacita_kg=kg, capacita_colli=colli, ha_sponda=sponda, accesso_ztl=True)


def _oracle(rows, vehicles, matrix, limits, orders, start='08:00'):
    case = dict(kind='fleet', start_time=start, return_depot=True, matrix=matrix,
                stops=[dict(row, customer_id=i + 1) for i, row in enumerate(rows)],
                resources=[dict(v, max_minutes=limits[i]) for i, v in enumerate(vehicles)])
    return plan_metrics(case, orders)


def test_breaks_and_two_windows_are_respected():
    # Il cliente 2 apre solo il pomeriggio, dopo la pausa: PyVRP sceglie la fascia giusta.
    rows = [_row(1, ('08:00', '09:00')), _row(2, ('08:00', '08:05'), ('13:30', '15:00')),
            _row(3, ('09:00', '12:00'))]
    vehicles = [_vehicle(breaks=[('12:00', '13:00')])]
    matrix, limits = _line([20, 200, 40]), [540]
    orders, report = fleet_pyvrp.improve(rows, vehicles, matrix, '08:00', True, limits, ((),), 2)
    assert report['feasible'] and sorted(orders[0]) == [0, 1, 2]
    metrics = _oracle(rows, vehicles, matrix, limits, orders)
    assert metrics['feasible'] and metrics['served'] == 3, metrics['routes'][0]['errors']


def test_capacity_limits_leave_out_only_what_cannot_fit():
    # 5 consegne da 40 colli, un solo mezzo da 100: al massimo 2 servite, mai un giro in sovraccarico.
    rows = [_row(i, kg=10, colli=40) for i in range(1, 6)]
    vehicles = [_vehicle(colli=100)]
    matrix, limits = _line([5, 6, 7, 8, 9]), [540]
    orders, report = fleet_pyvrp.improve(rows, vehicles, matrix, '08:00', True, limits, ((),), 2)
    assert report['feasible'] and len(orders[0]) == 2
    assert _oracle(rows, vehicles, matrix, limits, orders)['feasible']


def test_drivers_with_different_hours_keep_their_own_windows():
    # Il secondo autista inizia alle 10: il cliente che chiude alle 9 resta al primo.
    rows = [_row(1, ('08:00', '09:00')), _row(2, ('10:00', '16:00')), _row(3, ('10:00', '16:00'))]
    # Come build_vehicle_dict: chi inizia dopo l'orario comune parte a inizio turno.
    vehicles = [_vehicle(end='09:30'), dict(_vehicle(start='10:00', end='17:00'), departure='10:00')]
    matrix, limits = _line([10, 30, 31]), [90, 540]
    orders, report = fleet_pyvrp.improve(rows, vehicles, matrix, '08:00', True, limits, ((), ()), 2)
    assert report['feasible'] and report['clocks'] == 2
    assert 0 in orders[0] and sorted(orders[0] + orders[1]) == [0, 1, 2]
    assert _oracle(rows, vehicles, matrix, limits, orders)['feasible']


def test_missing_tail_lift_is_avoided_when_another_vehicle_has_it():
    rows = [_row(1, sponda=True), _row(2)]
    vehicles = [_vehicle(sponda=False), _vehicle(sponda=True)]
    matrix, limits = _line([10, 11]), [540, 540]
    orders, _ = fleet_pyvrp.improve(rows, vehicles, matrix, '08:00', True, limits, ((), ()), 2)
    assert 0 in orders[1]


def test_balanced_spreads_the_work_where_shortest_km_would_use_one_driver():
    # Quattro consegne vicine: per i soli km basta un mezzo, per l'equilibrio servono entrambi.
    rows = [_row(i, service=60) for i in range(1, 5)]
    vehicles = [_vehicle(), _vehicle()]
    matrix, limits = _line([10, 11, 12, 13]), [540, 540]
    efficient, _ = fleet_pyvrp.improve(rows, vehicles, matrix, '08:00', True, limits, ((), ()), 2)
    balanced, report = fleet_pyvrp.improve(rows, vehicles, matrix, '08:00', True, limits, ((), ()), 2, 'balanced')
    assert sum(bool(order) for order in efficient) == 1
    assert sorted(map(len, balanced)) == [2, 2] and report['balance']['steps']
    assert _oracle(rows, vehicles, matrix, limits, balanced)['feasible']
