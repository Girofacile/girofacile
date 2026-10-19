"""Execution projections reapply waits even without driver breaks."""
import json
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace as N
import pytest
from app.services.route_schedule import LOCAL, route_schedule_datetimes

DAY = date(2099, 1, 15)


def stop(id, arrival, departure, *, travel=20, wait=0, window=None, unload=10):
    return N(id=id, ordine=id, arrivo_stimato=arrival, partenza_stimata=departure,
        minuti_tappa=travel, km_tappa=1, attesa_min=wait, tempo_scarico_min=unload,
        optimizer_details='{}', scarico_mattina_da=window[0] if window else None,
        scarico_mattina_a=window[1] if window else None,
        scarico_pomeriggio_da=None, scarico_pomeriggio_a=None)


def plan(deliveries, *, start=time(8), started=time(8), returned=time(10, 20), schedule=None):
    return N(data_giro=DAY, orario_partenza=start, started_at=datetime.combine(DAY, started),
        orario_rientro_stimato=returned, totale_minuti=140, status='in_corso',
        deliveries=deliveries, driver_schedule=schedule or {}, rientro_deposito=True,
        routing_snapshot_json=json.dumps({'base_legs': [{'min': 10}]}),
        traffic_result_json='{}', position=None)


@pytest.mark.parametrize('completed', [time(8, 50), time(9, 30)])
def test_early_completion_and_delay_consume_opening_wait(completed):
    first = stop(1, time(9), time(9, 10), travel=60)
    second = stop(2, time(10), time(10, 10), travel=20, wait=30, window=(time(10), time(11)))
    actual = datetime.combine(DAY, completed)
    result = route_schedule_datetimes(plan([first, second]), {1: N(status='completata', completata_il=actual)})
    assert result['deliveries'][1]['arrival'] == actual.replace(tzinfo=LOCAL)
    assert result['deliveries'][2]['arrival'] == datetime.combine(DAY, time(10), LOCAL)
    assert result['deliveries'][2]['source'] == 'execution'
    assert result['deliveries'][2]['updated_at'] == actual.replace(tzinfo=LOCAL)
    assert result['return_at'] == datetime.combine(DAY, time(10, 20), LOCAL)


def test_late_departure_consumes_wait_before_first_service():
    first = stop(1, time(9), time(9, 10), travel=20, wait=40, window=(time(9), time(10)))
    result = route_schedule_datetimes(plan([first], started=time(8, 30), returned=time(9, 20)))
    assert result['deliveries'][1]['arrival'] == datetime.combine(DAY, time(9), LOCAL)
    assert result['return_at'] == datetime.combine(DAY, time(9, 20), LOCAL)


def test_completion_seconds_do_not_move_the_opening_time():
    first = stop(1, time(9), time(9, 10), travel=60)
    second = stop(2, time(10), time(10, 10), travel=20, wait=30, window=(time(10), time(11)))
    statuses = {1: N(status='mancata', completata_il=datetime.combine(DAY, time(8, 50, 30)))}
    result = route_schedule_datetimes(plan([first, second]), statuses)
    assert result['deliveries'][2]['arrival'] == datetime.combine(DAY, time(10), LOCAL)


def test_legacy_missing_legs_reuse_saved_times_without_provider_calls():
    result = route_schedule_datetimes(plan([
        stop(1, time(9), time(9, 10), travel=0),
        stop(2, time(10), time(10, 10), travel=0)], started=time(8, 25)))
    assert result['deliveries'][1]['arrival'].time() == time(9, 25)
    assert result['deliveries'][2]['arrival'].time() == time(10, 25)


def test_execution_projection_keeps_the_date_after_midnight():
    route = plan([stop(1, time(23, 50), time(0, 10), travel=50, unload=20),
                  stop(2, time(0, 40), time(0, 50), travel=30)],
                 start=time(23), started=time(23, 10), returned=time(1))
    result = route_schedule_datetimes(route)
    tomorrow = DAY + timedelta(days=1)
    assert result['deliveries'][1]['arrival'] == datetime.combine(tomorrow, time(0), LOCAL)
    assert result['deliveries'][2]['arrival'] == datetime.combine(tomorrow, time(0, 50), LOCAL)
    assert result['return_at'] == datetime.combine(tomorrow, time(1, 10), LOCAL)


def test_execution_projection_keeps_fixed_pause_in_place():
    route = plan([stop(1, time(8, 10), time(8, 20), travel=10)],
        started=time(8, 30), returned=time(8, 30),
        schedule={'breaks': [{'start': '08:15', 'end': '08:45'}]})
    result = route_schedule_datetimes(route)
    assert result['deliveries'][1]['arrival'].time() == time(8, 55)
    assert result['return_at'].time() == time(9, 15)


def test_unknown_leg_and_estimate_remain_unknown():
    result = route_schedule_datetimes(plan([stop(1, None, None, travel=None)], started=time(8, 30)))
    assert result['deliveries'][1]['arrival'] is None
