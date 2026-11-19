"""Messaggi sul turno: un orario oltre la mezzanotte si legge come ora del giorno dopo."""
from app.services.driver_schedule import clock, day_clock, shift_error

SCHEDULE = {"start": "07:00", "end": "16:00"}


def test_end_after_midnight_is_written_as_next_day():
    # Partenza alle 22:33 (giro in ritardo) e 320 minuti di giro: fine alle 03:53 del giorno dopo.
    message = shift_error(SCHEDULE, 22 * 60 + 33, 22 * 60 + 33 + 320)
    assert "03:53 del giorno dopo" in message and "27:53" not in message


def test_same_day_times_are_unchanged():
    assert day_clock(13 * 60 + 43) == "13:43" == clock(13 * 60 + 43)
    assert "17:10, dopo la fine del turno" in shift_error(SCHEDULE, 8 * 60, 17 * 60 + 10)
    assert day_clock(2 * 1440 + 5) == "00:05 di 2 giorni dopo"
