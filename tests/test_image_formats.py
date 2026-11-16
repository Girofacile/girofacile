"""Immagini caricate: Pillow apre solo il formato dichiarato (nessun altro decodificatore)."""
import base64
import io

import pytest
from fastapi import HTTPException
from PIL import Image

from app.services.delivery_pod import normalize_image


def _data_url(fmt, header):
    out = io.BytesIO()
    Image.new('RGB', (20, 20), 'red').save(out, format=fmt)
    return header + ',' + base64.b64encode(out.getvalue()).decode()


def test_declared_png_is_accepted():
    assert normalize_image(_data_url('PNG', 'data:image/png;base64'), 'photo')


@pytest.mark.parametrize('fmt', ['GIF', 'TIFF', 'BMP'])
def test_other_formats_disguised_as_png_are_rejected(fmt):
    with pytest.raises(HTTPException):
        normalize_image(_data_url(fmt, 'data:image/png;base64'), 'photo')
