"""Historical comparisons must never execute the current optimizer as baseline."""
from importlib import import_module
import sys

import pytest

import run_fleet_constraint_benchmark as constraint
import run_fleet_upgrade_benchmark as upgrade
from routing_quality_fleet import _case, _resource, _stop, run_fleet


@pytest.mark.parametrize('runner', [upgrade, constraint])
def test_baseline_uses_its_own_calendar_and_restores_current_modules(runner, monkeypatch):
    sources = runner.frozen_sources()
    paths = [*upgrade.SHARED_ENGINE_FILES,
             *(f'app/services/{name}.py' for name in runner.MODULES)]
    originals = {path: import_module(path.removesuffix('.py').replace('/', '.'))
                 for path in paths}
    current_optimizer = originals['app/optimizer.py']

    def current_calendar_must_not_run(*args, **kwargs):
        raise AssertionError('current calendar leaked into frozen baseline')

    monkeypatch.setattr(current_optimizer, '_evaluate_fixed_sequence', current_calendar_must_not_run)
    case = _case('baseline-isolation', 'baseline-isolation', [_stop(0), _stop(1)],
                 [_resource(), _resource()])
    with pytest.raises(RuntimeError, match='restore on failure'):
        with runner.implementation(sources):
            for path, original in originals.items():
                full_name = path.removesuffix('.py').replace('/', '.')
                historical = import_module(full_name)
                assert historical is not original
                assert historical.__file__ == f'git:{runner.BASELINE_COMMIT}:{path}'
                package, name = full_name.rsplit('.', 1)
                assert getattr(import_module(package), name) is historical
            legacy_optimizer = import_module('app.optimizer')
            assert legacy_optimizer is not current_optimizer
            assert not hasattr(legacy_optimizer, 'KM_PER_HOUR')
            assert import_module('app.services.fleet_planning').opt is legacy_optimizer
            answer = run_fleet(case, 'efficient', budget=100)
            assert sum(map(len, answer['routes'])) == 2
            assert answer['external_calls'] == 0
            raise RuntimeError('restore on failure')

    for path, original in originals.items():
        full_name = path.removesuffix('.py').replace('/', '.')
        package, name = full_name.rsplit('.', 1)
        assert sys.modules[full_name] is original
        assert getattr(import_module(package), name) is original


@pytest.mark.parametrize('runner', [upgrade, constraint])
def test_changed_historical_calendar_is_rejected_before_execution(runner, monkeypatch):
    original = runner.subprocess.check_output

    def changed_source(command, **kwargs):
        source = original(command, **kwargs)
        return source + b'\n# changed frozen source\n' if command[-1].endswith(':app/optimizer.py') else source

    monkeypatch.setattr(runner.subprocess, 'check_output', changed_source)
    with pytest.raises(ValueError, match='Unexpected frozen baseline: app/optimizer.py'):
        runner.frozen_sources()
