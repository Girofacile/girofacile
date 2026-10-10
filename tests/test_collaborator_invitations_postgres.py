"""Invitation locking checks on a disposable PostgreSQL schema, never SQLite concurrency."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from urllib.parse import parse_qs, urlsplit

from fastapi import HTTPException
from sqlalchemy import text, inspect
from sqlalchemy.orm import Session

from test_audit_postgres import pg


PASSWORD = "Silver&Falcon93Maple!"


def _seed(pg, monkeypatch):
    from app.database import Base
    from app.models import User, CompanyCollaborator
    from app.services.collaborator_invitations import issue_invitation
    Base.metadata.create_all(pg)
    mailbox = []

    def deliver(to_email, full_name, company_name, setup_url):
        mailbox.append(setup_url)
        return True

    monkeypatch.setattr("app.services.email.send_collaborator_invitation", deliver)
    with Session(pg) as db:
        owner = User(username="invitation-concurrency", password_hash="test-only",
                     company_name="Disposable Company", plan="business", plan_status="active")
        db.add(owner)
        db.flush()
        actor = CompanyCollaborator(
            user_id=owner.id, full_name="Noemi Sarti", email="noemi@example.test",
            password_hash="!", password_setup_required=True, permissions_json='["customers.read"]',
            is_active=True,
        )
        db.add(actor)
        db.flush()
        ack = issue_invitation(db, actor, owner)
        db.commit()
        assert ack["invitation_sent"] is True
        return owner.id, actor.id, _token(mailbox[-1]), mailbox


def _token(url):
    return parse_qs(urlsplit(url).fragment)["token"][0]


def test_concurrent_invitation_acceptance_can_change_password_exactly_once(pg, monkeypatch):
    from app.core.security import verify_password
    from app.models import CompanyCollaborator, CollaboratorInvitation
    from app.services.collaborator_invitations import confirm_invitation
    _, actor_id, token, _ = _seed(pg, monkeypatch)
    start = Barrier(2)

    def accept(_):
        with Session(pg) as db:
            start.wait(timeout=15)
            try:
                confirm_invitation(db, token, PASSWORD, PASSWORD)
                return 200
            except HTTPException as exc:
                db.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(accept, range(2)))
    assert sorted(statuses) == [200, 400], statuses
    with Session(pg) as db:
        actor = db.get(CompanyCollaborator, actor_id)
        assert actor.password_setup_required is False
        assert verify_password(PASSWORD, actor.password_hash)
        assert actor.session_version == 1
        invitations = db.query(CollaboratorInvitation).filter_by(collaborator_id=actor_id).all()
        assert len(invitations) == 1 and invitations[0].used_at is not None
        assert invitations[0].token_hash == hashlib.sha256(token.encode()).hexdigest()


def test_concurrent_resend_and_acceptance_have_a_single_serialized_outcome(pg, monkeypatch):
    from app.core.security import verify_password
    from app.models import User, CompanyCollaborator, CollaboratorInvitation
    from app.services.collaborator_invitations import confirm_invitation, issue_invitation
    owner_id, actor_id, original, mailbox = _seed(pg, monkeypatch)
    start = Barrier(2)

    def accept():
        with Session(pg) as db:
            start.wait(timeout=15)
            try:
                confirm_invitation(db, original, PASSWORD, PASSWORD)
                return "accept", 200
            except HTTPException as exc:
                db.rollback()
                return "accept", exc.status_code

    def resend():
        with Session(pg) as db:
            actor, owner = db.get(CompanyCollaborator, actor_id), db.get(User, owner_id)
            start.wait(timeout=15)
            try:
                issue_invitation(db, actor, owner)
                db.commit()
                return "resend", 200
            except HTTPException as exc:
                db.rollback()
                return "resend", exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        accepted, resent = pool.submit(accept), pool.submit(resend)
        statuses = dict([accepted.result(timeout=30), resent.result(timeout=30)])
    assert statuses in ({"accept": 200, "resend": 409}, {"accept": 400, "resend": 200}), statuses
    with Session(pg) as db:
        actor = db.get(CompanyCollaborator, actor_id)
        live = db.query(CollaboratorInvitation).filter_by(collaborator_id=actor_id, used_at=None).all()
        original_row = db.query(CollaboratorInvitation).filter_by(
            token_hash=hashlib.sha256(original.encode()).hexdigest()).one()
        assert original_row.used_at is not None
        if statuses["accept"] == 200:
            assert not actor.password_setup_required and verify_password(PASSWORD, actor.password_hash)
            assert live == [] and len(mailbox) == 1
        else:
            assert actor.password_setup_required is True and len(live) == 1
            assert len(mailbox) == 2 and _token(mailbox[-1]) != original
            confirm_invitation(db, _token(mailbox[-1]), PASSWORD, PASSWORD)
            assert actor.password_setup_required is False
            assert verify_password(PASSWORD, actor.password_hash)


def test_additive_invitation_migration_preserves_legacy_passwords_and_tenant_fk(pg):
    from app.migrations import run_migrations, require_current_schema, LATEST
    versions = ("20261004_01", "20261004_02", "20261004_03", "20261004_04",
                "20261006_01", "20261009_01")
    with pg.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)"))
        conn.execute(text("INSERT INTO users VALUES (1, 'existing-owner')"))
        conn.execute(text("CREATE TABLE customers (id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE route_plans (id INTEGER PRIMARY KEY)"))
        conn.execute(text("""
            CREATE TABLE company_collaborators (
              id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
              full_name VARCHAR(160) NOT NULL, email VARCHAR(200) UNIQUE NOT NULL,
              password_hash VARCHAR(300) NOT NULL, permissions_json TEXT NOT NULL DEFAULT '[]',
              session_version INTEGER NOT NULL DEFAULT 0, is_active BOOLEAN NOT NULL DEFAULT TRUE,
              created_at TIMESTAMP, last_login TIMESTAMP
            )
        """))
        conn.execute(text("""
            INSERT INTO company_collaborators (id,user_id,full_name,email,password_hash,permissions_json)
            VALUES (1,1,'Legacy Operator','legacy@example.test','legacy-password-hash','["customers.read"]')
        """))
        conn.execute(text("CREATE TABLE schema_migrations (version VARCHAR(40) PRIMARY KEY, applied_at TIMESTAMP NOT NULL)"))
        for version in versions:
            conn.execute(text("INSERT INTO schema_migrations VALUES (:v,CURRENT_TIMESTAMP)"), {"v": version})
    run_migrations(pg)
    run_migrations(pg)
    require_current_schema(pg)
    with pg.connect() as conn:
        row = conn.execute(text("""
            SELECT password_hash,password_setup_required,permissions_json
            FROM company_collaborators WHERE id=1
        """)).one()
        assert row.password_hash == "legacy-password-hash"
        assert row.password_setup_required is False
        assert row.permissions_json == '["customers.read"]'
        assert set(conn.execute(text("SELECT version FROM schema_migrations")).scalars()) == set(versions) | {"20261009_02", "20261010_01", LATEST}
        assert conn.execute(text("SELECT COUNT(*) FROM collaborator_invitations")).scalar() == 0
    fks = inspect(pg).get_foreign_keys("collaborator_invitations")
    assert any(fk["referred_table"] == "company_collaborators"
               and fk["constrained_columns"] == ["collaborator_id"] for fk in fks)
    indexes = inspect(pg).get_indexes("collaborator_invitations")
    assert any(index["unique"] and index["column_names"] == ["token_hash"] for index in indexes)


def test_older_smtp_success_cannot_overwrite_a_newer_failed_invitation(pg, monkeypatch):
    """Release a stalled delivery after a later retry; verify the captured token remains revoked."""
    from datetime import datetime, timedelta
    from threading import Event
    from app.models import User, CompanyCollaborator, CollaboratorInvitation
    from app.services.collaborator_invitations import issue_invitation, invitation_info
    owner_id, actor_id, original, _ = _seed(pg, monkeypatch)
    started, release = Event(), Event()
    sent_tokens = []

    def delayed_delivery(to_email, full_name, company_name, setup_url):
        sent_tokens.append(_token(setup_url))
        if len(sent_tokens) == 1:
            started.set()
            assert release.wait(timeout=15)
            return True
        return False

    monkeypatch.setattr("app.services.email.send_collaborator_invitation", delayed_delivery)

    def first_send():
        with Session(pg) as db:
            ack = issue_invitation(db, db.get(CompanyCollaborator, actor_id), db.get(User, owner_id))
            db.commit()
            return ack

    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(first_send)
        try:
            assert started.wait(timeout=15)
            with Session(pg) as db:
                live = db.query(CollaboratorInvitation).filter_by(
                    collaborator_id=actor_id, used_at=None).one()
                # The anti-double-click interval is deliberately passed to allow a real retry.
                live.created_at = datetime.utcnow() - timedelta(seconds=31)
                db.commit()
                second = issue_invitation(
                    db, db.get(CompanyCollaborator, actor_id), db.get(User, owner_id))
                db.commit()
                assert second["invitation_sent"] is False
        finally:
            release.set()
        first_ack = first.result(timeout=30)
    assert first_ack["invitation_sent"] is False
    assert len(sent_tokens) == 2 and sent_tokens[0] != sent_tokens[1]
    with Session(pg) as db:
        actor = db.get(CompanyCollaborator, actor_id)
        assert actor.password_setup_required is True and actor.password_hash == "!"
        assert db.query(CollaboratorInvitation).filter_by(collaborator_id=actor_id, used_at=None).count() == 0
        latest = db.query(CollaboratorInvitation).filter_by(collaborator_id=actor_id).order_by(
            CollaboratorInvitation.id.desc()).first()
        assert latest.token_hash == hashlib.sha256(sent_tokens[1].encode()).hexdigest()
        assert latest.sent_at is None and latest.used_at is not None
        for token in (original, *sent_tokens):
            try:
                invitation_info(db, token)
            except HTTPException as exc:
                assert exc.status_code == 400
            else:
                raise AssertionError("A superseded or failed delivery revived its bearer token")


def test_concurrent_owner_disable_and_acceptance_cannot_reactivate_the_account(pg, monkeypatch):
    """Exercise the same locked update function used by the owner API."""
    from app.core.security import verify_password
    from app.models import User, CompanyCollaborator, CollaboratorInvitation
    from app.routers.collaborators import CollaboratorIn, update
    from app.services.collaborator_invitations import confirm_invitation
    owner_id, actor_id, token, _ = _seed(pg, monkeypatch)
    start = Barrier(2)

    def accept():
        with Session(pg) as db:
            start.wait(timeout=15)
            try:
                confirm_invitation(db, token, PASSWORD, PASSWORD)
                return "accept", 200
            except HTTPException as exc:
                db.rollback()
                return "accept", exc.status_code

    def disable():
        with Session(pg) as db:
            owner = db.get(User, owner_id)
            data = CollaboratorIn(
                full_name="Noemi Sarti", email="noemi@example.test",
                permissions=["customers.read"], is_active=False,
            )
            start.wait(timeout=15)
            update(actor_id, data, owner, db)
            return "disable", 200

    with ThreadPoolExecutor(max_workers=2) as pool:
        accepted, disabled = pool.submit(accept), pool.submit(disable)
        statuses = dict([accepted.result(timeout=30), disabled.result(timeout=30)])
    assert statuses in ({"accept": 200, "disable": 200},
                        {"accept": 400, "disable": 200}), statuses
    with Session(pg) as db:
        actor = db.get(CompanyCollaborator, actor_id)
        assert actor.is_active is False
        assert db.query(CollaboratorInvitation).filter_by(collaborator_id=actor_id, used_at=None).count() == 0
        if statuses["accept"] == 200:
            assert actor.password_setup_required is False
            assert verify_password(PASSWORD, actor.password_hash)
        else:
            assert actor.password_setup_required is True and actor.password_hash == "!"


def test_stale_password_and_reset_requests_cannot_overwrite_a_new_email_invitation_password(pg, monkeypatch):
    import pytest
    from fastapi import Response
    from app.core.security import verify_password
    from app.models import User, CompanyCollaborator, PasswordResetToken
    from app.routers.auth import _create_reset_token, confirm_password_reset, get_password_reset_info
    from app.routers.collaborators import CollaboratorIn, update, password as change_password
    from app.services.collaborator_invitations import confirm_invitation
    owner_id, actor_id, token, mailbox = _seed(pg, monkeypatch)
    chosen_password = "Orbit!River47Cedar#"
    obsolete_replacement = "Quartz&Heron82Breeze!"
    with Session(pg) as db:
        confirm_invitation(db, token, PASSWORD, PASSWORD)
        actor = db.get(CompanyCollaborator, actor_id)
        reset = _create_reset_token(db, "collaborator", actor.id, actor.email)
        db.commit()
        old_reset_token = reset.token
    with Session(pg, expire_on_commit=False) as stale_password_db, Session(pg, expire_on_commit=False) as stale_reset_db:
        stale_actor = stale_password_db.get(CompanyCollaborator, actor_id)
        stale_reset = stale_reset_db.query(PasswordResetToken).filter_by(token=old_reset_token).one()
        assert verify_password(PASSWORD, stale_actor.password_hash)
        assert stale_reset.used_at is None
        with Session(pg) as db:
            owner = db.get(User, owner_id)
            data = CollaboratorIn(
                full_name="Noemi Sarti", email="new-noemi@example.test",
                permissions=["customers.read"], is_active=True,
            )
            result = update(actor_id, data, owner, db)
            assert result["invitation_sent"] is True
            confirm_invitation(db, _token(mailbox[-1]), chosen_password, chosen_password)
        # Both old identity maps retain the values loaded before the email change.
        assert verify_password(PASSWORD, stale_actor.password_hash)
        assert stale_reset.used_at is None
        with pytest.raises(HTTPException) as denied_password:
            change_password({
                "current_password": PASSWORD,
                "new_password": obsolete_replacement,
                "confirm_password": obsolete_replacement,
            }, Response(), stale_actor, stale_password_db)
        assert denied_password.value.status_code == 401
        stale_password_db.rollback()
        with pytest.raises(HTTPException) as denied_reset:
            confirm_password_reset({
                "token": old_reset_token, "password": obsolete_replacement,
            }, stale_reset_db)
        assert denied_reset.value.status_code == 400
        stale_reset_db.rollback()
    with Session(pg) as db:
        actor = db.get(CompanyCollaborator, actor_id)
        assert actor.email == "new-noemi@example.test"
        assert actor.password_setup_required is False and actor.is_active is True
        assert verify_password(chosen_password, actor.password_hash)
        assert not verify_password(PASSWORD, actor.password_hash)
        assert not verify_password(obsolete_replacement, actor.password_hash)
        assert db.query(PasswordResetToken).filter_by(token=old_reset_token).one().used_at is not None
        # A recovery request started earlier may persist its old-email token
        # after revocation. An unused token still cannot target a new address.
        late_reset = _create_reset_token(db, "collaborator", actor.id, "noemi@example.test")
        db.commit()
        assert late_reset.used_at is None
        with pytest.raises(HTTPException) as denied_metadata:
            get_password_reset_info(late_reset.token, db)
        assert denied_metadata.value.status_code == 404
        with pytest.raises(HTTPException) as denied_late:
            confirm_password_reset({
                "token": late_reset.token, "password": obsolete_replacement,
            }, db)
        assert denied_late.value.status_code == 400
        db.rollback()
        db.refresh(actor)
        assert verify_password(chosen_password, actor.password_hash)
        # Recovery for the verified current email continues to work.
        current_reset = _create_reset_token(db, "collaborator", actor.id, actor.email)
        db.commit()
        assert get_password_reset_info(current_reset.token, db)["email"] == actor.email
        assert confirm_password_reset({
            "token": current_reset.token, "password": obsolete_replacement,
        }, db)["ok"] is True
        db.refresh(actor)
        assert verify_password(obsolete_replacement, actor.password_hash)
