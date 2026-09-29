"""Tests for the project-level email backends."""

import io
from unittest import mock

from django.core.mail import EmailMultiAlternatives
from django.core.mail.backends.console import EmailBackend as ConsoleEmailBackend
from django.test import SimpleTestCase

from .email_backends import FallbackSMTPEmailBackend, UTF8ConsoleEmailBackend


class UTF8ConsoleEmailBackendTests(SimpleTestCase):
    """The console backend must survive non-ASCII text on a Windows console."""

    def build_message(self):
        return EmailMultiAlternatives(
            subject="Export Zone — Order Confirmation #EZ-20260924-7930",
            body="Total: ৳1,290.00 · Cash on Delivery",
            from_email="EXPORT ZONE <noreply@example.com>",
            to=["member@example.com"],
        )

    def cp1252_stream(self):
        """A stream that behaves like a Windows console (cp1252, no error handler)."""
        return io.TextIOWrapper(io.BytesIO(), encoding="cp1252")

    def test_utf8_backend_writes_non_ascii_without_raising(self):
        stream = self.cp1252_stream()

        self.assertEqual(
            UTF8ConsoleEmailBackend(stream=stream).send_messages([self.build_message()]),
            1,
        )
        stream.flush()
        written = stream.buffer.getvalue().decode("utf-8")
        self.assertIn("৳1,290.00", written)
        self.assertIn("EZ-20260924-7930", written)

    def test_stock_console_backend_cannot_write_non_ascii(self):
        """Documents the defect the subclass works around."""
        with self.assertRaises(UnicodeEncodeError):
            ConsoleEmailBackend(stream=self.cp1252_stream()).send_messages(
                [self.build_message()]
            )


class FallbackSMTPEmailBackendTests(SimpleTestCase):
    """A blocked SMTP port must not silently swallow the message.

    Both senders in this project return False instead of raising, so a shop on a
    host that blocks outbound mail would show the customer a successful order
    and staff would never learn the mail was lost. The backend therefore prints
    the message to the Passenger log and reports the message as sent.
    """

    def backend(self, **kwargs):
        options = {
            "host": "smtp.example.com",
            "port": 587,
            "username": "shop@example.com",
            "password": "secret",
            "timeout": 1,
            "fail_silently": False,
        }
        options.update(kwargs)
        return FallbackSMTPEmailBackend(**options)

    def message(self, subject="EXPORT ZONE test"):
        return EmailMultiAlternatives(
            subject=subject,
            body="Order EZ-1 total 1290",
            from_email="shop@example.com",
            to=["customer@example.com"],
        )

    def test_a_working_relay_reports_the_count_without_printing(self):
        backend = self.backend()
        with mock.patch.object(
            FallbackSMTPEmailBackend.__bases__[0],
            "send_messages",
            return_value=1,
        ) as parent:
            with mock.patch.object(UTF8ConsoleEmailBackend, "send_messages") as console:
                self.assertEqual(backend.send_messages([self.message()]), 1)
        parent.assert_called_once()
        console.assert_not_called()

    def test_a_refused_connection_falls_back_to_the_log(self):
        backend = self.backend()
        with mock.patch.object(
            FallbackSMTPEmailBackend.__bases__[0],
            "send_messages",
            side_effect=OSError("connection refused"),
        ):
            with mock.patch.object(UTF8ConsoleEmailBackend, "send_messages") as console:
                # Reported as sent, so the caller does not log a false failure.
                self.assertEqual(backend.send_messages([self.message()]), 1)
        console.assert_called_once()

    def test_fail_silently_stays_silent(self):
        backend = self.backend(fail_silently=True)
        with mock.patch.object(
            FallbackSMTPEmailBackend.__bases__[0],
            "send_messages",
            side_effect=OSError("connection refused"),
        ):
            with mock.patch.object(UTF8ConsoleEmailBackend, "send_messages") as console:
                self.assertEqual(backend.send_messages([self.message()]), 0)
        console.assert_not_called()

    def test_the_fallback_is_capped_so_the_log_cannot_be_flooded(self):
        backend = self.backend()
        with mock.patch.object(
            FallbackSMTPEmailBackend.__bases__[0],
            "send_messages",
            side_effect=OSError("connection refused"),
        ):
            with mock.patch.object(UTF8ConsoleEmailBackend, "send_messages") as console:
                sent = backend.send_messages(
                    [self.message(subject=f"Order {i}") for i in range(60)]
                )
        self.assertEqual(sent, 50)
        self.assertEqual(console.call_count, 50)

    def test_no_messages_means_no_connection_attempt(self):
        backend = self.backend()
        with mock.patch.object(
            FallbackSMTPEmailBackend.__bases__[0], "send_messages"
        ) as parent:
            self.assertEqual(backend.send_messages([]), 0)
        parent.assert_not_called()

