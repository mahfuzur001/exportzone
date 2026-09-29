"""``manage.py test_email`` - prove that the shop can really send mail.

Configuring SMTP on a shared host is guesswork: the credentials look right,
the site loads, and the mail only fails later, silently, on the first real
order. This command separates the three questions that matter:

    1. is the configuration complete and self-consistent?
    2. can this server open a TCP connection to the SMTP host at all?
       (shared hosts usually block outbound port 587 - the usual real cause)
    3. does the relay accept the login and the message?

Each check reports its own verdict, so the answer is a specific fix rather
than a stack trace. Run it on the server, not on your computer: the firewall
that blocks the mail is the server's, not yours.
"""

from __future__ import annotations

import smtplib
import socket

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand, CommandError

CONSOLE_BACKENDS = {
    "django.core.mail.backends.console.EmailBackend",
    "apps.core.email_backends.UTF8ConsoleEmailBackend",
    "django.core.mail.backends.locmem.EmailBackend",
}


class Command(BaseCommand):
    help = "Send a test email and report exactly why it would fail."

    def add_arguments(self, parser):
        parser.add_argument(
            "recipient",
            nargs="?",
            default="",
            help="Where to send it. Defaults to EMAIL_HOST_USER.",
        )
        parser.add_argument(
            "--skip-network",
            action="store_true",
            help="Only check the configuration; never touch the network.",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("EXPORT ZONE - email check"))
        self.stdout.write("")

        recipient = options["recipient"] or settings.EMAIL_HOST_USER
        problems = self.check_configuration(recipient)

        if problems:
            self.stdout.write("")
            for problem in problems:
                self.stdout.write(self.style.ERROR(f"  FAIL  {problem}"))
            self.stdout.write("")
            self.stdout.write("Fix the lines above in .env, then run this again.")
            raise CommandError("Email is not configured correctly.")

        if options["skip_network"]:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("Configuration OK (network skipped)."))
            return

        self.check_network()
        self.send_test(recipient)

    # -- step 1: configuration -------------------------------------------------

    def check_configuration(self, recipient):
        problems = []
        backend = settings.EMAIL_BACKEND
        is_console = backend in CONSOLE_BACKENDS

        self.stdout.write(f"  EMAIL_BACKEND   {backend}")
        self.stdout.write(f"  EMAIL_HOST      {settings.EMAIL_HOST or '(empty)'}")
        self.stdout.write(f"  EMAIL_PORT      {settings.EMAIL_PORT}")
        self.stdout.write(f"  EMAIL_HOST_USER {settings.EMAIL_HOST_USER or '(empty)'}")
        self.stdout.write(
            f"  PASSWORD        {'*' * 8 if settings.EMAIL_HOST_PASSWORD else '(empty)'}"
        )
        self.stdout.write(f"  TLS             {settings.EMAIL_USE_TLS}")
        self.stdout.write(f"  TIMEOUT         {settings.EMAIL_TIMEOUT}s")
        self.stdout.write(f"  FROM            {settings.DEFAULT_FROM_EMAIL}")
        self.stdout.write(f"  SITE_URL        {settings.SITE_URL}")
        self.stdout.write(f"  TO              {recipient or '(empty)'}")

        if is_console:
            problems.append(
                "EMAIL_BACKEND is the console backend: messages are only printed, "
                "never delivered. Set EMAIL_BACKEND=django.core.mail.backends.smtp."
                "EmailBackend in .env."
            )
            return problems

        if not settings.EMAIL_HOST:
            problems.append("EMAIL_HOST is empty.")
        if not settings.EMAIL_HOST_USER:
            problems.append("EMAIL_HOST_USER is empty.")
        if not settings.EMAIL_HOST_PASSWORD:
            problems.append("EMAIL_HOST_PASSWORD is empty.")
        if not settings.EMAIL_TIMEOUT:
            problems.append(
                "EMAIL_TIMEOUT is 0, so a blocked connection would hang the request."
            )
        if not recipient:
            problems.append(
                "No recipient: pass one on the command line, or set EMAIL_HOST_USER."
            )

        if settings.DEFAULT_FROM_EMAIL and "@" in settings.DEFAULT_FROM_EMAIL:
            from_address = settings.DEFAULT_FROM_EMAIL.split("<")[-1].rstrip("> ")
            if settings.EMAIL_HOST_USER and from_address != settings.EMAIL_HOST_USER:
                self.stdout.write(
                    self.style.WARNING(
                        f"  NOTE    FROM address {from_address} differs from "
                        f"EMAIL_HOST_USER {settings.EMAIL_HOST_USER}. Some relays "
                        "(Gmail) reject that."
                    )
                )

        return problems

    # -- step 2: can we reach the relay at all? --------------------------------

    def check_network(self):
        host, port = settings.EMAIL_HOST, settings.EMAIL_PORT
        self.stdout.write("")
        self.stdout.write(f"  Connecting to {host}:{port} ...")
        try:
            with socket.create_connection((host, port), timeout=settings.EMAIL_TIMEOUT):
                pass
        except OSError as error:
            self.stdout.write(self.style.ERROR(f"  FAIL  cannot reach {host}:{port}"))
            self.stdout.write("")
            self.stdout.write(
                f"  {error}\n"
                "  This is the usual shared-hosting block: cPanel refuses outbound\n"
                "  SMTP to any relay that is not this account's own mail server.\n"
                "  The site keeps working - FallbackSMTPEmailBackend prints the\n"
                "  message to the Passenger log (cPanel > Errors) - but no customer\n"
                "  mail is delivered.\n\n"
                "  Ways out, cheapest first:\n"
                "    1. Use this account's own mailbox (no firewall rule applies).\n"
                "       In cPanel > Email Accounts create one, for example\n"
                "       orders@YOURDOMAIN, then set in .env:\n"
                "         EMAIL_HOST=mail.YOURDOMAIN\n"
                "         EMAIL_PORT=587   EMAIL_USE_TLS=True\n"
                "         EMAIL_HOST_USER=orders@YOURDOMAIN\n"
                "         EMAIL_HOST_PASSWORD=that mailbox's password\n"
                "    2. Ask the host to unblock port 587, or to allow smtp.gmail.com.\n"
                "    3. Keep the console fallback: no customer mail, but staff see\n"
                "       every message in cPanel > Errors."
            )
            raise CommandError("Outbound SMTP is blocked on this server.")

        self.stdout.write(self.style.SUCCESS(f"  OK    {host}:{port} is reachable"))

    # -- step 3: log in and send ----------------------------------------------

    def send_test(self, recipient):
        self.stdout.write("")
        self.stdout.write(f"  Logging in as {settings.EMAIL_HOST_USER} ...")
        try:
            message = EmailMultiAlternatives(
                subject="EXPORT ZONE - test email",
                body=(
                    "This message proves the shop can send mail.\n\n"
                    f"Site: {settings.SITE_URL}\n"
                    "Sent by manage.py test_email\n"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[recipient],
            )
            message.send(fail_silently=False)
        except smtplib.SMTPAuthenticationError:
            self.stdout.write(self.style.ERROR("  FAIL  the relay rejected the login"))
            self.stdout.write(
                "\n  The password is wrong, or it is an account password where an\n"
                "  app password is required. Google requires a 16-character app\n"
                "  password (Google Account > Security > 2-Step Verification >\n"
                "  App passwords) with the spaces removed."
            )
            raise CommandError("SMTP authentication failed.")
        except smtplib.SMTPRecipientsRefused:
            self.stdout.write(self.style.ERROR("  FAIL  the relay refused the recipient"))
            self.stdout.write(
                f"\n  {recipient} is unknown to {settings.EMAIL_HOST}. For Gmail the\n"
                "  address must exist and be verified."
            )
            raise CommandError("The recipient was refused.")
        except (smtplib.SMTPException, OSError) as error:
            self.stdout.write(self.style.ERROR(f"  FAIL  {type(error).__name__}: {error}"))
            raise CommandError("The SMTP conversation failed.")

        self.stdout.write(
            self.style.SUCCESS(f"  OK    message accepted for {recipient}")
        )
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Mail works. Check the inbox AND the spam folder of {recipient}."
            )
        )
