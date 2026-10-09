"""Standalone Playwright check with mocked APIs; never contacts the live server."""
import sys, os
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0,str(Path.cwd()/'test-results/ui-tools'))
sys.path.insert(0,str(Path.cwd()))
from playwright.sync_api import sync_playwright
from app.services.company_permissions import CATALOG, DEPENDENCIES
root=Path.cwd()
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=os.environ.get('CHROME_EXECUTABLE',r'C:\Program Files\Google\Chrome\Application\chrome.exe'),headless=True)
    for width in (1440,390):
        page=browser.new_page(viewport={'width':width,'height':950})
        errors=[];requests=[];saved=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        def handle(route):
            path=urlparse(route.request.url).path
            if path.startswith('/api/'):
                requests.append(path)
                if path=='/api/me': data={'authenticated':False}
                elif path=='/api/collaborators/permissions':data={'permissions':CATALOG,'dependencies':{k:sorted(v) for k,v in DEPENDENCIES.items()}}
                elif path=='/api/collaborators':
                    if route.request.method=='POST':
                        entry=route.request.post_data_json
                        saved.append(dict(entry,id=1,last_login=None));data=saved[-1]
                    else:data=saved
                elif path=='/api/settings':data={}
                elif path=='/api/collaborator/context':data={}
                elif path=='/api/collaborator/account':data={'username':'Collaboratore Demo','email':'demo@example.test','role':'Collaboratore'}
                elif path=='/api/billing/catalog.js':
                    route.fulfill(body='',content_type='application/javascript');return
                elif path=='/api/sector-config':data={}
                else:data=[]
                route.fulfill(json=data);return
            file=root/('static/dashboard/index.html' if path=='/dashboard' else path.lstrip('/'))
            if file.is_file():route.fulfill(path=str(file))
            else:route.fulfill(status=404,body='')
        page.route('**/*',handle)
        page.goto('http://collaborators.test/dashboard')
        page.wait_for_timeout(800)
        page.evaluate("currentSessionUser={authenticated:true,role:'admin',username:'Titolare',company_name:'Demo',plan:'business',plan_status:'active',workspace_operational:true}; showGestionaleAfterLogin(); showTab('collaboratori');")
        page.wait_for_function("document.getElementById('collaboratorsBody').textContent.includes('Nessun collaboratore')")
        page.locator('#tab-collaboratori button.btn-primary').click()
        page.locator('#collaboratorName').fill('Collaboratore Demo')
        page.locator('#collaboratorEmail').fill('demo@example.test')
        page.locator('#collaboratorPassword').fill('Orbit!River47Cedar#')
        page.locator('#collaboratorPermissions input[value="routes.program"]').check()
        assert page.locator('#collaboratorPermissions input[value="customers.read"]').is_checked()
        assert page.locator('#collaboratorPermissions input[value="routes.plan"]').is_checked()
        assert not page.locator('#collaboratorPermissions input[value="customers.delete"]').is_checked()
        page.screenshot(path=str(root/f'test-results/collaborators-dialog-{width}.png'))
        page.locator('#collaboratorSave').click()
        page.wait_for_function("document.getElementById('collaboratorsTotal').textContent==='1'")
        assert saved[0]['permissions']
        page.locator('#collaboratorSearch').fill('does not exist')
        assert 'Nessun collaboratore' in page.locator('#collaboratorsBody').inner_text()
        page.locator('#collaboratorSearch').fill('Demo')
        page.screenshot(path=str(root/f'test-results/collaborators-list-{width}.png'))
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'page overflow'
        requests.clear()
        page.evaluate("currentSessionUser={authenticated:true,role:'admin',is_collaborator:true,username:'Collaboratore Demo',permissions:['customers.read','agents.read']}; GFCompanyAccess.initialize()")
        page.wait_for_timeout(800)
        assert page.locator('[data-tab="collaboratori"]').is_hidden()
        assert page.locator('[onclick="openCustomerModal()"]').is_hidden()
        assert '/api/account-profile' not in requests
        assert '/api/company-profile' not in requests
        page.evaluate('openProfilePanel()')
        page.wait_for_timeout(300)
        assert page.locator('.profile-plan-section').is_hidden()
        assert page.locator('#profileEmail').get_attribute('readonly') is not None
        print(width, 'owner creation, dependencies, search, responsive layout, restricted collaborator and own profile OK; errors:',errors)
        assert not errors,errors
        page.close()
    browser.close()
