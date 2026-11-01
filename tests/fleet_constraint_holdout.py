"""Previously unused heterogeneous inputs for the constraint-solver check.

This module generates input data and independent feasible witnesses only. It
never calls the production optimizer or changes a seed based on its answers.
The twelve seeds differ from both groups used by the adaptive-search campaign.
"""
from fleet_upgrade_cases import _base


def constraint_holdout_cases():
    cases = []
    families = ('windows_shifts', 'scarce_tail_lift', 'combined_tight')
    for count in (2, 3, 4, 5):
        for index, family in enumerate(families):
            seed = 2045110000 + count * 103 + index * 1013
            case = _base(count, family, seed, 'holdout')
            case.update(id=f'constraint-holdout-{count}-{family}-{seed}',
                        split='constraint_holdout',
                        generated_for='fleet-constraint-solver',
                        witness_origin='independent constructive membership and calendar; no production answer')
            cases.append(case)
    return cases
