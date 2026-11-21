"""Campagna carburante (TOFU) – stile 'bozza bianco': bianco, titoli parola per parola, UI reale in finestre, pillole."""
import json, math, random, pathlib, html
from PIL import Image

ROOT = pathlib.Path(__file__).parent / "video"
CAP = pathlib.Path(__file__).parent / "capture" / "cap"
(ROOT / "assets/ui").mkdir(parents=True, exist_ok=True)
(ROOT / "compositions").mkdir(exist_ok=True)
B = json.load(open(CAP / "boxes.json"))
TOTAL = 28.0
SPEED = 1.12
BLUE, NAVY, INK, MUTED = "#1665ff", "#0f2250", "#16213a", "#5a6680"

def crop(name, state, x0, y0, x1, y1):
    im = Image.open(CAP / f"{state}.png").convert("RGB").crop((int(x0 * 2), int(y0 * 2), int(x1 * 2), int(y1 * 2)))
    im.save(ROOT / "assets/ui" / f"{name}.png"); return im.size
s_cli = crop("clienti", "A1", 234, 340, 834, 900)
s_sud = crop("suddivisione", "C0", 228, 80, 968, 472)
s_kpi = crop("kpi", "C0", 524, 80, 1122, 184)
crop("selbar", "A1", B["selbar"]["x"] - 14, B["selbar"]["y"] - 14, B["selbar"]["x"] + B["selbar"]["w"] + 14, B["selbar"]["y"] + B["selbar"]["h"] + 14)

# ---------- mappa illustrata: stesso set di fermate, ordine "a occhio" vs ordine ottimizzato ----------
rnd = random.Random(11)
MW, MH = 960, 700
depot = (480, 600)
stops = []
while len(stops) < 12:
    p = (rnd.uniform(90, 870), rnd.uniform(90, 520))
    if all(math.dist(p, q) > 120 for q in stops) and math.dist(p, depot) > 140:
        stops.append(p)
def tour(o): pts = [depot] + [stops[i] for i in o] + [depot]; return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
messy = list(range(12)); rnd.shuffle(messy)
while tour(messy) < 1.9 * 3000:  # garantisce un percorso davvero ingarbugliato
    rnd.shuffle(messy)
    if tour(messy) > 5200: break
left, cur, opt = set(range(12)), depot, []
while left:
    n = min(left, key=lambda i: math.dist(cur, stops[i])); opt.append(n); left.remove(n); cur = stops[n]
imp = True
while imp:
    imp = False
    for a in range(11):
        for b in range(a + 1, 12):
            c = opt[:a] + opt[a:b + 1][::-1] + opt[b + 1:]
            if tour(c) < tour(opt) - 1e-6: opt, imp = c, True
PM = [depot] + [stops[i] for i in messy] + [depot]
PO = [depot] + [stops[i] for i in opt] + [depot]
print("km relativi: a occhio", round(tour(messy)), "ottimizzato", round(tour(opt)))

streets = []
for i in range(9):
    y = 40 + i * 80 + rnd.uniform(-12, 12); streets.append(f'<path d="M -20 {y:.0f} L {MW+20} {y + rnd.uniform(-40, 40):.0f}"/>')
for i in range(12):
    x = 30 + i * 85 + rnd.uniform(-12, 12); streets.append(f'<path d="M {x:.0f} -20 L {x + rnd.uniform(-60, 60):.0f} {MH+20}"/>')
streets.append(f'<path d="M -20 650 C 300 520, 520 420, {MW+20} 120" style="stroke-width:26"/>')
dots = "".join(f'<circle class="stop" cx="{x:.0f}" cy="{y:.0f}" r="15"/>' for x, y in stops)
map_svg = f'''<svg width="{MW}" height="{MH}" viewBox="0 0 {MW} {MH}">
<rect width="{MW}" height="{MH}" fill="#f3f5f9"/>
<g fill="none" stroke="#ffffff" stroke-width="16" stroke-linecap="round">{''.join(streets)}</g>
<path id="route" d="" fill="none" stroke="#9aa3b5" stroke-width="9" stroke-linejoin="round" stroke-linecap="round" pathLength="1" stroke-dasharray="1 1" stroke-dashoffset="1" opacity="0"/>
<g id="stops" fill="#ffffff" stroke="{NAVY}" stroke-width="6">{dots}</g>
<rect x="{depot[0]-24}" y="{depot[1]-24}" width="48" height="48" rx="12" fill="{NAVY}"/>
</svg>'''

