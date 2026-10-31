"""Fresh development and held-out problems for the adaptive fleet upgrade.

Each problem contains fifty fictional deliveries and a frozen directed road
matrix. Feasible witnesses are constructed without the production search:
membership, loads and compatible tail lifts are chosen first; an independent
calendar then supplies windows around an already feasible itinerary. The data
do not prove global optimality, predict live traffic, or model EV autonomy.

``max_minutes`` remains a booking/day availability horizon, not a configurable
maximum route duration. Electric/diesel consumption and prices are accounting
inputs only; no unsupported battery-range constraint is invented here.
"""
from copy import deepcopy
import math
import random

from routing_quality_fleet import _case, _geometry, _resource, _stop
from routing_quality_oracle import plan_metrics, replay


FAMILIES = ('geography_capacity', 'windows_shifts', 'scarce_tail_lift', 'combined_tight')
COUNTS = (2, 3, 4, 5)


def _hhmm(value):
    value = int(value)
    if not 0 <= value < 1440:
        raise ValueError('Upgrade scenarios use same-day clocks')
    return f'{value // 60:02d}:{value % 60:02d}'


def _nearest_order(indices, matrix):
    pending, sequence, previous = set(indices), [], 0
    while pending:
        selected = min(pending, key=lambda i: (
            matrix[previous, i + 1]['min'], matrix[previous, i + 1]['km'], i))
        sequence.append(selected)
        pending.remove(selected)
        previous = selected + 1
    return sequence


