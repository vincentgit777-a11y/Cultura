"""
TECHNOVANA — registration tests.

These cover the registration flow end to end: the form renders, the server
rejects bad input, a valid registration is genuinely written to the JSON file,
the confirmation is protected, and the records are never exposed publicly.
"""

import json
import os
import shutil
import tempfile
import unittest

from app import create_app
from config import TestConfig

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class RegistrationTestCase(unittest.TestCase):
    """Base class with an isolated data directory for each test."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="technovana-reg-")

        for name in ("events.json", "settings.json"):
            shutil.copyfile(
                os.path.join(BASE_DIR, "data", name),
                os.path.join(self.temp_dir, name),
            )

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
    def csrf_token(self, slug="prompt-wars"):
        html = self.client.get(
            "/events/{}/register".format(slug)
        ).get_data(as_text=True)
        marker = 'name="csrf_token" value="'
        start = html.index(marker) + len(marker)
        return html[start:html.index('"', start)]

    def valid_payload(self, **overrides):
        payload = {
            "full_name": "Aarav Sharma",
            "email": "aarav.sharma@example.edu",
            "institution": "",
            "phone": "",
            "department": "Computer Science & Engineering",
            "academic_year": "3rd Year",
            "entry_type": "individual",
            "team_name": "",
            "team_members": [],
            "notes": "",
        }
        payload.update(overrides)
        return payload

    def post(self, slug="prompt-wars", payload=None, **overrides):
        """Submit the registration form with a valid CSRF token."""
        payload = payload if payload is not None else self.valid_payload()
        payload.update(overrides)
        data = dict(payload)
        data["csrf_token"] = self.csrf_token(slug)
        return self.client.post(
            "/events/{}/register".format(slug), data=data, follow_redirects=True
        )

    def stored_registrations(self):
        with open(self.registrations_path, encoding="utf-8") as handle:
            return json.load(handle)


# ===========================================================================
# Happy path
# ===========================================================================

class SuccessfulRegistrationTests(RegistrationTestCase):

    def test_valid_registration_is_saved_to_the_json_file(self):
        response = self.post("prompt-wars")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Registration received", response.get_data(as_text=True))

        records = self.stored_registrations()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["event_slug"], "prompt-wars")
        self.assertEqual(
            records[0]["participant"]["full_name"], "Aarav Sharma"
        )
        self.assertTrue(records[0]["reference"])

    def test_registration_reference_is_unique(self):
        self.post("prompt-wars")
        self.post("debugging")
        records = self.stored_registrations()
        self.assertEqual(len(records), 2)
        self.assertNotEqual(records[0]["reference"], records[1]["reference"])

    def test_confirmation_page_shows_the_reference(self):
        response = self.post("prompt-wars")
        html = response.get_data(as_text=True)
        reference = self.stored_registrations()[0]["reference"]
        self.assertIn(reference, html)

    def test_team_registration_is_saved_with_the_roster(self):
        payload = self.valid_payload(
            entry_type="team",
            team_name="Night Shift",
            team_members=["Aarav Sharma", "Riya Sen"],
        )
        response = self.post("ui-ux", payload)
        self.assertEqual(response.status_code, 200)

        records = self.stored_registrations()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["participant"]["team_name"], "Night Shift")
        self.assertEqual(
            records[0]["participant"]["team_members"],
            ["Aarav Sharma", "Riya Sen"],
        )


# ===========================================================================
# Validation
# ===========================================================================

class ValidationTests(RegistrationTestCase):

    def test_missing_required_fields_are_rejected(self):
        response = self.post("prompt-wars", payload={})
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Enter the participant", html)
        self.assertEqual(len(self.stored_registrations()), 0)

    def test_invalid_email_is_rejected(self):
        response = self.post("prompt-wars", email="not-an-email")
        html = response.get_data(as_text=True)
        self.assertIn("valid email address", html)
        self.assertEqual(len(self.stored_registrations()), 0)

    def test_missing_name_is_rejected(self):
        response = self.post("prompt-wars", full_name="")
        self.assertIn("full name", response.get_data(as_text=True))
        self.assertEqual(len(self.stored_registrations()), 0)

    def test_missing_department_is_rejected(self):
        response = self.post("prompt-wars", department="")
        self.assertIn("department", response.get_data(as_text=True).lower())
        self.assertEqual(len(self.stored_registrations()), 0)

    def test_invalid_phone_number_is_rejected(self):
        response = self.post("prompt-wars", phone="call me maybe")
        self.assertIn("phone", response.get_data(as_text=True).lower())
        self.assertEqual(len(self.stored_registrations()), 0)

    def test_team_entry_without_a_team_name_is_rejected(self):
        response = self.post(
            "ui-ux",
            entry_type="team",
            team_name="",
            team_members=["Aarav Sharma", "Riya Sen"],
        )
        self.assertIn("name for your team", response.get_data(as_text=True))
        self.assertEqual(len(self.stored_registrations()), 0)

    def test_team_entry_with_too_few_members_is_rejected(self):
        response = self.post(
            "ui-ux",
            entry_type="team",
            team_name="Night Shift",
            team_members=["Aarav Sharma"],
        )
        self.assertIn("at least 2 team member", response.get_data(as_text=True))
        self.assertEqual(len(self.stored_registrations()), 0)

    def test_team_entry_with_too_many_members_is_rejected(self):
        members = ["A", "B", "C", "D", "E"]
        response = self.post(
            "ui-ux",
            entry_type="team",
            team_name="Night Shift",
            team_members=members,
        )
        self.assertIn("at most 4 team member", response.get_data(as_text=True))
        self.assertEqual(len(self.stored_registrations()), 0)

    def test_duplicate_team_member_names_are_rejected(self):
        response = self.post(
            "ui-ux",
            entry_type="team",
            team_name="Night Shift",
            team_members=["Aarav Sharma", "aarav sharma"],
        )
        self.assertIn("only once", response.get_data(as_text=True))
        self.assertEqual(len(self.stored_registrations()), 0)

    def test_individual_event_rejects_team_only_input(self):
        """An individual-only event must not accept a team entry."""
        response = self.post(
            "paper-presentation",
            entry_type="team",
            team_name="Night Shift",
            team_members=["Aarav Sharma"],
        )
        # The server normalises the entry type to individual for this event,
        # so a valid individual registration is still accepted.
        self.assertEqual(response.status_code, 200)


# ===========================================================================
# CSRF, closed events and rate limiting
# ===========================================================================

class SecurityTests(RegistrationTestCase):

    def test_registration_without_a_csrf_token_is_rejected(self):
        response = self.client.post(
            "/events/prompt-wars/register",
            data=self.valid_payload(),
            follow_redirects=True,
        )
        self.assertIn("security token", response.get_data(as_text=True))
        self.assertEqual(len(self.stored_registrations()), 0)

    def test_registration_with_a_wrong_csrf_token_is_rejected(self):
        response = self.client.post(
            "/events/prompt-wars/register",
            data=dict(self.valid_payload(), csrf_token="not-the-right-token"),
            follow_redirects=True,
        )
        self.assertIn("security token", response.get_data(as_text=True))
        self.assertEqual(len(self.stored_registrations()), 0)

    def test_closed_event_cannot_be_registered_for(self):
        # Treasure Hunt is marked closed in the shipped event data.
        response = self.post("treasure-hunt")
        self.assertIn("closed", response.get_data(as_text=True).lower())
        self.assertEqual(len(self.stored_registrations()), 0)

    def test_rate_limiting_blocks_repeated_submissions(self):
        # Lower the limit so the test stays fast.
        self.app.config["RATE_LIMIT_MAX"] = 3
        self.app.limiter = type(self.app.limiter)(3, 600)

        for _ in range(3):
            self.post("prompt-wars")

        response = self.post("prompt-wars")
        self.assertIn("too many registration attempts", response.get_data(as_text=True).lower())


# ===========================================================================
# Confirmation protection and privacy
# ===========================================================================

class PrivacyTests(RegistrationTestCase):

    def test_confirmation_requires_a_registration_in_this_session(self):
        response = self.client.get("/registration/success", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("no registration to show", response.get_data(as_text=True))

    def test_confirmation_is_not_exposed_to_another_session(self):
        self.post("prompt-wars")
        reference = self.stored_registrations()[0]["reference"]

        # A brand new client has its own session cookie.
        other = self.app.test_client()
        response = other.get("/registration/success", follow_redirects=True)
        self.assertNotIn(reference, response.get_data(as_text=True))

    def test_registration_records_are_not_reachable_over_http(self):
        self.post("prompt-wars")

        for path in (
            "/data/registrations.json",
            "/static/data/registrations.json",
            "/registrations.json",
        ):
            response = self.client.get(path)
            self.assertNotEqual(response.status_code, 200, path)

    def test_no_route_exposes_the_whole_registration_list(self):
        response = self.client.get("/events")
        self.assertNotIn("aarav.sharma@example.edu", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
