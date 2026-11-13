"""Importazione clienti: intestazioni scritte «a mano» in un file Excel o CSV."""
import asyncio
import io

import openpyxl
import pytest
from fastapi import HTTPException

from app.services.customer_import import read_customer_import


class Upload:
    def __init__(self, data, name):
        self.data, self.filename = data, name

    async def read(self, limit):
        return self.data


def xlsx(headers, rows):
    book = openpyxl.Workbook()
    book.active.append(headers)
    for row in rows:
        book.active.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def read(data, name):
    return asyncio.run(read_customer_import(Upload(data, name)))


def test_natural_excel_headers_are_recognised():
    df = read(xlsx(['Ragione Sociale', 'Via', 'N. Civico', 'CAP', 'Città', 'Prov.', 'Tel', 'E-mail', 'Cod. Cliente', 'Tempo di scarico'],
                   [['Bar Roma', 'Via Roma', 1, 80031, 'Brusciano', 'NA', '0811234567', 'bar@esempio.it', 'C01', 15]]), 'clienti.xlsx')
    row = df.iloc[0]
    assert row['nome'] == 'Bar Roma' and row['via'] == 'Via Roma' and row['civico'] == '1'
    assert row['cap'] == '80031' and row['comune'] == 'Brusciano' and row['provincia'] == 'NA'
    assert row['telefono'] == '0811234567' and row['email'] == 'bar@esempio.it'
    assert row['codice_cliente'] == 'C01' and row['tempo_scarico_min'] == '15'


def test_csv_with_capitalised_headers():
    df = read('Nome;Indirizzo;Comune\nBar Roma;Via Roma 1;Napoli\n'.encode(), 'clienti.csv')
    assert list(df.columns) == ['nome', 'indirizzo', 'comune']


def test_missing_essential_columns_gives_a_clear_message():
    with pytest.raises(HTTPException) as error:
        read(xlsx(['Telefono', 'Email'], [['081', 'a@b.it']]), 'clienti.xlsx')
    assert 'Nome' in error.value.detail and 'Colonne trovate: Telefono, Email' in error.value.detail


def test_old_xls_format_explains_how_to_convert():
    with pytest.raises(HTTPException) as error:
        read(b'old', 'clienti.xls')
    assert '.xlsx' in error.value.detail