# ---------- markup helpers ----------
def title(tid, lines, top, size=84):
    out = []
    for ln in lines:
        words = []
        for w in ln.split(" "):
            acc = w.startswith("*")
            w = w.lstrip("*")
            words.append(f'<span class="wd{" acc" if acc else ""}">{html.escape(w)}</span>')
        out.append('<div class="ln">' + " ".join(words) + "</div>")
    return f'<div class="ttl" id="{tid}" style="top:{top}px;font-size:{size}px">' + "".join(out) + "</div>"

def window(wid, img, w, h, top, imgw=None, extra=""):
    return (f'<div class="win" id="{wid}" style="left:{540-w/2:.0f}px;top:{top}px;width:{w}px;height:{h}px">'
            f'<div class="bar"><i></i><i></i><i></i></div><div class="body" id="{wid}-body">'
            + (f'<img src="assets/ui/{img}.png" style="width:{imgw or w}px">' if img else "") + extra + "</div></div>")

def pill(pid, text, top, left=None, kind="ok"):
    icon = {"ok": f'<b class="ic ok">✓</b>', "no": '<b class="ic no">✕</b>', "warn": '<b class="ic warn">!</b>', "eur": '<b class="ic ok">€</b>'}[kind]
    pos = f"left:{left}px" if left is not None else "left:50%;margin-left:0"
    return f'<div class="pill" id="{pid}" style="top:{top}px;{pos}">{icon}<span>{text}</span></div>'

parts, js = [], []
js.append("tl.set('.pill', {xPercent:-50}, 0);")
A = js.append
def T_IN(tid, t): A(f"tl.fromTo('#{tid} .wd', {{opacity:0, y:46, filter:'blur(10px)'}}, {{opacity:1, y:0, filter:'blur(0px)', duration:0.5, ease:'expo.out', stagger:0.07}}, {t});")
def T_OUT(tid, t): A(f"tl.to('#{tid} .wd', {{opacity:0, y:-30, filter:'blur(10px)', duration:0.28, ease:'power3.in', stagger:0.03}}, {t});")
def W_IN(wid, t): A(f"tl.fromTo('#{wid}', {{opacity:0, y:140, scale:0.94, filter:'blur(8px)'}}, {{opacity:1, y:0, scale:1, filter:'blur(0px)', duration:0.75, ease:'expo.out'}}, {t});")
def W_OUT(wid, t): A(f"tl.to('#{wid}', {{opacity:0, y:-60, scale:0.96, filter:'blur(10px)', duration:0.35, ease:'power3.in'}}, {t});")
def P_IN(pid, t): A(f"tl.fromTo('#{pid}', {{opacity:0, y:24, scale:0.86, xPercent:-50}}, {{opacity:1, y:0, scale:1, xPercent:-50, duration:0.5, ease:'back.out(1.6)'}}, {t});")
def P_OUT(pid, t): A(f"tl.to('#{pid}', {{opacity:0, y:-20, duration:0.25, ease:'power3.in'}}, {t});")
SFX = []

# ---------- SCENE v5: messaggio più completo (dal documento di posizionamento) + outro con transizioni ----------
# Tempi "base"; il video esce accelerato di SPEED.

# 1 · HOOK (0–1.4)
parts.append(title("t1", ["Ogni km in più", "è *gasolio buttato."], 590, 118))
parts.append('<div id="flood" style="position:absolute;left:440px;top:770px;width:200px;height:200px;margin:-100px 0 0 -100px;border-radius:50%;background:'+BLUE+';z-index:30;transform:scale(0)"></div>')
A("tl.set('#t1 .ln:nth-child(1) .wd', {opacity:1}, 0);")
for sel, t in [(".ln:nth-child(2) .wd:nth-child(1)", 0.18), (".ln:nth-child(2) .wd:nth-child(2)", 0.32), (".ln:nth-child(2) .wd:nth-child(3)", 0.52)]:
    A(f"tl.fromTo('#t1 {sel}', {{opacity:0, scale:1.9, filter:'blur(10px)'}}, {{opacity:1, scale:1, filter:'blur(0px)', duration:0.22, ease:'expo.out'}}, {t});")
    SFX.append(("click-soft.mp3", t, 0.3, 0.7))
