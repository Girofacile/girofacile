"""Dati fiscali: formato plausibile o vuoto (collaudo 10/11: P.IVA «123», PEC «non-una-pec», SDI «XYZ» accettati)."""
import pytest
from fastapi import HTTPException
from app.services import fiscal
from test_agents_feature import env  # noqa: F401


@pytest.mark.parametrize('value,ok', [('', True), ('01234567897', True), ('IT 012 345 678 97', True), ('DE123456789', True),
                                      ('123', False), ('01234567890', False), ('ABC', False)])
def test_vat(value, ok):
    assert (fiscal.vat_error(value) is None) == ok


@pytest.mark.parametrize('field,value,ok', [('company_pec', 'azienda@pec.it', True), ('company_pec', 'non-una-pec', False),
                                            ('company_sdi', 'M5UXCR1', True), ('company_sdi', '1', False),
                                            ('company_fiscal_code', 'RSSMRA80A01F839W', True), ('company_fiscal_code', '01234567897', True),
                                            ('company_fiscal_code', 'XYZ', False)])
def test_other_fields(field, value, ok):
    if ok:
        fiscal.validate_fiscal({field: value})
    else:
        with pytest.raises(HTTPException) as exc:
            fiscal.validate_fiscal({field: value})
        assert exc.value.status_code == 422


def test_company_profile_and_billing_details_refuse_invalid_values(env):
    from app.routers import billing
    client, db, owner, *_ = env
    client.app.include_router(billing.router)
    from app.routers import auth
    client.app.include_router(auth.router)
    assert client.put('/api/company-profile', json={'company_vat': '123'}).status_code == 422
    assert client.put('/api/billing/billing-details', json={'company_pec': 'non-una-pec'}).status_code == 422
    assert client.put('/api/billing/billing-details', json={'company_vat': '01234567897', 'company_sdi': 'M5UXCR1'}).status_code == 200
    db.refresh(owner)
    assert owner.company_vat == '01234567897'
