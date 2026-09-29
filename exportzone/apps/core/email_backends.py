"""Email backends used by EXPORT ZONE."""

from __future__ import annotations

import logging
import sys

from django.core.mail.backends.console import EmailBackend as ConsoleEmailBackend
from django.core.mail.backends.smtp import EmailBackend as SMTPEmailBackend


logger = logging.getLogger(__name__)


class UTF8ConsoleEmailBackend(ConsoleEmailBackend):
    """Console backend that always writes UTF-8.

    Windows consoles default to cp1252, where characters such as the taka sign
    (৳) raise ``UnicodeEncodeError``. Django's stock console backend wrote
    through that codec, which silently killed every order-confirmation and
    status-update email in local development; this subclass writes the raw
    UTF-8 bytes to the underlying buffer instead.
    """

    def write_message(self, message):
        stream = self.stream or sys.stdout
        payload = message.message().as_bytes() + b"\n"

        buffer = getattr(stream, "buffer", None)
        if buffer is not None:
            buffer.write(payload)
            buffer.flush()
            return

        stream.write(payload.decode("utf-8", errors="replace"))
        stream.flush()


class FallbackSMTPEmailBackend(SMTPEmailBackend):
    """SMTP backend that never loses a message when the host blocks SMTP.

    Shared hosting almost always forbids outbound connections to third-party
    SMTP relays: cPanel's own firewall blocks port 587 to any host that is not
    the account's mail server, so a shop that configures ``smtp.gmail.com``
    gets a refused connection the first time an order is placed. Django's stock
    backend then raises, and because both senders in this project deliberately
    swallow exceptions ("the customer must never see a mail error"), the mail
    disappears with nothing in the log.

    This subclass keeps the delivery attempt identical but, when the host
    refuses, prints the full message to the Passenger log instead. The order
    details are then recoverable from cPanel > Errors, and a shop that cannot
    send mail at all degrades to a visible log rather than to silence.
    """

    #: Keep the number of fallback prints bounded: a busy shop would otherwise
    #: fill the account's log quota with copies of the same failure.
    max_fallback_messages = 50

    def __init__(self, *args, **kwargs):
        self.fallback_prints = 0
        super().__init__(*args, **kwargs)

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        try:
            sent = super().send_messages(email_messages)
        except Exception:
            if self.fail_silently:
                return 0
            logger.exception(
                "SMTP delivery to %s:%s failed; the host is very likely blocking "
                "outbound mail. The message is printed to the log instead.",
                self.host,
                self.port,
            )
            return self._print_to_console(email_messages)

        # A non-zero return with a warning is also a failed attempt (for
        # example when the relay accepts the socket but rejects every RCPT).
        if not sent:
            logger.warning(
                "SMTP server %s:%s accepted no message from %s.",
                self.host,
                self.port,
                getattr(self, "username", "") or "(no user)",
            )
        return sent

    def _print_to_console(self, email_messages):
        """Write the messages to the log through the UTF-8 safe console writer."""
        printed = 0
        for message in email_messages:
            if self.fallback_prints >= self.max_fallback_messages:
                logger.error(
                    "Fallback mail printing stopped after %s messages.",
                    self.max_fallback_messages,
                )
                break
            try:
                UTF8ConsoleEmailBackend(stream=sys.stdout, fail_silently=True).send_messages(
                    [message]
                )
            except Exception:
                logger.exception("Could not even print the message to the log.")
                continue
            self.fallback_prints += 1
            printed += 1
        return printed

