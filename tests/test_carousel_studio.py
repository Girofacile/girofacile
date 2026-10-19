"""Standalone tests: no application DB, credentials or AI calls."""
import importlib.util
import json
import io
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

path = Path(__file__).resolve().parents[1] / "tools/carousel_studio/server.py"
spec = importlib.util.spec_from_file_location("carousel_studio", path)
studio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(studio)


class CarouselTests(unittest.TestCase):
    def brief(self, **overrides):
        return {"topic": "Consegne organizzate", "facts": "Pianificazione delle consegne", "audience": "piccole flotte", "count": 6, **overrides}

    def test_brand_reads_current_tokens_and_logo(self):
        brand = studio.brand_profile()
        self.assertEqual(brand["colors"]["primary"], "#1665ff")
        self.assertEqual(brand["fonts"]["display"], "Bricolage Grotesque")
        self.assertTrue((studio.ROOT / brand["sources"][1]).is_file())
        self.assertIn("Proposta", brand["tone_status"])

    def test_default_brief_is_ready_without_user_input(self):
        brand = studio.brand_profile()
        brief = brand["default_brief"]
        self.assertEqual(len(brief["facts"].splitlines()), 6)
        self.assertEqual(brief["count"], 9)
        self.assertIn("https://girofacile.it/login", brief["cta"])
        result = studio.generate(brief)
        studio.validate_output(result, studio.brief_input(brief))
        self.assertEqual(len(result["carousels"]), 3)

    def test_brief_tracks_source_copy_changes(self):
        landing = (studio.ROOT / "static/landing/index.html").read_text()
        changed = landing.replace("Pianificazione intelligente", "Pianificazione verificata")
        self.assertIn("Pianificazione verificata", studio.project_brief(changed)["brief"]["facts"])
        with self.assertRaises(ValueError):
            studio.project_brief("<h1>Landing incompleta</h1>")

    def test_all_counts_stages_and_cta_separation(self):
        for count in range(5, 10):
            result = studio.generate(self.brief(count=count, cta="Richiedi una valutazione"))
            self.assertEqual([c["stage"] for c in result["carousels"]], ["TOFU", "MOFU", "BOFU"])
            for carousel in result["carousels"]:
                self.assertEqual(len(carousel["slides"]), count)
                self.assertIn("Pianificazione delle consegne", [s["body"] for s in carousel["slides"]])
                self.assertEqual(carousel["slides"][-1]["body"] == "Richiedi una valutazione", carousel["stage"] == "BOFU")

    def test_invalid_briefs_and_no_silent_fact_loss(self):
        for change in [{"count": True}, {"stage": "other"}, {"facts": ""}, {"topic": 3}, {"mode": "other"}, {"facts": "x" * 361}, {"facts": "a\nb\nc", "count": 5}]:
            with self.assertRaises(ValueError):
                studio.generate(self.brief(**change))

    def test_long_local_project_remains_reopenable(self):
        brief = studio.brief_input(self.brief(count=9, facts="\n".join(["x" * 360] * 6)))
        result = studio.generate(brief)
        studio.validate_output(result, brief)
        self.assertEqual(sum(s["body"] == "x" * 360 for s in result["carousels"][0]["slides"]), 6)

    def test_ai_adapter_and_missing_configuration(self):
        brief = studio.brief_input(self.brief(mode="ai"))
        expected = studio.local_carousels(brief)
        response = {"choices": [{"message": {"content": json.dumps({"carousels": expected})}}]}
        with patch.dict(studio.os.environ, {"OPENAI_API_KEY": "test-not-real"}), patch.object(studio, "urlopen", return_value=io.BytesIO(json.dumps(response).encode())) as call:
            self.assertEqual(studio.generate(brief)["carousels"], expected)
            request = call.call_args.args[0]
            self.assertEqual(request.full_url, "https://api.openai.com/v1/chat/completions")
            self.assertNotIn("test-not-real", request.data.decode())
        with patch.dict(studio.os.environ, {"OPENAI_API_KEY": ""}):
            with self.assertRaises(ValueError):
                studio.generate(brief)

    def test_ai_output_rejects_duplicate_stages_and_long_text(self):
        brief = studio.brief_input(self.brief())
        data = {"carousels": studio.local_carousels(brief)}
        self.assertEqual(len(studio.validate_output(data, brief)), 3)
        data["carousels"][1]["stage"] = "TOFU"
        with self.assertRaises(ValueError):
            studio.validate_output(data, brief)
        data["carousels"][1]["stage"] = "MOFU"
        data["carousels"][0]["slides"][0]["body"] = "x" * 361
        with self.assertRaises(ValueError):
            studio.validate_output(data, brief)

    def test_local_http_security_and_generation(self):
        server = studio.ThreadingHTTPServer(("127.0.0.1", 0), studio.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(base + "/api/brand") as response:
                token = json.load(response)["token"]
            request = Request(base + "/api/generate", data=json.dumps(self.brief()).encode(), headers={"X-Studio-Token": token})
            with urlopen(request) as response:
                self.assertEqual(len(json.load(response)["carousels"]), 3)
            for request in [Request(base + "/api/generate", data=b"{}"), Request(base + "/api/brand", headers={"Host": "evil.example"}), Request(base + "/.env")]:
                with self.assertRaises(HTTPError) as error:
                    urlopen(request)
                self.assertIn(error.exception.code, (403, 404))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
