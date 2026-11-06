"""«Distribuisci il lavoro» misura le ore dell'autista senza le attese eliminabili partendo più tardi."""
from app import optimizer as opt
from app.services.fleet_working_clock import _plan_key


def _score(km, minutes, slack):
    return {'total_km': km, 'total_min': minutes, '_objective': (km, minutes, 0.0, 0, km + minutes, minutes - slack)}


def test_work_minutes_drops_only_the_absorbable_wait():
    assert opt.work_minutes(_score(10, 300, 120)) == 180
    # Risultati senza il sesto valore: si usa la partenza spostabile, se nota.
    assert opt.work_minutes({'total_km': 1, 'total_min': 300, 'departure_slack_min': 60}) == 240
    assert opt.work_minutes({'total_km': 1, 'total_min': 300, '_objective': (1, 300, 0, 0, 301)}) == 300
    assert opt.work_minutes(None) == 0


def test_afternoon_driver_is_not_counted_from_the_morning():
    rows = [{} for _ in range(4)]
    vehicles = [{}, {}]
    # Piano A: due giri di 6 ore pieni di attese. Piano B: mattino e pomeriggio, 4 ore ciascuno
    # dopo aver tolto l'attesa iniziale del pomeriggio (partenza più tarda).
    plan_a = _plan_key(((0, 1), (2, 3)), (_score(50, 360, 0), _score(50, 360, 0)), rows, vehicles, 'balanced')
    plan_b = _plan_key(((0, 1), (2, 3)), (_score(60, 240, 0), _score(60, 480, 240)), rows, vehicles, 'balanced')
    assert plan_b < plan_a
