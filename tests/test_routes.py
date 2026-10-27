"""
TECHNOVANA — route and page tests.

Every test runs against a temporary copy of the data directory, so the real
`data/registrations.json` is never modified and no test can see another's
records.
"""

import json
import os
import shutil
import tempfile
import unittest

from app import create_app
from config import TestConfig

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class RouteTestCase(unittest.TestCase):
    """Base class that builds an isolated application for each test."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="technovana-test-")

        # Copy the real data files into the temporary directory.
        for name in ("events.json", "settings.json"):
            source = os.path.join(BASE_DIR, "data", name)
            target = os.path.join(self.temp_dir, name)
            shutil.copyfile(source, target)

        self.registrations_path = os.path.join(self.temp_dir, "registrations.json")
        with open(self.registrations_path, "w", encoding="utf-8") as handle:
            json.dump([], handle)

        class TempConfig(TestConfig):
            DATA_DIR = self.temp_dir
            EVENTS_FILE = os.path.join(self.temp_dir, "events.json")
            REGISTRATIONS_FILE = self.registrations_path
            SETTINGS_FILE = os.path.join(self.temp_dir, "settings.json")

        self.app = create_app(TempConfig)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # --- helpers -----------------------------------------------------
    def events_from_disk(self):
        with open(os.path.join(self.temp_dir, "events.json"), encoding="utf-8") as handle:
            return json.load(handle)["events"]

    def write_events(self, events):
        path = os.path.join(self.temp_dir, "events.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"updated": None, "events": events}, handle)

    def registrations_from_disk(self):
        with open(self.registrations_path, encoding="utf-8") as handle:
            return json.load(handle)

    def csrf_token(self, path="/events/prompt-wars/register"):
        """Fetch a page and read the CSRF token out of its form."""
        html = self.client.get(path).get_data(as_text=True)
        marker = 'name="csrf_token" value="'
        start = html.index(marker) + len(marker)
        return html[start:html.index('"', start)]


# ===========================================================================
# Page routes
# ===========================================================================

class PageRouteTests(RouteTestCase):

    def test_homepage_returns_200(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Technovana", response.get_data(as_text=True))

    def test_events_page_returns_200(self):
        response = self.client.get("/events")
        self.assertEqual(response.status_code, 200)

    def test_event_detail_returns_200(self):
        response = self.client.get("/events/prompt-wars")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Prompt Wars", response.get_data(as_text=True))

    def test_every_event_has_a_working_detail_page(self):
        for event in self.events_from_disk():
            response = self.client.get("/events/" + event["slug"])
            self.assertEqual(response.status_code, 200, event["slug"])
            self.assertIn(event["title"], response.get_data(as_text=True))

    def test_about_page_returns_200(self):
        self.assertEqual(self.client.get("/about").status_code, 200)

    def test_schedule_page_returns_200(self):
        self.assertEqual(self.client.get("/schedule").status_code, 200)

    def test_faq_page_returns_200(self):
        self.assertEqual(self.client.get("/faq").status_code, 200)

    def test_register_page_returns_200(self):
        self.assertEqual(
            self.client.get("/events/prompt-wars/register").status_code, 200
        )

    def test_unknown_event_returns_404(self):
        response = self.client.get("/events/not-a-real-event")
        self.assertEqual(response.status_code, 404)
        self.assertIn("404", response.get_data(as_text=True))

    def test_unknown_page_returns_404(self):
        self.assertEqual(self.client.get("/definitely-not-here").status_code, 404)


# ===========================================================================
# Search and filtering
# ===========================================================================

class FilterTests(RouteTestCase):

    def test_search_matches_the_event_title(self):
        response = self.client.get("/events?q=debugging")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Debugging", html)

    def test_search_matches_the_category(self):
        response = self.client.get("/events?q=Gaming")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Free Fire", html)

    def test_category_filter_narrows_the_results(self):
        response = self.client.get("/events?category=Gaming+%26+Esports")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Free Fire", html)
        self.assertIn("BGMI", html)
        self.assertNotIn("Paper Presentation", html)

    def test_search_with_no_match_shows_the_empty_state(self):
        response = self.client.get("/events?q=zzzznotanevent")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("No competitions matched", html)

    def test_sorting_by_title_is_applied(self):
        response = self.client.get("/events?sort=title")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Debugging", html)


# ===========================================================================
# Data integrity
# ===========================================================================

class DataTests(RouteTestCase):

    def test_slugs_are_unique(self):
        slugs = [event["slug"] for event in self.events_from_disk()]
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_slugs_are_url_safe(self):
        for event in self.events_from_disk():
            self.assertRegex(event["slug"], r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

    def test_categories_come_from_the_event_data(self):
        import html as html_module

        events = self.events_from_disk()
        expected = sorted({event["category"] for event in events})
        page = self.client.get("/events").get_data(as_text=True)
        for category in expected:
            # Category names contain "&", which is escaped in the markup.
            self.assertIn(html_module.escape(category), page)

    def test_malformed_events_file_produces_a_controlled_error(self):
        with open(os.path.join(self.temp_dir, "events.json"), "w", encoding="utf-8") as handle:
            handle.write("{ this is not valid json ")

        response = self.client.get("/events")
        self.assertEqual(response.status_code, 500)
        html = response.get_data(as_text=True)
        self.assertIn("Something went wrong", html)
        # The internal traceback must never reach the visitor.
        self.assertNotIn("Traceback", html)

    def test_event_with_an_unconfirmed_date_is_not_in_the_schedule(self):
        events = self.events_from_disk()
        for event in events:
            event["date"] = ""
        self.write_events(events)

        response = self.client.get("/schedule")
        self.assertEqual(response.status_code, 200)
        self.assertIn("has not been published yet", response.get_data(as_text=True))

    def test_confirmed_dates_produce_schedule_entries(self):
        events = self.events_from_disk()
        events[0]["date"] = "2026-03-12"
        events[0]["start_time"] = "10:00"
        events[0]["venue"] = "Main Hall"
        self.write_events(events)

        response = self.client.get("/schedule")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(events[0]["title"], html)
        self.assertIn("12 Mar 2026", html)


# ===========================================================================
# Navigation integrity
# ===========================================================================

class NavigationTests(RouteTestCase):

    def test_every_internal_link_resolves(self):
        import re

        pages = ["/", "/events", "/events/prompt-wars", "/schedule", "/about", "/faq"]

        for page in pages:
            response = self.client.get(page)
            self.assertEqual(response.status_code, 200, page)
            html = response.get_data(as_text=True)

            hrefs = set(re.findall(r'href="(/[^"#?]*)', html))
            for href in hrefs:
                if href.startswith("/static/"):
                    continue
                target = self.client.get(href)
                self.assertNotEqual(
                    target.status_code,
                    404,
                    "Link '{}' on page '{}' returns 404".format(href, page),
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
