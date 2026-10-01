"""Read-only, on-demand routing diagnostics; never calls paid traffic APIs."""
import os
import time
from urllib.parse import urlparse

import requests

from .platform_settings import (
    get_platform_setting, mapbox_access_token, osrm_url, traffic_provider_name,
)


def routing_health(db):
    provider = traffic_provider_name(db)
    traffic = {
        "provider": provider if provider in ("none", "mapbox") else "unsupported",
        "configured": provider == "mapbox" and bool(mapbox_access_token(db)),
    }
    source = "database" if get_platform_setting(db, "osrm_url") else (
        "environment" if os.getenv("OSRM_URL") else "default")
    osrm = {"configured": False, "reachable": False, "status": "invalid_configuration",
            "response_ms": None, "configuration_source": source}
    result = {"osrm": osrm, "traffic": traffic}
    try:
        url = osrm_url(db)
        host = urlparse(url).hostname
    except ValueError:
        return result
    osrm["configured"] = True
    if os.getenv("GIROFACILE_RUNTIME") == "docker-compose" and host in ("localhost", "127.0.0.1", "::1"):
        osrm["warning"] = "docker_loopback_configuration"
    started = time.perf_counter()
    try:
        # Nearest without a radius works on regional extracts too. One read-only
        # request, no cache writes, retries, redirects or provider fallback.
        response = requests.get(f"{url}/nearest/v1/driving/0,0", params={"number": 1},
                                timeout=(2, 3), allow_redirects=False)
        osrm["reachable"] = True
        osrm["status"] = "invalid_response"
        if response.status_code == 200:
            payload = response.json()
            if (isinstance(payload, dict) and payload.get("code") == "Ok"
                    and isinstance(payload.get("waypoints"), list) and payload["waypoints"]
                    and isinstance(payload["waypoints"][0], dict)
                    and isinstance(payload["waypoints"][0].get("location"), list)
                    and len(payload["waypoints"][0]["location"]) == 2):
                osrm["status"] = "ok"
    except (ValueError, TypeError):
        osrm["status"] = "invalid_response"
    except requests.RequestException:
        osrm["status"] = "unreachable"
    finally:
        osrm["response_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return result