A("tl.fromTo('#t1', {scale:1.08}, {scale:1, duration:1.0, ease:'power2.out'}, 0);")
A("tl.fromTo('#t1 .acc', {'--hl':0}, {'--hl':1, duration:0.3, ease:'power3.out'}, 0.45);")
A("tl.to('#t1 .ln:nth-child(2) .acc', {scale:1.25, duration:0.35, ease:'power2.in'}, 0.95);")
A("tl.to('#t1 .wd:not(.acc)', {opacity:0, filter:'blur(12px)', scale:0.8, duration:0.25, ease:'power3.in'}, 1.0);")
A("tl.fromTo('#flood', {scale:0}, {scale:16, duration:0.38, ease:'expo.in'}, 1.0);")
A("tl.set('#t1', {opacity:0}, 1.38);")
SFX += [("whoosh.mp3", 1.0, 0.57, 0.7), ("impact-bass-1.mp3", 1.32, 2.1, 0.9)]

# 2 · PERCHÉ ORA (1.4–4.9): sul blu, il prezzo del gasolio sale
parts.append('<div id="stat" style="position:absolute;inset:0;z-index:31">'
             + title("t2", ["Il gasolio costa", "un terzo in più."], 330, 92).replace('class="ttl"', 'class="ttl light"')
             + '<div id="num" class="bignum" style="top:620px">1,67 €</div>'
             + '<div id="lab" class="statlab" style="top:900px"><span id="labA">al litro · un anno fa</span><span id="labB">al litro · oggi</span></div>'
             + '<div class="pill" id="p2" style="top:1010px;left:50%"><b class="ic up">↑</b><span><strong>+32%</strong> in un anno</span></div>'
             + '<div id="src" class="src" style="top:1130px">Prezzo medio gasolio self, Mimit · nov 2025 → 18 nov 2026</div></div>')
T_IN("t2", 1.45)
A("tl.fromTo('#num', {opacity:0, y:60, filter:'blur(12px)'}, {opacity:1, y:0, filter:'blur(0px)', duration:0.5, ease:'expo.out'}, 1.85);")
A("tl.fromTo('#labA', {opacity:0}, {opacity:1, duration:0.3}, 2.0);")
A("tl.to(P, {v:2.204, duration:0.85, ease:'power2.inOut', onUpdate:drawNum}, 2.15);")
A("tl.to('#num', {scale:1.06, duration:0.12, yoyo:true, repeat:1, ease:'power2.out'}, 3.0);")
A("tl.to('#labA', {opacity:0, y:-20, duration:0.2}, 2.95); tl.fromTo('#labB', {opacity:0, y:20}, {opacity:1, y:0, duration:0.3, ease:'expo.out'}, 3.0);")
P_IN("p2", 3.1); A("tl.fromTo('#src', {opacity:0}, {opacity:1, duration:0.4}, 3.15);")
SFX += [("pop.mp3", 3.1, 0.6, 0.5)]
A("tl.to('#stat', {opacity:0, filter:'blur(12px)', y:-80, duration:0.3, ease:'power3.in'}, 4.55);")
A("tl.to('#flood', {y:-3700, duration:0.45, ease:'expo.inOut'}, 4.6);")
SFX += [("whoosh-short.mp3", 4.6, 0.57, 0.6)]

# 3 · PROBLEMA (4.9–8.7)
parts.append(title("t3", ["E i giri? Ancora", "*a *occhio."], 290))
parts.append(window("w3", None, 960, 700, 500, extra=map_svg))
parts.append(pill("p3a", "Fermate nell'ordine sbagliato", 1060, kind="no"))
parts.append(pill("p3b", "Km e gasolio che nessuno vede", 1160, kind="no"))
T_IN("t3", 4.95); W_IN("w3", 5.05)
A("tl.fromTo('#w3 .stop', {scale:0}, {scale:1, duration:0.35, ease:'back.out(2)', stagger:0.04}, 5.3);")
A("tl.fromTo('#route', {strokeDashoffset:1, opacity:1}, {strokeDashoffset:0, opacity:1, duration:1.3, ease:'power1.inOut'}, 5.45);")
P_IN("p3a", 6.55); P_IN("p3b", 7.0)
SFX += [("pop.mp3", 6.55, 0.6, 0.45), ("pop.mp3", 7.0, 0.6, 0.45)]
T_OUT("t3", 8.55); P_OUT("p3a", 8.55); P_OUT("p3b", 8.6)

