"""Playwright renderer: beat frames for review, or full 60fps with 3 subframes per frame + audio."""
import sys, os, base64, pathlib, subprocess
from playwright.sync_api import sync_playwright

D = pathlib.Path(__file__).parent
src = (D / "reel.src.html").read_text()
src = src.replace("__FONT700__", (D / "font700.b64").read_text()).replace("__LOGO__", (D / "logo.b64").read_text())
(D / "reel.html").write_text(src)
mode = sys.argv[1]

with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox", "--disable-gpu-vsync"])
    pg = b.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
    pg.goto((D / "reel.html").as_uri())
    pg.evaluate("window.ready")
    canvas = pg.locator("#c")
    if mode == "beats":
        out = D / "beats"; out.mkdir(exist_ok=True)
        times = [float(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else [k * 0.5 + 0.3 for k in range(30)]
        for i, t in enumerate(times):
            pg.evaluate(f"seek({t})")
            canvas.screenshot(path=str(out / f"b{i:02d}.png"))
    elif mode == "audio":
        wav = pg.evaluate("renderAudio()")
        (D / "sound.wav").write_bytes(base64.b64decode(wav))
    elif mode == "full":
        out = D / "sub"; out.mkdir(exist_ok=True)
        n = 0
        for f in range(15 * 60):
            for j in range(3):
                t = f / 60 + (j - 1) / 180
                pg.evaluate(f"seek({t})")
                canvas.screenshot(path=str(out / f"s{n:05d}.png"))
                n += 1
            if f % 60 == 0:
                print("frame", f, flush=True)
    b.close()
