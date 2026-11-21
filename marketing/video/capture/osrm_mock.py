"""OSRM finto per le riprese: distanze in linea d'aria x1.35, 30 km/h, geometria a segmenti."""
import json, math, re
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit as urlparse, parse_qs

def hav(a, b):
    (lo1, la1), (lo2, la2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    d = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lo2 - lo1) / 2) ** 2
    return 6371000 * 2 * math.atan2(math.sqrt(d), math.sqrt(1 - d)) * 1.35

def enc(v):
    v = ~(v << 1) if v < 0 else (v << 1)
    out = ""
    while v >= 0x20:
        out += chr((0x20 | (v & 0x1f)) + 63); v >>= 5
    return out + chr(v + 63)

def polyline(coords):
    s, plat, plon = "", 0, 0
    for lon, lat in coords:
        la, lo = round(lat * 1e5), round(lon * 1e5)
        s += enc(la - plat) + enc(lo - plon); plat, plon = la, lo
    return s

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        m = re.match(r"/(table|route)/v1/driving/(.+)", u.path)
        pts = [tuple(map(float, p.split(","))) for p in m.group(2).split(";")]
        if m.group(1) == "table":
            src = [int(x) for x in q.get("sources", [";".join(map(str, range(len(pts))))])[0].split(";")]
            dst = [int(x) for x in q.get("destinations", [";".join(map(str, range(len(pts))))])[0].split(";")]
            dist = [[hav(pts[i], pts[j]) for j in dst] for i in src]
            body = {"code": "Ok", "distances": dist, "durations": [[d / 8.33 for d in row] for row in dist]}
        else:
            legs = []
            for a, b in zip(pts, pts[1:]):
                d = hav(a, b)
                legs.append({"distance": d, "duration": d / 8.33, "steps": [{"distance": d, "duration": d / 8.33, "name": "",
                             "geometry": polyline([a, b]), "intersections": [], "maneuver": {"location": list(a), "type": "depart"}}],
                             "annotation": {"nodes": [], "distance": [d], "duration": [d / 8.33]}, "summary": ""})
            body = {"code": "Ok", "routes": [{"distance": sum(l["distance"] for l in legs), "duration": sum(l["duration"] for l in legs),
                                               "legs": legs, "geometry": polyline(pts)}], "waypoints": []}
        out = json.dumps(body).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(out)))
        self.end_headers(); self.wfile.write(out)

HTTPServer(("127.0.0.1", 5000), H).serve_forever()