# 4 · SOLUZIONE (8.8–11.8)
parts.append(title("t4", ["GiroFacile trova", "*il *giro *più *corto."], 290))
parts.append(pill("p4", "Per ogni furgone, in pochi minuti", 1150))
T_IN("t4", 8.8)
A("tl.to(R, {u:1, duration:1.3, ease:'power3.inOut', onUpdate:drawRoute}, 9.15);")
A("tl.to('#route', {attr:{stroke:'" + BLUE + "'}, duration:0.6}, 9.4); tl.to('#stops', {attr:{stroke:'" + BLUE + "'}, duration:0.6}, 9.4);")
P_IN("p4", 10.2); SFX += [("whoosh-short.mp3", 9.1, 0.57, 0.35), ("pop.mp3", 10.2, 0.6, 0.45)]
T_OUT("t4", 11.55); W_OUT("w3", 11.6); P_OUT("p4", 11.6)

# 5 · IL PILASTRO: fasce di scarico, ZTL e sponda (11.8–15.4)
cli_w = 960; cli_h = min(int(s_cli[1] * cli_w / s_cli[0]) + 54, 640)
parts.append(title("t5", ["Sa già orari di scarico,", "*ZTL *e *sponda."], 290, 78))
parts.append(window("w5", "clienti", cli_w, cli_h, 500))
for n, (txt, kind, top) in enumerate([("Fasce di scarico nel calcolo", "ok", 830), ("Avviso ZTL prima di partire", "warn", 940), ("Avviso sponda per il mezzo", "warn", 1050)]):
    parts.append(pill(f"p5{n}", txt, top, kind=kind))
T_IN("t5", 11.85); W_IN("w5", 11.95)
A("tl.fromTo('#w5-body img', {y:0}, {y:-90, duration:3.2, ease:'power1.inOut'}, 12.2);")
for n in range(3):
    P_IN(f"p5{n}", 12.8 + n * 0.35); SFX.append(("pop.mp3", 12.8 + n * 0.35, 0.6, 0.4))
T_OUT("t5", 15.15); W_OUT("w5", 15.2)
for n in range(3): P_OUT(f"p5{n}", 15.15 + n * 0.04)

# 6 · CALCOLO (15.4–18.9)
sud_w = 980; sud_h = int(s_sud[1] * sud_w / s_sud[0]) + 54
parts.append(title("t6", ["Un clic.", "*Giri *pronti."], 290))
parts.append(window("w6", "suddivisione", sud_w, sud_h, 560))
parts.append(pill("p6", "<strong>3 giri</strong> calcolati in automatico", 1110))
T_IN("t6", 15.45); W_IN("w6", 15.55)
A("tl.fromTo('#w6-body img', {scale:1, transformOrigin:'50% 0%'}, {scale:1.12, duration:3.2, ease:'power1.inOut'}, 15.9);")
P_IN("p6", 16.4); SFX.append(("pop.mp3", 16.4, 0.6, 0.45))
T_OUT("t6", 18.65); W_OUT("w6", 18.7); P_OUT("p6", 18.7)

