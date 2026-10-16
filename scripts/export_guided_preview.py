"""Package the guided-layout prototype into one independently openable HTML file."""
from pathlib import Path
import base64
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'anteprime' / 'guidata'
OUTPUT = ROOT / 'anteprime' / 'html-autonomi' / 'pianificazione-guidata.html'


def export():
    html = (SOURCE / 'index.html').read_text(encoding='utf-8')
    references = re.findall(r'(?:href|src)="([^"]+\.(?:css|js))"', html)
    for reference in references:
        path = (SOURCE / reference).resolve()
        content = path.read_text(encoding='utf-8')
        if path.name == 'theme.css':
            content = re.sub(r"@import url\('https://fonts\.googleapis\.com/[^']*'\);", '', content)
        mime = 'text/css' if path.suffix == '.css' else 'text/javascript'
        embedded = base64.b64encode(content.encode('utf-8')).decode('ascii')
        html = html.replace(f'"{reference}"', f'"data:{mime};charset=utf-8;base64,{embedded}"')
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html, encoding='utf-8')
    print(OUTPUT)
    return OUTPUT


if __name__ == '__main__':
    export()
