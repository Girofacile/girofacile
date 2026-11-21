"""Prepara la mappa delle scene "a occhio" / "giro più corto".

Input (scaricati una volta dal browser, perché da qui OSM e OSRM non sono raggiungibili):
  - mosaic14.webp: tessere OSM z14 x 8704-8711, y 5922-5928 (stile del gestionale)
  - osrm_routes.json: /route/v1/driving di OSRM per l'ordine "mess" e "opt" (overview=full, geojson)
Output: public/map/bologna.jpg e src/data/route.json (coordinate in px della finestra 960x646).
Uso: python3 scripts/build_map.py /percorso/mosaic14.webp
"""
import json, math, os, sys
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
P = [(11.3920,44.5050),(11.3440,44.4985),(11.3310,44.4940),(11.3260,44.4890),(11.3170,44.5180),(11.3080,44.4920),(11.3300,44.5150),(11.3620,44.4880),(11.3820,44.4930),(11.3560,44.4810),(11.3650,44.5080),(11.3720,44.4760),(11.3480,44.5260)]  # deposito + C001..C012 (capture/seed.py)
def px(lon, lat, z=14):
    n = 256 * 2 ** z
    return ((lon + 180) / 360 * n - 8704 * 256, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n - 5922 * 256)
W, H = 1427, 960; X0, Y0 = 1187 - W // 2, 927 - H // 2; s = 960 / W
os.makedirs(f"{ROOT}/public/map", exist_ok=True)
Image.open(sys.argv[1]).convert("RGB").crop((X0, Y0, X0 + W, Y0 + H)).save(f"{ROOT}/public/map/bologna.jpg", quality=92)
def css(p): x, y = px(*p); return [round((x - X0) * s, 1), round((y - Y0) * s, 1)]
def resample(pts, N=420):
    d = [0]
    for a, b in zip(pts, pts[1:]): d.append(d[-1] + math.dist(a, b))
    out, j = [], 0
    for k in range(N):
        t = d[-1] * k / (N - 1)
        while j < len(d) - 2 and d[j + 1] < t: j += 1
        u = (t - d[j]) / ((d[j + 1] - d[j]) or 1)
        out.append([round(pts[j][0] + (pts[j + 1][0] - pts[j][0]) * u, 1), round(pts[j][1] + (pts[j + 1][1] - pts[j][1]) * u, 1)])
    return out
R = json.load(open(f"{HERE}/osrm_routes.json")); O = json.load(open(f"{HERE}/orders.json"))
data = {"mapW": 960, "mapH": round(H * s, 1), "depot": css(P[0]), "stops": [css(p) for p in P[1:]],
        "mess": resample([css(c) for c in R["mess"]["coords"]]), "opt": resample([css(c) for c in R["opt"]["coords"]]),
        "messKm": round(R["mess"]["distance"] / 1000, 1), "optKm": round(R["opt"]["distance"] / 1000, 1),
        "messOrder": O["mess"], "optOrder": O["opt"]}
open(f"{ROOT}/src/data/route.json", "w").write(json.dumps(data, separators=(",", ":")))
print("ok", data["messKm"], data["optKm"])
