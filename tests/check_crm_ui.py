"""CRM browser flow against a disposable API/database, without external services."""
import os
os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('ALLOW_SQLITE_LEGACY', 'true')
os.environ.setdefault('APP_ENV', 'test')
import sys
import threading
import socket
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from playwright.sync_api import sync_playwright, expect
import uvicorn
from app.database import Base, get_db
from app.models import SuperAdminCollaborator
from app.routers.admin_crm import router
from app.core.dependencies import require_superadmin

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'test-results' / 'crm'


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.TemporaryDirectory(prefix='gf-crm-ui-')
    engine = create_engine('sqlite:///'+str(Path(temporary.name)/'crm.db'), connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    actor = {'role':'superadmin','username':'owner','display_name':'Proprietario','permissions':{'all':True}}
    app=FastAPI(); app.include_router(router)
    app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
    @app.get('/admin')
    def admin(): return FileResponse(ROOT/'static/admin/index.html')
    @app.get('/api/admin/me')
    def me(): return dict(actor,authenticated=True)
    def db():
        with Session(engine) as session: yield session
    app.dependency_overrides[get_db]=db
    app.dependency_overrides[require_superadmin]=lambda:actor
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error'))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    import time
    for _ in range(100):
        if server.started: break
        time.sleep(.05)
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page(viewport={'width':1440,'height':1000})
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('response',lambda response: errors.append(str(response.status)+' '+response.url) if '/api/admin/crm' in response.url and response.status>=400 else None)
            def route(request):
                url=request.request.url
                if url.startswith(f'http://127.0.0.1:{port}'):
                    if '/api/' in url and '/api/admin/crm' not in url and '/api/admin/me' not in url:
                        request.fulfill(status=200,content_type='application/javascript' if url.endswith('.js') else 'application/json',body='' if url.endswith('.js') else '{}')
                    else:request.continue_()
                else:request.abort()
            page.route('**/*',route)
            page.goto(f'http://127.0.0.1:{port}/admin#crm')
            root=page.locator('#section-crm')
            expect(root.get_by_role('button',name='Gestisci aziende')).to_be_visible()
            root.get_by_role('button',name='Gestisci aziende').click()
            root.get_by_role('button',name='Nuova azienda',exact=True).click()
            page.locator('#crm-dialog').get_by_label('Ragione sociale',exact=False).fill('Azienda <CRM>')
            page.locator('#crm-dialog').get_by_label('Email aziendale').fill('sales@example.test')
            page.locator('#crm-dialog').get_by_label('Telefono',exact=True).fill('+39 021234567')
            page.locator('#crm-save').click()
            expect(page.locator('#crm-dialog')).not_to_be_visible()
            expect(root.get_by_text('Azienda <CRM>',exact=True)).to_be_visible()
            root.get_by_role('button',name='Apri',exact=True).click()
            root.get_by_role('button',name='Contatti',exact=True).last.click()
            root.get_by_role('button',name='Nuovo contatto').click()
            page.locator('#crm-dialog').get_by_label('Nome referente',exact=False).fill('Mario Rossi')
            page.locator('#crm-dialog').get_by_label('Email',exact=True).fill('mario@example.test')
            page.locator('#crm-save').click()
            expect(root.get_by_text('Mario Rossi',exact=True)).to_be_visible()
            root.get_by_role('button',name='Pipeline',exact=True).click()
            root.get_by_role('button',name='Nuova trattativa').click()
            page.locator('#crm-dialog').get_by_label('Trattativa',exact=False).fill('Abbonamento annuale')
            page.locator('#crm-dialog').get_by_label('Valore EUR').fill('1200')
            page.locator('#crm-dialog').get_by_label('Fase',exact=True).select_option('won')
            page.locator('#crm-save').click()
            expect(page.locator('#crm-content').get_by_text('Vinta',exact=True)).to_be_visible()
            root.get_by_role('button',name='Follow-up',exact=True).click()
            root.get_by_role('button',name='Nuovo follow-up').click()
            page.locator('#crm-dialog').get_by_label('Attività da svolgere',exact=False).fill('Inviare proposta')
            page.locator('#crm-save').click()
            expect(root.get_by_text('Inviare proposta',exact=True)).to_be_visible()
            root.get_by_role('button',name='Modifica',exact=True).click()
            page.locator('#crm-dialog').get_by_label('Stato',exact=True).select_option('completed')
            page.locator('#crm-save').click()
            expect(page.locator('#crm-content').get_by_text('Completato',exact=True)).to_be_visible()
            root.get_by_role('button',name='Report',exact=True).click()
            expect(root.get_by_text('Conversione: 100%',exact=True)).to_be_visible()
            page.reload();expect(root.get_by_role('button',name='Gestisci aziende')).to_be_visible()
            page.screenshot(path=str(OUTPUT/'desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            root.get_by_role('button',name='Aziende',exact=True).click()
            expect(root.get_by_text('Azienda <CRM>',exact=True)).to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
            root.get_by_role('button',name='Modifica',exact=True).click()
            expect(page.locator('#crm-save')).to_be_visible()
            assert page.locator('#crm-save').evaluate('(e)=>{const r=e.getBoundingClientRect(); return r.top>=0 && r.bottom<=innerHeight;}'), page.locator('#crm-dialog').evaluate('(e)=>({rect:e.getBoundingClientRect().toJSON(),height:innerHeight,scale:getComputedStyle(document.documentElement).getPropertyValue("--gf-ui-scale")})')
            page.screenshot(path=str(OUTPUT/'mobile-form.png'),full_page=True)
            page.locator('#crm-close').click()
            # A CRM-only collaborator enters directly without overview or error polling.
            with Session(engine) as session:
                user=SuperAdminCollaborator(full_name='Commerciale',email='commerciale@example.test',password_hash='test',permissions_json='{"crm_access":true}')
                session.add(user);session.commit();uid=user.id
            actor.clear();actor.update(role='collaborator',username='commerciale@example.test',collaborator_id=uid,permissions={'crm_access':True})
            requests=[];page.on('request',lambda request:requests.append(request.url))
            page.goto(f'http://127.0.0.1:{port}/admin')
            expect(root.get_by_role('button',name='Gestisci aziende')).to_be_visible()
            assert not any('/api/admin/overview' in url or '/api/admin/errors' in url for url in requests)
            root.get_by_role('button',name='Aziende',exact=True).click()
            expect(root.get_by_role('button',name='Nuova azienda',exact=True)).to_have_count(0)
            page.screenshot(path=str(OUTPUT/'mobile-readonly.png'),full_page=True)
            assert not errors, errors
            browser.close()
    finally:
        server.should_exit=True;thread.join(timeout=5);engine.dispose();temporary.cleanup()
    print('CRM: creazione, contatti, trattativa vinta, follow-up, persistenza, report, mobile e accesso limitato verificati.')


if __name__=='__main__':main()