def _memberships(coords, count, rng, geographic):
    indices = list(range(50))
    if geographic:
        depot = coords[0]
        indices.sort(key=lambda i: math.atan2(coords[i + 1]['lat'] - depot['lat'],
                                             coords[i + 1]['lon'] - depot['lon']))
        return [indices[i * 50 // count:(i + 1) * 50 // count] for i in range(count)]
    rng.shuffle(indices)
    return [indices[resource::count] for resource in range(count)]


def _base(count, family, seed, split):
    rng = random.Random(seed)
    matrix, coords = _geometry(50, seed, spread=5.5 if split == 'holdout' else 4.6)
    memberships = _memberships(coords, count, rng, family == 'geography_capacity')
    orders = [_nearest_order(members, matrix) for members in memberships]
    rows = [_stop(i, weight=rng.choice((5, 10, 15, 20, 25)),
                  packages=rng.choice((1, 1, 2, 3)), service=rng.choice((2, 3, 4, 5, 6)),
                  lat=coords[i + 1]['lat'], lon=coords[i + 1]['lon']) for i in range(50)]
    resources = []
    equipment_family = family in ('scarce_tail_lift', 'combined_tight')
    for resource_index, order in enumerate(orders):
        lift = not equipment_family or (resource_index + seed) % 2 == 0
        access = resource_index % 3 != 1
        electric = resource_index % 2 == 0
        weight = sum(rows[i]['peso_kg'] for i in order)
        parcels = sum(rows[i]['colli'] for i in order)
        quantum = 10 if family == 'combined_tight' else 25
        cap = math.ceil(weight / quantum) * quantum
        schedule = {'start': '07:30' if resource_index % 2 else '08:00',
                    'end': '19:00', 'breaks': []}
        if family != 'geography_capacity':
            first = 9 * 60 + 15 + resource_index * 9
            second = 11 * 60 + 55 + resource_index * 7
            schedule['breaks'] = [
                {'start': _hhmm(first), 'end': _hhmm(first + 15 + resource_index % 2 * 5)},
                {'start': _hhmm(second), 'end': _hhmm(second + 25)},
            ]
        resources.append(_resource(cap, parcels + (0 if family == 'combined_tight' else 1),
            available=660, schedule=schedule, ha_sponda=lift, accesso_ztl=access,
            alimentazione='elettrico' if electric else 'gasolio',
            consumo_primario_100km=0 if electric else 8.3 + resource_index * .4,
            consumo_kwh_100km=18.5 + resource_index * .7 if electric else 0,
            energy_price_primary=1.87 + resource_index * .02,
            energy_price_electric=.29 + resource_index * .015))
        for position, index in enumerate(order):
            rows[index]['sponda'] = bool(equipment_family and lift and
                (position % 2 == 0 or family == 'combined_tight' and position % 3 == 1))
            # ZTL remains advisory in the application; a compatible witness is
            # nevertheless useful when comparing the equipment preference.
            rows[index]['ztl'] = bool(access and (index + seed) % 7 == 0)
    case = _case(f'upgrade-{split}-{count}-{family}-{seed}', family, rows,
        resources, matrix, reference='witness', seed=seed, witness=orders,
        split=split, hard_tail_lift=True, expected_served=50, expected_unassigned=[],
        expected_upper_bound=50, requested_vehicles=count,
        witness_origin='independent constructive membership and calendar; no production answer',
        generated_for='fleet-adaptive-upgrade', electric_range_modelled=False)
    if family != 'geography_capacity':
        _add_windows_and_available_turns(case, family, rng)
    _validate_witness(case)
    return case


def _add_windows_and_available_turns(case, family, rng):
    for resource_index, order in enumerate(case['witness']):
        timing = replay(case, resource_index, order)
        if not timing['feasible']:
            raise AssertionError('Constructed membership must fit the initial full working day')
        slack = {'windows_shifts': 70, 'scarce_tail_lift': 90, 'combined_tight': 35}[family]
        if case['split'] == 'holdout':
            slack += rng.choice((-10, 0, 15))
        latest_break = max(int(b['end'][:2]) * 60 + int(b['end'][3:])
                           for b in case['resources'][resource_index]['driver_schedule']['breaks'])
        end = min(19 * 60, 15 * math.ceil(max(480 + timing['minutes'] + slack,
                                             latest_break + 30) / 15))
        resource = case['resources'][resource_index]
        resource['driver_schedule']['end'] = _hhmm(end)
        resource['max_minutes'] = end - 480
        for position, visit in enumerate(timing['stops']):
            row = case['stops'][visit['index']]
            # Some stops remain flexible: the planner must decide where to use
            # slack rather than simply following an imposed appointment chain.
            if family == 'windows_shifts' and position % 4 == 0:
                continue
            before = slack if family != 'combined_tight' else rng.choice((20, 25, 35))
            after = slack if family != 'combined_tight' else rng.choice((25, 35, 45))
            opening = max(480, math.floor(visit['service_start'] - before))
            closing = min(end, math.ceil(visit['service_end'] + after))
            period = 'mattina' if visit['service_start'] < 720 else 'pomeriggio'
            row[f'scarico_{period}_da'] = _hhmm(opening)
            row[f'scarico_{period}_a'] = _hhmm(closing)
            if family == 'combined_tight' and position % 6 == 2 and period == 'mattina':
                second_opening = max(13 * 60, closing + 45)
                second_closing = min(end, second_opening + 65)
                if second_closing > second_opening:
                    row['scarico_pomeriggio_da'] = _hhmm(second_opening)
                    row['scarico_pomeriggio_a'] = _hhmm(second_closing)
    case['window_generation'] = 'independent witness with varied service-completion slack'


def _validate_witness(case):
    metrics = plan_metrics(case, case['witness'])
    if not metrics['feasible'] or metrics['served'] != case['expected_served']:
        raise AssertionError(f"Independent witness is invalid for {case['id']}")
    for resource, order in zip(case['resources'], case['witness']):
        if any(case['stops'][index]['sponda'] and not resource['ha_sponda'] for index in order):
            raise AssertionError('A required tail lift must be present on the witness vehicle')
    if metrics['mismatches']:
        raise AssertionError('Constructed witnesses must avoid equipment preferences too')


def _diagnostic_cases():
    overweight = _base(3, 'geography_capacity', 2026119091, 'development')
    overweight.update(id='upgrade-development-impossible-weight', family='impossible_weight',
        expected_served=49, expected_unassigned=[0], expected_upper_bound=49,
        coverage_proof='Stop 0 exceeds every selected vehicle weight capacity even on its own.')
    overweight['stops'][0]['peso_kg'] = max(r['capacita_kg'] for r in overweight['resources']) + 1
    overweight['witness'] = [[i for i in order if i != 0] for order in overweight['witness']]
    _validate_witness(overweight)

    no_lift = _base(4, 'geography_capacity', 2026119092, 'development')
    no_lift.update(id='upgrade-development-impossible-tail-lift', family='impossible_tail_lift',
        expected_served=49, expected_unassigned=[0], expected_upper_bound=49,
        coverage_proof='Stop 0 requires a tail lift; none of the selected vehicles has one.')
    for resource in no_lift['resources']:
        resource['ha_sponda'] = False
    for row in no_lift['stops']:
        row['sponda'] = row['customer_id'] == 1
    no_lift['witness'] = [[i for i in order if i != 0] for order in no_lift['witness']]
    _validate_witness(no_lift)

    unavailable = _base(2, 'windows_shifts', 2026119093, 'development')
    late = deepcopy(unavailable['resources'][0])
    late.update(driver_schedule={'start': '09:00', 'end': '18:00', 'breaks': []},
                capacita_kg=1000, capacita_colli=1000, max_minutes=600,
                alimentazione='gasolio', consumo_primario_100km=9.1, consumo_kwh_100km=0)
    unavailable['resources'].append(late)
    unavailable['witness'].append([])
    unavailable.update(id='upgrade-development-later-driver-start', family='later_driver_start',
        requested_vehicles=3, unavailable_resources=[2], expected_used=2,
        coverage_proof='The third driver starts after the common departure; the first two can serve all fifty.')
    _validate_witness(unavailable)
    return [overweight, no_lift, unavailable]


def upgrade_cases(holdout=False):
    """Return fixed, disjoint development/held-out inputs without running search.

    Development: sixteen feature combinations plus three diagnostic problems.
    Holdout: twelve different seeds across the three operational families.
    Holdout labels are frozen to support a final check after search tuning.
    """
    split = 'holdout' if holdout else 'development'
    families = FAMILIES[1:] if holdout else FAMILIES
    seed_base = 2037100000 if holdout else 2027110000
    cases = [_base(count, family, seed_base + count * 101 + FAMILIES.index(family) * 1009, split)
             for count in COUNTS for family in families]
    if not holdout:
        cases.extend(_diagnostic_cases())
    return cases


def independent_energy_cost(case, routes):
    """Return per-route energy estimates without using application accounting.

    The scenarios intentionally contain only fully electric and diesel vehicles.
    Estimates include energy alone, not labour, depreciation, charging stops or
    tolls. Rounding follows one currency amount per selected route.
    """
    if len(routes) != len(case['resources']):
        raise ValueError('One route is required for every resource')
    result = []
    for index, (resource, order) in enumerate(zip(case['resources'], routes)):
        km = replay(case, index, order)['km']
        if resource['alimentazione'] == 'elettrico':
            raw = km * resource.get('consumo_kwh_100km', 0) / 100 * resource['energy_price_electric']
        elif resource['alimentazione'] == 'gasolio':
            raw = km * resource.get('consumo_primario_100km', 0) / 100 * resource['energy_price_primary']
        else:
            raise ValueError('Only diesel and fully electric vehicles are modelled by this audit')
        result.append(round(raw, 2))
    return result
