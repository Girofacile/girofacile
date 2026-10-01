from copy import deepcopy
from itertools import permutations
import json
import hashlib
import pytest
from road_margin_benchmark import (FIXTURE, production_input, replay, scenario,
                                   certificate, routing_reference, run_one, opt)


def tiny(back=True, windows=False):
    return dict(n=3,return_depot=back,
        distance_m=[[0,10,40,25],[80,0,10,30],[35,60,0,10],[10,20,60,0]],
        duration_s=[[0,60,120,180],[180,0,60,120],[120,180,0,60],[60,120,180,0]],
        service_s=[0,60,120,60],windows_s=[None,[0,180] if windows else None,None,None],
        operator_order=[1,2,3])


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('windows',[False,True])
def test_independent_replay_matches_canonical_windows_and_directed_matrix(back,windows):
    data=tiny(back,windows)
    rows,matrix=production_input(data)
    for order in permutations(range(1,4)):
        actual=replay(data,list(order))
        canonical=opt._evaluate_fixed_sequence([rows[i] for i in order],matrix,[],return_depot=back)
        assert actual['distance_m']/1000 == pytest.approx(canonical['_objective'][0])
        assert actual['duration_s']/60 == pytest.approx(canonical['total_min'])
        assert actual['violations'] == canonical['violations']
        assert actual['lateness_s']/60 == pytest.approx(canonical['total_lateness_min'])


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('windows',[False,True])
def test_solver_certificate_matches_exhaustive_independent_oracle(back,windows):
    pytest.importorskip('ortools')
    data=tiny(back,windows)
    oracle=min((replay(data,list(p)) for p in permutations(range(1,4))),
               key=lambda r:(r['violations'],r['distance_m'],r['duration_s'],r['wait_s']))
    proof=certificate(data,[1,2,3],5)
    assert proof['distance_optimal']
    assert proof['distance_m'] == oracle['distance_m']
    assert proof['lower_bound_m'] == pytest.approx(oracle['distance_m'])
    for seed in ([1,2,3],oracle['order']):
        found=routing_reference(data,seed,.1)
        assert found['violations'] == 0
        assert found['distance_m'] == oracle['distance_m']


def test_saved_geographic_scenarios_are_complete_repeatable_and_feasible():
    snapshot=json.loads(FIXTURE.read_text(encoding='utf-8'))
    assert snapshot['source'] == 'fictional_deliveries_on_real_osm_roads'
    for pool in snapshot['pools'].values():
        assert len(pool['coordinates']) == 51
        assert max(pool['snap_distance_m']) <= 200
        for field in ('distance_m','duration_s'):
            assert len(pool[field]) == 51
            assert all(len(row)==51 and all(isinstance(x,int) and x>=0 for x in row) for row in pool[field])
            assert all(pool[field][i][i]==0 for i in range(51))
        for n in (8,15,20,30,50):
            for windows in (False,True):
                data=scenario(pool,n,windows,True)
                assert data == scenario(deepcopy(pool),n,windows,True)
                assert replay(data,data['operator_order'])['violations'] == 0
                rows,matrix=production_input(data)
                canonical=opt._evaluate_fixed_sequence([rows[i] for i in data['operator_order']],matrix,[])
                assert canonical['violations'] == 0


def test_open_route_includes_last_service_but_no_depot_leg():
    data=tiny(False)
    result=replay(data,[1,2,3])
    assert result['duration_s'] == 420
    assert result['distance_m'] == 30
    with pytest.raises(ValueError): replay(data,[1,1,2])


def test_full_comparison_stays_offline_and_preserves_input(monkeypatch):
    pytest.importorskip('ortools')
    pool=json.loads(FIXTURE.read_text(encoding='utf-8'))['pools']['urban']
    original=deepcopy(pool)
    def blocked(*a,**k): pytest.fail('Unexpected network request')
    monkeypatch.setattr(opt.requests.sessions.Session,'request',blocked)
    record=run_one(pool,'urban',3,True,False,.1,5)
    assert pool == original
    assert record['margin_is_exact']
    assert record['best_known']['violations'] == 0
    assert record['found_margin_km'] >= 0


def test_report_rejects_incomplete_checkpoint():
    from summarize_road_margin import summary
    with pytest.raises(ValueError,match='60'): summary([])


def test_saved_report_orders_metrics_and_certificates_match_frozen_matrices():
    from road_margin_benchmark import OUTPUT
    from summarize_road_margin import summary
    snapshot=json.loads(FIXTURE.read_text(encoding='utf-8'))
    report=json.loads(OUTPUT.read_text(encoding='utf-8'))
    assert report['matrix_sha256'] == hashlib.sha256(FIXTURE.read_text(encoding='utf-8').encode('utf-8')).hexdigest()
    assert summary(report['records'])
    for r in report['records']:
        data=scenario(snapshot['pools'][r['family']],r['n'],r['windows'],r['return_depot'])
        for field in ('operator','girofacile','reference_independent','reference_warm','best_known'):
            assert r[field] == replay(data,r[field]['order'])
            assert r[field]['violations'] == 0
        assert r['found_margin_km'] == (r['girofacile']['distance_m']-r['best_known']['distance_m'])/1000
        if r['margin_is_exact']:
            assert r['certificate']['status'] == 'OPTIMAL'
            assert r['certificate']['distance_m'] == r['best_known']['distance_m']
            assert r['certificate']['lower_bound_m'] == pytest.approx(r['best_known']['distance_m'])
