"""Token Mapbox rifiutato o quota esaurita: avviso al Super Admin, una volta, senza mai mostrare il token."""
import pytest
import requests

from app.services import traffic_provider as tp


class _Response:
    def __init__(self, status):
        self.status_code = status

    def raise_for_status(self):
        raise requests.HTTPError(f"{self.status_code} for url ...access_token=pk.SEGRETO", response=self)


@pytest.mark.parametrize("status,kind", [(401, "MapboxTokenRejected"), (403, "MapboxTokenRejected"),
                                         (429, "MapboxQuotaExceeded"), (500, None)])
def test_rejected_token_or_quota_is_reported_without_the_token(monkeypatch, status, kind):
    reports = []
    from app.services import error_monitor
    monkeypatch.setattr(error_monitor, "report_service_problem", lambda **kw: reports.append(kw))
    monkeypatch.setattr(tp, "mapbox_access_token", lambda db: "pk.SEGRETO")
    monkeypatch.setattr(tp, "routing_number", lambda db, key, default, *a: default)
    monkeypatch.setattr(tp.requests, "get", lambda *a, **kw: _Response(status))
    points = [{"lat": 40.74, "lon": 14.43}, {"lat": 40.69, "lon": 14.6}]
    with pytest.raises(tp.TrafficUnavailable):
        tp.MapboxTrafficProvider().calculate(points, "2026-11-26T06:35:00Z")
    if kind is None:
        assert reports == []
    else:
        assert [r["error_type"] for r in reports] == [kind]
        assert "SEGRETO" not in repr(reports) and reports[0]["path"] == "mapbox-traffic"


def test_same_problem_is_recorded_once_a_day(monkeypatch, tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database import Base
    from app.models import SystemErrorLog
    from app.services import error_monitor
    engine = create_engine(f"sqlite:///{tmp_path/'e.db'}")
    Base.metadata.create_all(engine, tables=[SystemErrorLog.__table__])
    monkeypatch.setattr(error_monitor, "SessionLocal", sessionmaker(bind=engine))
    sent = []
    monkeypatch.setattr(error_monitor, "ERROR_NOTIFICATIONS_ENABLED", True)
    monkeypatch.setattr(error_monitor, "ERROR_NOTIFICATIONS_EMAIL", "admin@example.test")
    monkeypatch.setattr(error_monitor, "send_system_error_alert", lambda to, payload: sent.append(payload) or True)
    args = dict(path="mapbox-traffic", action="Traffico Mapbox", error_type="MapboxTokenRejected", message="Token rifiutato")
    assert error_monitor.report_service_problem(**args) is not None
    assert error_monitor.report_service_problem(**args) is None
    assert len(sent) == 1 and sent[0]["severity"] == "critical"
    with sessionmaker(bind=engine)() as db:
        assert db.query(SystemErrorLog).count() == 1
