"""OSRM per le riprese: tabella distanze/tempi REALE (OSRM, scaricata una volta), geometria reale se disponibile."""
import json, math, re, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit, parse_qs
T = json.load(open(sys.argv[1]))
P = [(11.3920,44.5050),(11.3440,44.4985),(11.3310,44.4940),(11.3260,44.4890),(11.3170,44.5180),(11.3080,44.4920),(11.3300,44.5150),(11.3620,44.4880),(11.3820,44.4930),(11.3560,44.4810),(11.3650,44.5080),(11.3720,44.4760),(11.3480,44.5260),(11.3220,44.5120),(11.3600,44.5200),(11.3730,44.5150),(11.2950,44.5010),(11.3380,44.5060),(11.3900,44.4830)]
def idx(p):
    i = min(range(len(P)), key=lambda k: (P[k][0]-p[0])**2 + (P[k][1]-p[1])**2)
    if (P[i][0]-p[0])**2 + (P[i][1]-p[1])**2 > 1e-6: print("MISS", p, flush=True)
    return i
def enc(v):
    v = ~(v << 1) if v < 0 else (v << 1); out = ""
    while v >= 0x20: out += chr((0x20 | (v & 0x1f)) + 63); v >>= 5
    return out + chr(v + 63)
def polyline(coords):
    s, a, b = "", 0, 0
    for lon, lat in coords:
        la, lo = round(lat*1e5), round(lon*1e5); s += enc(la-a) + enc(lo-b); a, b = la, lo
    return s
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        u = urlsplit(self.path); q = parse_qs(u.query)
        m = re.match(r"/(table|route)/v1/driving/(.+)", u.path)
        if not m:
            self.send_response(404); self.end_headers(); return
        pts = [tuple(map(float, p.split(","))) for p in m.group(2).split(";")]
        ix = [idx(p) for p in pts]
        if m.group(1) == "table":
            src = [int(x) for x in q.get("sources", [";".join(map(str, range(len(pts))))])[0].split(";")]
            dst = [int(x) for x in q.get("destinations", [";".join(map(str, range(len(pts))))])[0].split(";")]
            body = {"code": "Ok", "distances": [[T["distances"][ix[i]][ix[j]] for j in dst] for i in src],
                    "durations": [[T["durations"][ix[i]][ix[j]] for j in dst] for i in src]}
        else:
            legs = []
            for a, b in zip(range(len(pts)), range(1, len(pts))):
                d, t = T["distances"][ix[a]][ix[b]], T["durations"][ix[a]][ix[b]]
                legs.append({"distance": d, "duration": t, "steps": [{"distance": d, "duration": t, "name": "", "geometry": polyline([pts[a], pts[b]]),
                             "intersections": [], "maneuver": {"location": list(pts[a]), "type": "depart"}}],
                             "annotation": {"nodes": [], "distance": [d], "duration": [t]}, "summary": ""})
            body = {"code": "Ok", "routes": [{"distance": sum(l["distance"] for l in legs), "duration": sum(l["duration"] for l in legs),
                                               "legs": legs, "geometry": polyline(pts)}], "waypoints": [{"location": list(p)} for p in pts]}
        out = json.dumps(body).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(out)))
        self.end_headers(); self.wfile.write(out)
HTTPServer(("127.0.0.1", 5000), H).serve_forever()
