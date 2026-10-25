"""Score fixed-membership route orders without rebuilding ETA/display details.

Only parsing and output construction are removed: the earliest-window selector
and pause arithmetic are the same functions used by the canonical scheduler.
"""
import math


class FixedRouteEvaluator:
    def __init__(self, rows, sequence, matrix, points, vehicle, return_depot,
                 start_time, available_minutes):
        from .. import optimizer as opt
        from . import driver_schedule as shifts
        self.opt, self.shifts = opt, shifts
        self.start = opt._start_clock(start_time)
        self.return_depot = return_depot
        self.available_minutes = available_minutes
        self.rows = {index: rows[index] for index in sequence}
        self.windows = {index: opt.delivery_windows(row) for index, row in self.rows.items()}
        self.service = {index: float(row.get("tempo_scarico_min") or 0)
                        for index, row in self.rows.items()}
        schedule = (vehicle or {}).get("driver_schedule") or {}
        self.pauses = shifts.intervals(schedule)
        self.shift = ((shifts.minutes(schedule["start"]), shifts.minutes(schedule["end"]))
                      if schedule.get("start") else None)
        self.load_valid = True
        try:
            opt.validate_vehicle_load(list(self.rows.values()), vehicle)
        except ValueError:
            self.load_valid = False
        nodes = {-1: 0, **{index: rows[index]["_matrix_index"] for index in sequence}}
        self.legs = {(a, b): opt._matrix_leg(matrix, points, origin, destination)
                     for a, origin in nodes.items() for b, destination in nodes.items()
                     if a != b}

    def __call__(self, order):
        if not self.load_valid or (self.shift and self.start < self.shift[0]):
            return None
        clock, previous, km = self.start, -1, 0.0
        opt, shifts, pauses = self.opt, self.shifts, self.pauses
        for index in order:
            row, service, windows = self.rows[index], self.service[index], self.windows[index]
            leg = self.legs[previous, index]
            physical_arrival = shifts.travel_end(clock, leg["min"], pauses)
            ev = opt._earliest_feasible_candidate(
                clock, {**leg, "min": physical_arrival-clock}, row,
                windows=windows, service_min=service)
            if pauses:
                for _ in range(len(pauses)+1):
                    ready = shifts.service_ready(ev["service_start"], service, pauses)
                    if ready == ev["service_start"]:
                        break
                    ev = opt._earliest_feasible_candidate(
                        clock, {**leg, "min": ready-clock}, row,
                        windows=windows, service_min=service)
            if not ev.get("feasible", True):
                return None
            clock = ev["service_start"] + service
            km += leg["km"]
            previous = index
        if self.return_depot and order:
            back = self.legs[previous, -1]
            km += back["km"]
            clock = shifts.travel_end(clock, back["min"], pauses)
        duration = clock-self.start
        if (self.shift and clock > self.shift[1]) or math.ceil(duration) > self.available_minutes:
            return None
        return {"total_km": round(km, 2), "total_min": round(duration, 1),
                "_objective": (km, duration, 0.0, 0)}
