"""File ordini esportati da un gestionale AS400: date, colonne abbreviate, codifica Windows."""
import pytest

from app.services import order_files as of

BASE = {'N': '0000451', 'R': 'Alimentari Oplonti', 'A': 'Via Roma 1, 80031 Brusciano NA'}
MAPPING = {'number': 'N', 'external_id': 'N', 'recipient_name': 'R', 'delivery_address': 'A', 'requested_date': 'D'}


@pytest.mark.parametrize('raw', ['13/11/2026', '13/11/26', '13-11-2026', '13.11.2026', '2026-11-13',
                                 '20261113', '13112026', 20261113, '2026-11-13T08:00:00'])
def test_requested_date_accepts_common_and_as400_formats(raw):
    assert of.mapped({**BASE, 'D': raw}, MAPPING)['requested_date'] == '2026-11-13'


@pytest.mark.parametrize('raw', ['131126', '32/11/2026', '2026-13-01', 'domani'])
def test_ambiguous_or_invalid_dates_are_rejected(raw):
    with pytest.raises(ValueError, match='non valida'):
        of.mapped({**BASE, 'D': raw}, MAPPING)


def test_as400_export_is_read_and_mapped_automatically():
    text = ('NUMORD;RAGSOC;INDIRIZZO;CAP;LOCALITA;PROV;DTCONS;NRCOLLI;PESO\r\n'
            '0000452   ;CAFFÈ DELLA PIAZZA      ;P.ZZA MUNICIPIO 4   ;80045;POMPEI              ;NA;20261113;1;4,25\r\n')
    headers, rows = of.read_file(text.encode('cp1252'), 'ordini.csv')
    mapping = of.suggestions(headers)
    assert mapping['number'] == mapping['external_id'] == 'NUMORD'
    assert mapping['recipient_name'] == 'RAGSOC'
    assert mapping['requested_date'] == 'DTCONS' and mapping['packages'] == 'NRCOLLI'
    order = of.mapped(rows[0], {k: v for k, v in mapping.items() if k in of.FIELDS})
    assert order['number'] == '0000452' and order['recipient_name'] == 'CAFFÈ DELLA PIAZZA'
    assert order['requested_date'] == '2026-11-13' and order['weight_kg'] == 4.25
