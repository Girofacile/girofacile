"""Logo aziendale: solo immagini PNG, JPEG o WebP incorporate, come le usano gestionale e PDF di consegna."""
import base64
import io

import pytest
from PIL import Image

from test_agents_feature import env


def data_url(fmt='PNG', mime=None, size=(64, 32)):
    out = io.BytesIO()
    Image.new('RGBA' if fmt == 'PNG' else 'RGB', size, (20, 90, 200)).save(out, format=fmt)
    return f'data:image/{mime or fmt.lower()};base64,' + base64.b64encode(out.getvalue()).decode()


@pytest.fixture
def profile(env):
    from app.core.dependencies import current_user
    from app.routers import auth
    client, db, owner, *_ = env
    client.app.include_router(auth.router)
    client.app.dependency_overrides[current_user] = lambda: owner
    return client, db, owner


@pytest.mark.parametrize('fmt', ['PNG', 'JPEG', 'WEBP'])
def test_supported_logo_formats_are_saved(profile, fmt):
    client, db, owner = profile
    response = client.put('/api/company-profile', json={'company_logo_url': data_url(fmt)})
    assert response.status_code == 200, response.text
    db.refresh(owner)
    assert owner.company_logo_url.startswith(f'data:image/{fmt.lower()};base64,')


@pytest.mark.parametrize('value', [
    'data:image/svg+xml;base64,' + base64.b64encode(b'<svg xmlns="http://www.w3.org/2000/svg"/>').decode(),
    'data:image/heic;base64,AAAAGGZ0eXBoZWlj',
    'data:image/png;base64,non-valido',
    'https://example.com/logo.png',
    'javascript:alert(1)',
    data_url('GIF', size=(10, 10)),
    data_url('PNG', mime='png', size=(1, 1)).replace('base64,', 'base64,' + 'A' * 2_100_000, 1),
], ids=['svg', 'heic', 'base64-non-valido', 'url-esterno', 'javascript', 'gif', 'troppo-grande'])
def test_unsupported_or_oversized_logos_are_refused(profile, value):
    client, db, owner = profile
    owner.company_logo_url = None
    db.commit()
    response = client.put('/api/company-profile', json={'company_logo_url': value})
    assert response.status_code == 400
    assert 'Logo non valido' in response.json()['detail']
    db.refresh(owner)
    assert owner.company_logo_url is None


def test_logo_removal_and_unchanged_logo_never_block_profile_save(profile):
    client, db, owner = profile
    owner.company_logo_url = 'https://example.com/vecchio-logo.png'  # salvato prima del controllo
    db.commit()
    response = client.put('/api/company-profile', json={'company_name': 'Nuovo nome', 'company_logo_url': owner.company_logo_url})
    assert response.status_code == 200, response.text
    assert client.put('/api/company-profile', json={'company_logo_url': ''}).status_code == 200
    db.refresh(owner)
    assert owner.company_logo_url is None and owner.company_name == 'Nuovo nome'