# 7 · IL COSTO DEL GASOLIO (18.9–22.6)
kpi_w = 980; kpi_h = int(s_kpi[1] * kpi_w / s_kpi[0])
RX, RY, RW, RH = 50 + kpi_w * 0.5 + 6, 600 + 6, kpi_w * 0.5 - 12, kpi_h - 12
parts.append(title("t7", ["Il costo del gasolio,", "*prima *di *partire."], 290, 80))
parts.append(f'<div class="win flat" id="w7" style="left:50px;top:600px;width:{kpi_w}px;height:{kpi_h}px"><div class="body"><img src="assets/ui/kpi.png" style="width:{kpi_w}px"></div></div>')
parts.append(f'<div id="ring7" style="position:absolute;left:{RX:.0f}px;top:{RY:.0f}px;width:{RW:.0f}px;height:{RH}px;border:5px solid {BLUE};border-radius:26px;opacity:0;z-index:6"></div>')
parts.append(pill("p7a", "<strong>€ 9,02</strong> di carburante stimato", 900))
parts.append(pill("p7b", "<strong>54,3 km</strong> per 12 consegne", 1020))
T_IN("t7", 18.95); W_IN("w7", 19.05)
A("tl.fromTo('#ring7', {opacity:0, scale:1.08}, {opacity:1, scale:1, duration:0.5, ease:'expo.out'}, 19.9);")
P_IN("p7a", 20.3); P_IN("p7b", 20.65); SFX += [("pop.mp3", 20.3, 0.6, 0.45), ("pop.mp3", 20.65, 0.6, 0.4)]

# 8 · OUTRO (22.4–28): il riquadro del carburante diventa il logo
T_OUT("t7", 22.35); P_OUT("p7a", 22.35); P_OUT("p7b", 22.4)
TX, TY, TS = 540 - 90, 480, 180
parts.append(f'<div id="morph" style="position:absolute;left:{TX}px;top:{TY}px;width:{TS}px;height:{TS}px;border-radius:24%;background:{BLUE};opacity:0;z-index:7"></div>')
A("tl.to('#ring7', {borderWidth:60, duration:0.22, ease:'power2.in'}, 22.5);")
A("tl.set('#morph', {opacity:1}, 22.7); tl.set('#ring7', {opacity:0}, 22.7);")
A("tl.to('#w7', {opacity:0, scale:0.92, filter:'blur(12px)', duration:0.3, ease:'power3.in'}, 22.6);")
A(f"tl.fromTo('#morph', {{x:{RX+RW/2-(TX+TS/2):.1f}, y:{RY+RH/2-(TY+TS/2):.1f}, scaleX:{RW/TS:.3f}, scaleY:{RH/TS:.3f}, rotation:0}}, {{x:0, y:0, scaleX:1, scaleY:1, rotation:360, duration:0.6, ease:'expo.inOut'}}, 22.72);")
SFX += [("whoosh.mp3", 22.6, 0.57, 0.7), ("impact-bass-1.mp3", 23.3, 2.1, 0.75)]
parts.append(f'''<div id="logo8" style="position:absolute;left:{540-150}px;top:{TY+TS/2-150:.0f}px;width:300px;height:300px;z-index:8">
 <svg width="300" height="300" style="position:absolute;inset:0;overflow:visible"><circle id="arc8" cx="150" cy="150" r="140" fill="none" stroke="{BLUE}" stroke-width="7" stroke-linecap="round" pathLength="1" stroke-dasharray="0.62 1" stroke-dashoffset="0.62" opacity="0" transform="rotate(130 150 150)"/>
 <circle id="dot8" cx="150" cy="150" r="140" fill="none" stroke="{BLUE}" stroke-width="5" stroke-linecap="round" pathLength="1" opacity="0" transform="rotate(-100 150 150)" style="stroke-dasharray:0.001 0.03"/></svg>
 <div id="tile8" style="position:absolute;left:60px;top:60px;width:180px;height:180px;border-radius:24%;overflow:hidden;opacity:0"><img id="icon8" src="assets/logo.png" style="width:100%;height:100%"></div></div>''')
