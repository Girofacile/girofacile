"""Physical calendars and canonically checked proposals for the native solver."""
import random

import pytest

from app.services.driver_schedule import travel_end
from app.services.fleet_working_clock import TIME_SCALE, service_domains, working_clock


def vehicle(**updates):
    row = dict(capacita_kg=3, capacita_colli=3, ha_sponda=True, accesso_ztl=True,
        driver_schedule={'start': '08:00', 'end': '12:00', 'breaks': []})
    row.update(updates)
    return row


def test_compressed_clock_matches_ten_thousand_real_driving_transitions():
    pauses = [(555, 570), (715, 740)]
    rng = random.Random(20311031)
    for _ in range(10_000):
        start, drive = rng.uniform(480, 900), rng.uniform(0, 180)
        arrival = travel_end(start, drive, pauses)
        assert working_clock(arrival, pauses, 480) == pytest.approx(
            working_clock(start, pauses, 480) + drive, abs=1e-9)


def test_service_domains_do_not_split_unloading_and_wait_can_absorb_break():
    resource = vehicle(driver_schedule={'start': '08:00', 'end': '12:00',
        'breaks': [{'start': '08:15', 'end': '08:30'}]})
    domains, horizon = service_domains(dict(tempo_scarico_min=10,
        scarico_mattina_da='08:00', scarico_mattina_a='08:40'), resource, 480, 240)
    assert domains == ((0, 5*TIME_SCALE), (15*TIME_SCALE, 15*TIME_SCALE))
    assert horizon == 225*TIME_SCALE


def test_zero_duration_service_at_break_start_is_not_treated_as_before_break():
    resource = vehicle(driver_schedule={'start': '08:00', 'end': '12:00',
        'breaks': [{'start': '08:15', 'end': '08:30'}]})
    domains, _ = service_domains(dict(tempo_scarico_min=0,
        scarico_mattina_da='08:00', scarico_mattina_a='08:15'), resource, 480, 240)
    assert domains == ((0, 15*TIME_SCALE-1),)


def test_later_driver_cannot_leave_before_the_common_departure():
    domains, horizon = service_domains({}, vehicle(driver_schedule={
        'start': '09:00', 'end': '12:00', 'breaks': []}), 480, 240)
    assert domains == () and horizon == 0

