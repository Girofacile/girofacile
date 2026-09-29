from copy import deepcopy
import json
import pytest
from run_real_optimizer_benchmark import load_scenario, evaluate_scenario, run_dataset, summarize


def sample():
    return dict(schema_version=1,source='synthetic_test',scenario_id='synthetic-only',split='development',
        depot={'id':'D'},start_time='00:00',return_depot=True,
        stops=[{'id':'A','service_min':0},{'id':'B','service_min':0}],operator_order=['B','A'],
        matrix_km=[[0,1,10],[10,0,1],[1,10,0]],matrix_min=[[0,1,10],[10,0,1],[1,10,0]],
        energy={'currency':'EUR','components':[{'consumption_per_100km':10,'price_per_unit':2}]})


def test_saved_fixture_offline_metrics_and_energy():
    data=sample(); original=deepcopy(data)
    result=evaluate_scenario(data,allow_synthetic=True)
    assert data == original
    assert result['operator']['total_km'] == 30
    assert result['girofacile']['total_km'] == 3
    assert result['delta_km'] == -27 and result['delta_km_pct'] == -90
    assert result['delta_min'] == -27
    assert result['energy_cost'] == {'currency':'EUR','operator':6,'girofacile':pytest.approx(.6)}
    assert result['outcome'] == 'improved'
    assert summarize([result])['delta_km']['mean'] == -27


@pytest.mark.parametrize('mutate',[
    lambda d:d.update(operator_order=['A','A']),
    lambda d:d.update(matrix_min=[[0]]),
    lambda d:d['matrix_km'][0].__setitem__(1,float('nan')),
    lambda d:d['stops'][0].update(scarico_mattina_da='09:00'),
    lambda d:d.update(start_time='25:00'),
])
def test_fixture_rejects_invalid_data(mutate):
    data=sample(); mutate(data)
    with pytest.raises(ValueError): load_scenario(data,allow_synthetic=True)


def test_synthetic_requires_opt_in():
    with pytest.raises(ValueError,match='source'): evaluate_scenario(sample())


def test_empty_and_separate_holdout(tmp_path):
    for split in ('development','validation'): (tmp_path/split).mkdir()
    report=run_dataset(tmp_path,'validation')
    assert report['summary']['count'] == 0
    assert report['summary']['delta_km']['mean'] is None
    (tmp_path/'development'/'example.json').write_text(json.dumps(sample()))
    assert run_dataset(tmp_path,'validation')['summary']['count'] == 0
    assert run_dataset(tmp_path,'development',True)['summary']['count'] == 1
    (tmp_path/'validation'/'wrong.json').write_text(json.dumps(sample()))
    with pytest.raises(ValueError,match='split'): run_dataset(tmp_path,'validation',True)
