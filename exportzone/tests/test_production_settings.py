"""Production-configuration audit.

These tests pin the settings a shared host depends on. They are not about
Django features - each one guards a value that, if it silently reverted, would
only show up as a broken page on the server rather than as a failing test.
"""

from django.conf import settings
from django.test import SimpleTestCase


class UploadLimitTests(SimpleTestCase):
    """The request-body ceiling must not sit below the form's own file limit.

    ProductImageForm rejects anything over 5 MB with a readable message, but
    Django raises RequestDataTooBig for anything over its own (2.5 MB by default)
    DATA_UPLOAD_MAX_MEMORY_SIZE *before* the form runs. The friendly message would
    therefore be unreachable for images between those two limits.
    """

    def test_request_body_limit_matches_the_image_form_limit(self):
        self.assertEqual(
            settings.DATA_UPLOAD_MAX_MEMORY_SIZE,
            5 * 1024 * 1024,
            "Django rejects the request before ProductImageForm can show its own "
            "5 MB message; the two limits must stay in step.",
        )

    def test_field_count_limit_is_not_the_default(self):
        # A large catalogue form carries many fields; Django's default of 1000
        # is tight for bulk editing.
        self.assertGreaterEqual(settings.DATA_UPLOAD_MAX_NUMBER_FIELDS, 2000)

    def test_uploads_are_streamed_to_disk_rather_than_kept_in_memory(self):
        self.assertLessEqual(settings.FILE_UPLOAD_MAX_MEMORY_SIZE, 2 * 1024 * 1024)


class SecurityHeaderTests(SimpleTestCase):
    """Response headers that must be present on a public host."""

    def test_clickjacking_and_sniffing_protections_are_on(self):
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertEqual(settings.X_FRAME_OPTIONS, "DENY")

    def test_referrer_policy_does_not_leak_full_paths(self):
        self.assertIn(settings.SECURE_REFERRER_POLICY, {
            "strict-origin-when-cross-origin",
            "no-referrer",
            "same-origin",
        })

    def test_permissions_policy_is_restrictive(self):
        for feature in ("geolocation", "microphone", "camera"):
            self.assertIn(f"{feature}=()", settings.PERMISSIONS_POLICY)


class PasswordPolicyTests(SimpleTestCase):
    """Accounts are reachable by email OR phone, so weak passwords matter more."""

    def test_all_four_validators_are_enabled(self):
        names = {
            validator["NAME"].rsplit(".", 1)[-1]
            for validator in settings.AUTH_PASSWORD_VALIDATORS
        }

        self.assertEqual(
            names,
            {
                "UserAttributeSimilarityValidator",
                "MinimumLengthValidator",
                "CommonPasswordValidator",
                "NumericPasswordValidator",
            },
        )


class CookieSettingsTests(SimpleTestCase):
    def test_session_cookie_samesite_is_not_none(self):
        self.assertNotEqual(settings.SESSION_COOKIE_SAMESITE, "None")

    def test_csrf_cookie_samesite_is_not_none(self):
        self.assertNotEqual(settings.CSRF_COOKIE_SAMESITE, "None")
