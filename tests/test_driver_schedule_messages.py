"""Il messaggio del turno dice la causa: partenza troppo presto o rientro troppo tardi."""
from app.services.driver_schedule import shift_error

SHIFT = {'start': '09:00', 'end': '18:00', 'breaks': []}


def test_departure_before_shift_start_names_the_start():
    message = shift_error(SHIFT, 7 * 60, 12 * 60)
    assert 'partenza (07:00)' in message and 'alle 09:00' in message


def test_return_after_shift_end_names_the_return_time():
    message = shift_error(SHIFT, 9 * 60, 18 * 60 + 16)
    assert 'finisce alle 18:16' in message


def test_route_inside_the_shift_has_no_error():
    assert shift_error(SHIFT, 9 * 60, 18 * 60) is None
