"""File Excel di esempio per le importazioni (ordini e clienti)."""
import io

from fastapi.responses import Response
from openpyxl import Workbook
from openpyxl.styles import Font


def workbook(kind, headers, rows):
    book = Workbook()
    sheet = book.active
    sheet.title = kind.capitalize()
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append(row)
    for column in sheet.columns:
        sheet.column_dimensions[column[0].column_letter].width = max(12, min(40, max(len(str(c.value or '')) for c in column) + 2))
    buffer = io.BytesIO()
    book.save(buffer)
    return Response(buffer.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="girofacile_esempio_{kind}.xlsx"', "Cache-Control": "no-store"})