A("tl.set('#tile8', {opacity:1}, 23.32); tl.set('#morph', {opacity:0}, 23.34);")
A("tl.fromTo('#icon8', {scale:0.55, rotation:-90}, {scale:1, rotation:0, duration:0.55, ease:'expo.out'}, 23.32);")
A("tl.fromTo('#tile8', {scale:1}, {scale:1.12, duration:0.12, yoyo:true, repeat:1, ease:'power2.out'}, 23.32);")
A("tl.fromTo('#arc8', {strokeDashoffset:0.62, opacity:0}, {strokeDashoffset:0, opacity:1, duration:0.8, ease:'power3.out'}, 23.45);")
A("tl.fromTo('#dot8', {opacity:0, rotation:-160, transformOrigin:'50% 50%'}, {opacity:1, rotation:-100, duration:0.6, ease:'expo.out'}, 23.9);")
brand = "".join(f'<span class="ch">{c}</span>' for c in "GiroFacile")
parts.append(f'<div id="name8" class="brand" style="top:{TY+TS/2+150:.0f}px">{brand}</div>')
A("tl.fromTo('#name8', {opacity:1}, {opacity:1, duration:0.01}, 23.5);")
A("tl.fromTo('#name8 .ch', {opacity:0, y:70, rotationX:-80, filter:'blur(8px)'}, {opacity:1, y:0, rotationX:0, filter:'blur(0px)', duration:0.55, ease:'expo.out', stagger:0.035}, 23.55);")
parts.append(title("t8", ["I giri di domani,", "*pronti *in *pochi *minuti."], TY + TS // 2 + 290, 54).replace('class="ttl"', 'class="ttl sub"'))
T_IN("t8", 24.05)
parts.append(f'<div id="cta8" class="cta2" style="top:{TY+TS/2+440:.0f}px"><div id="cta8bg"></div><span id="cta8t">Provalo gratis sui tuoi giri</span></div>')
A("tl.fromTo('#cta8', {opacity:1}, {opacity:1, duration:0.01}, 24.6);")
A("tl.fromTo('#cta8bg', {scaleX:0}, {scaleX:1, duration:0.5, ease:'expo.inOut'}, 24.6);")
A("tl.fromTo('#cta8t', {opacity:0, y:30}, {opacity:1, y:0, duration:0.45, ease:'expo.out'}, 24.95);")
A("tl.fromTo('#cta8', {scale:1}, {scale:1.04, duration:0.25, yoyo:true, repeat:3, ease:'sine.inOut'}, 26.0);")
SFX += [("pop.mp3", 24.95, 0.6, 0.5)]
parts.append(f'<div id="url8" class="tag" style="top:{TY+TS/2+565:.0f}px;font-size:40px">14 giorni gratis · girofacile.it</div>')
A("tl.fromTo('#url8', {opacity:0, clipPath:'inset(0 100% 0 0)'}, {opacity:1, clipPath:'inset(0 0% 0 0)', duration:0.6, ease:'power2.inOut'}, 25.3);")
TOTAL = 28.0
OUT_T = round(TOTAL / SPEED, 2)
CUR = []

# cursore
for tm, tc, x, y in CUR:
    A(f"tl.fromTo('#cur', {{x:{x+240:.0f}, y:{y+260:.0f}, opacity:0}}, {{x:{x:.0f}, y:{y:.0f}, opacity:1, duration:{tc-tm-0.1:.2f}, ease:'power3.out'}}, {tm});")
    A(f"tl.to('#curi', {{scale:0.8, duration:0.07, ease:'power2.in', yoyo:true, repeat:1}}, {tc});")
    A(f"tl.to('#cur', {{opacity:0, duration:0.2}}, {tc+0.45:.2f});")
    SFX.append(("click.mp3", tc - 0.04, 0.36, 0.8))

scene = f"""<template>
<style>
  @font-face {{ font-family:'Bricolage Grotesque'; font-weight:700; src:url('assets/fonts/bricolage-grotesque-latin-700-normal.woff2') format('woff2'); }}
  @font-face {{ font-family:'IBM Plex Sans'; font-weight:500; src:url('assets/fonts/ibm-plex-sans-latin-500-normal.woff2') format('woff2'); }}
  @font-face {{ font-family:'IBM Plex Sans'; font-weight:600; src:url('assets/fonts/ibm-plex-sans-latin-600-normal.woff2') format('woff2'); }}
  #root {{ position:absolute; inset:0; background:#ffffff; overflow:hidden; font-family:'IBM Plex Sans'; color:{INK}; }}
  #root .ttl {{ position:absolute; left:60px; right:60px; text-align:center; font-family:'Bricolage Grotesque'; font-weight:700; letter-spacing:-0.025em; line-height:1.06; color:{NAVY}; }}
  #root .ln {{ white-space:nowrap; }}
  #root .wd {{ display:inline-block; opacity:0; position:relative; }}
  #root .acc {{ color:{BLUE}; --hl:1; isolation:isolate; }}
  #root .acc::after {{ content:''; position:absolute; left:-4px; right:-4px; bottom:6%; height:30%; background:#e4edff; z-index:-1; transform-origin:0 50%; transform:scaleX(var(--hl)); }}
  #root .win {{ position:absolute; background:#fff; border-radius:28px; overflow:hidden; box-shadow:0 24px 70px rgba(15,34,80,.16), 0 0 0 1.5px #e6eaf2; opacity:0; }}
  #root .win.flat {{ overflow:visible; }}
  #root .win.flat .body {{ border-radius:24px; overflow:hidden; }}
  #root .bar {{ height:54px; background:#f6f8fc; border-bottom:1.5px solid #e6eaf2; display:flex; gap:12px; align-items:center; padding-left:24px; }}
  #root .bar i {{ width:16px; height:16px; border-radius:50%; background:#ff5f57; display:block; }}
  #root .bar i:nth-child(2) {{ background:#febc2e; }} #root .bar i:nth-child(3) {{ background:#28c840; }}
  #root .body {{ position:relative; overflow:hidden; height:calc(100% - 54px); }}
  #root .win.flat .body {{ height:100%; }}
  #root .body img {{ display:block; }}
  #root .pill {{ position:absolute; display:flex; align-items:center; gap:14px; white-space:nowrap; background:#fff; border-radius:999px; padding:16px 30px 16px 18px;
               box-shadow:0 12px 32px rgba(15,34,80,.16), 0 0 0 1.5px #e6eaf2; font-size:36px; font-weight:500; color:{INK}; opacity:0; z-index:10; }}
  #root .pill strong {{ color:{BLUE}; font-weight:600; }}
  #root .ic {{ width:44px; height:44px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:26px; font-weight:600; }}
  #root .ic.ok {{ background:#e4edff; color:{BLUE}; }} #root .ic.no {{ background:#ffe4e1; color:#d92d20; }}
  #root .ov {{ position:absolute; opacity:0; z-index:8; border-radius:18px; }}
  #root .stop {{ transform-box:fill-box; transform-origin:50% 50%; }}
  #root .brand {{ position:absolute; left:0; right:0; text-align:center; font-family:'Bricolage Grotesque'; font-weight:700; font-size:124px; letter-spacing:-0.03em; color:{NAVY}; opacity:0; }}
  #root .tag {{ position:absolute; left:0; right:0; text-align:center; font-size:46px; font-weight:500; color:{MUTED}; opacity:0; }}
  #root .cta {{ position:absolute; left:290px; width:500px; height:92px; border-radius:999px; background:{BLUE}; color:#fff; display:flex; align-items:center; justify-content:center;
               font-size:40px; font-weight:600; opacity:0; box-shadow:0 12px 28px rgba(22,101,255,.28); }}
  #root .ttl.light {{ color:#ffffff; }}
  #root .ttl.light .acc {{ color:#ffffff; }}
  #root .ttl.sub {{ font-size:54px; color:#5a6680; font-family:'IBM Plex Sans'; font-weight:500; letter-spacing:0; }}
  #root .ttl.sub .acc {{ color:{BLUE}; font-weight:600; }}
  #root .ttl.sub .acc::after {{ display:none; }}
  #root .bignum {{ position:absolute; left:0; right:0; text-align:center; font-family:'Bricolage Grotesque'; font-weight:700; font-size:250px; letter-spacing:-0.04em; color:#fff; opacity:0; line-height:1; }}
  #root .statlab {{ position:absolute; left:0; right:0; height:60px; text-align:center; font-size:44px; font-weight:500; color:rgba(255,255,255,.85); }}
  #root .statlab span {{ position:absolute; left:0; right:0; opacity:0; }}
  #root .src {{ position:absolute; left:80px; right:80px; text-align:center; font-size:28px; color:rgba(255,255,255,.75); opacity:0; }}
  #root .ic.up {{ background:#ffe4e1; color:#d92d20; }} #root .ic.warn {{ background:#fff1d6; color:#b25e00; }}
  #root .brand .ch {{ display:inline-block; }}
  #root .cta2 {{ position:absolute; left:250px; width:580px; height:96px; display:flex; align-items:center; justify-content:center; font-size:40px; font-weight:600; color:#fff; opacity:0; }}
  #cta8bg {{ position:absolute; inset:0; border-radius:999px; background:{BLUE}; box-shadow:0 12px 28px rgba(22,101,255,.28); transform-origin:50% 50%; }}
  #cta8t {{ position:relative; }}
  #cur {{ position:absolute; left:-9px; top:-6px; width:78px; height:78px; opacity:0; z-index:20; }}
  #curi {{ width:100%; height:100%; transform-origin:9px 6px; }}
</style>
<div id="root" data-composition-id="spot" data-width="1080" data-height="1920">
{chr(10).join(parts)}
<div id="cur"><svg id="curi" viewBox="0 0 24 24"><path d="M3 2 L3 20 L8 15.5 L11.5 22.5 L14.5 21 L11 14.2 L18 14 Z" fill="#16213a" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/></svg></div>
<script>
  const PM = {json.dumps([[round(x,1), round(y,1)] for x, y in PM])}, PO = {json.dumps([[round(x,1), round(y,1)] for x, y in PO])};
  const R = {{u:0}};
  function drawRoute() {{
    const u = R.u; let d = '';
    for (let i = 0; i < PM.length; i++) {{ const x = PM[i][0] + (PO[i][0]-PM[i][0])*u, y = PM[i][1] + (PO[i][1]-PM[i][1])*u; d += (i ? ' L ' : 'M ') + x.toFixed(1) + ' ' + y.toFixed(1); }}
    document.getElementById('route').setAttribute('d', d);
  }}
  drawRoute();
  const P = {{v:1.668}};
  function drawNum() {{ document.getElementById('num').textContent = P.v.toFixed(2).replace('.', ',') + ' €'; }}
  const tl = gsap.timeline({{ paused: true }});
  tl.set(R, {{u:0}}, 0); tl.call(drawRoute, null, 0); tl.set(P, {{v:1.668}}, 0); tl.call(drawNum, null, 0);
  {chr(10).join(js)}
  tl.set({{}}, {{}}, {TOTAL});
  const outer = gsap.timeline({{ paused: true }});
  outer.to(tl, {{ time: {TOTAL}, duration: {OUT_T}, ease: 'none' }}, 0);
  window.__timelines['spot'] = outer;
</script>
</div>
</template>"""
(ROOT / "compositions" / "spot.html").write_text(scene)

OUT_T = round(TOTAL / SPEED, 2)
SFX = [(f, t / SPEED, d, v) for f, t, d, v in SFX]
SFX.sort(key=lambda s: s[1]); lanes, ends = [], []
for f, t, d, v in SFX:
    for li, e in enumerate(ends):
        if t >= e: ends[li] = t + d; lanes.append(3 + li); break
    else: ends.append(t + d); lanes.append(3 + len(ends) - 1)
audio = "\n      ".join(f'<audio id="fx{n}" class="clip" src="assets/sfx/{f}" data-start="{t:.2f}" data-duration="{d}" data-track-index="{ln}" data-volume="{v}"></audio>'
                       for n, ((f, t, d, v), ln) in enumerate(zip(SFX, lanes)))
(ROOT / "index.html").write_text(f"""<!doctype html>
<html lang="it"><head><meta charset="UTF-8" /><meta name="viewport" content="width=1080, height=1920" />
<script src="assets/js/gsap.min.js"></script>
<style>* {{ margin:0; padding:0; box-sizing:border-box; }} html, body {{ width:1080px; height:1920px; overflow:hidden; background:#fff; }} #root {{ position:relative; width:1080px; height:1920px; }}</style></head>
<body>
  <div id="root" data-composition-id="main" data-start="0" data-duration="{OUT_T}" data-width="1080" data-height="1920">
    <div id="spot" data-composition-id="spot" data-composition-src="compositions/spot.html" data-start="0" data-duration="{OUT_T}" data-track-index="1" data-track-kind="graphics" data-width="1080" data-height="1920"></div>
    <audio id="music" class="clip" src="assets/music.wav" data-start="0" data-duration="{OUT_T}" data-track-index="2" data-volume="0.8"></audio>
    {audio}
  </div>
  <script>window.__timelines["main"] = gsap.timeline({{ paused: true }});</script>
</body></html>""")
print("ok")
