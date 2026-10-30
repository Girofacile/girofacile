"""The same fifty deliveries on two, three, four and five vehicles.

These comparisons extend the new October audit; they deliberately reuse its
fifty-stop geometry so changes in fleet size do not change the road problem.
The operational windows are constructed from an independent feasible witness,
never from production solver answers. They do not certify global optimality.
"""
from copy import deepcopy
import math

from routing_quality_fleet import fleet_cases
from routing_quality_oracle import plan_metrics, replay


def _hhmm(minutes):
    value = int(minutes)
    if not 0 <= value < 1440:
        raise ValueError('Focused audit windows must stay in the same day')
    return f'{value // 60:02d}:{value % 60:02d}'


def fifty_cases():
    """Return eight cases: four resource counts and two constraint profiles.

    Every delivery has one kg and one parcel. Capacity is ceil(50 / vehicles),
    making all selected vehicles necessary for complete coverage. This is an
    explicit experimental control, not a claim about a real customer's fleet.
    """
    template = next(case for case in fleet_cases(False)
                    if case['id'] == 'fleet-new-scale-50')
    cases = []
    for count in (2, 3, 4, 5):
        capacity = math.ceil(50 / count)
        baseline = deepcopy(template)
        baseline.update(
            id=f'fifty-shared-{count}-baseline',
            family='fifty-fixed-geometry-baseline',
            resources=[deepcopy(template['resources'][0]) for _ in range(count)],
            witness=[list(range(resource, 50, count)) for resource in range(count)],
            reference='witness', requested_vehicles=count,
            profile='baseline', comparison_group='same-fifty-october-geometry',
            capacity_semantics='one kg and one parcel per delivery; capacity ceil(50 / vehicles)',
            source_case_id=template['id'])
        for resource in baseline['resources']:
            resource.update(capacita_kg=capacity, capacita_colli=capacity)
        if not plan_metrics(baseline, baseline['witness'])['feasible']:
            raise AssertionError('Baseline witness must serve all fifty deliveries')
        cases.append(baseline)

        constrained = deepcopy(baseline)
        constrained.update(id=f'fifty-shared-{count}-constrained',
                           family='fifty-fixed-geometry-windows-shifts-breaks',
                           profile='constrained',
                           window_generation='Independent witness timings, with 35 minutes before / 45 after service')
        for resource in constrained['resources']:
            resource.update(max_minutes=600, driver_schedule={
                'start': '08:00', 'end': '18:00',
                'breaks': [{'start': '10:30', 'end': '11:00'},
                           {'start': '14:00', 'end': '14:15'}]})
        # Replay without windows first. The resulting fixed-break schedule is
        # a constructive feasibility witness, independent of the engine.
        for resource_index, order in enumerate(constrained['witness']):
            timing = replay(constrained, resource_index, order)
            if not timing['feasible']:
                raise AssertionError('Shift-and-break witness must be feasible before adding windows')
            for visit in timing['stops']:
                row = constrained['stops'][visit['index']]
                opening = max(480, math.floor(visit['service_start'] - 35))
                closing = min(18 * 60, math.ceil(visit['service_end'] + 45))
                period = 'mattina' if visit['service_start'] < 12 * 60 else 'pomeriggio'
                row[f'scarico_{period}_da'] = _hhmm(opening)
                row[f'scarico_{period}_a'] = _hhmm(closing)
        if not plan_metrics(constrained, constrained['witness'])['feasible']:
            raise AssertionError('Windowed witness must still serve all fifty deliveries')
        cases.append(constrained)
    return cases
