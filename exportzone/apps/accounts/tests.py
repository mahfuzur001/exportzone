from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.auth.models import Permission
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import Address


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AuthenticationTests(TestCase):
    password = "A-strong-passphrase-42"

    def create_user(self, **overrides):
        data = {
            "email": "member@example.com",
            "phone": "01712345678",
            "full_name": "Member Example",
            "password": self.password,
            "is_active": True,
        }
        data.update(overrides)
        return get_user_model().objects.create_user(**data)

    def registration_data(self, **overrides):
        data = {
            "full_name": "New Member",
            "email": "new@example.com",
            "phone": "01812345678",
            "password1": self.password,
            "password2": self.password,
            "agree_to_terms": "on",
        }
        data.update(overrides)
        return data

    def test_custom_user_creation_hashes_password(self):
        user = self.create_user()

        self.assertEqual(user.email, "member@example.com")
        self.assertTrue(user.check_password(self.password))
        self.assertNotEqual(user.password, self.password)

    def test_superuser_creation(self):
        user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            phone="01912345678",
            full_name="Admin Example",
            password=self.password,
        )

        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)

    def test_registration_page_loads(self):
        response = self.client.get(reverse("accounts:register"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create your account")

    def test_registration_rejects_missing_terms_and_invalid_phone(self):
        data = self.registration_data(phone="123", agree_to_terms="")
        response = self.client.post(reverse("accounts:register"), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "valid Bangladesh phone number")
        self.assertContains(response, "must accept the terms")

    def test_registration_rejects_duplicate_email(self):
        self.create_user()
        response = self.client.post(
            reverse("accounts:register"),
            self.registration_data(email="MEMBER@example.com"),
        )

        self.assertContains(response, "An account with this email already exists.")

    def test_registration_rejects_duplicate_phone(self):
        self.create_user()
        response = self.client.post(
            reverse("accounts:register"),
            self.registration_data(phone="01712345678"),
        )

        self.assertContains(response, "This phone number is already registered.")

    def test_registration_creates_active_user_and_sends_welcome_email(self):
        response = self.client.post(reverse("accounts:register"), self.registration_data())
        user = get_user_model().objects.get(email="new@example.com")

        self.assertRedirects(response, reverse("accounts:login"))
        self.assertTrue(user.is_active)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["new@example.com"])
        self.assertIn("Account created successfully", message.alternatives[0][0])
        self.assertIn("Welcome to the house, New Member.", message.body)
        self.assertIn("Start shopping:", message.body)
        self.assertIn("/shop/", message.body)
        self.assertNotIn("&mdash;", message.body)

    def test_registration_creates_an_account_that_can_sign_in_immediately(self):
        self.client.post(reverse("accounts:register"), self.registration_data())
        response = self.client.post(
            reverse("accounts:login"),
            {"identifier": "new@example.com", "password": self.password},
        )

        self.assertRedirects(response, reverse("store:home"))
        self.assertIn(SESSION_KEY, self.client.session)

    def test_login_with_email(self):
        user = self.create_user()
        response = self.client.post(
            reverse("accounts:login"),
            {"identifier": user.email, "password": self.password},
        )

        self.assertRedirects(response, reverse("store:home"))
        self.assertEqual(int(self.client.session[SESSION_KEY]), user.pk)

    def test_login_with_phone(self):
        user = self.create_user()
        response = self.client.post(
            reverse("accounts:login"),
            {"identifier": user.phone, "password": self.password},
        )

        self.assertRedirects(response, reverse("store:home"))
        self.assertEqual(int(self.client.session[SESSION_KEY]), user.pk)

    def test_staff_login_lands_in_the_operations_console(self):
        staff = self.create_user(
            email="staff@example.com", phone="01711000000", is_staff=True
        )
        response = self.client.post(
            reverse("accounts:login"),
            {"identifier": staff.email, "password": self.password},
        )

        self.assertRedirects(response, reverse("admin_dashboard:dashboard"))

    def test_superuser_login_lands_in_the_operations_console(self):
        superuser = self.create_user(
            email="superuser@example.com",
            phone="01799000000",
            is_staff=True,
            is_superuser=True,
        )
        response = self.client.post(
            reverse("accounts:login"),
            {"identifier": superuser.email, "password": self.password},
        )

        self.assertRedirects(response, reverse("admin_dashboard:dashboard"))

    def test_explicit_next_url_still_wins_for_staff(self):
        staff = self.create_user(
            email="staff@example.com", phone="01711000000", is_staff=True
        )
        response = self.client.post(
            f"{reverse('accounts:login')}?next={reverse('cart:detail')}",
            {"identifier": staff.email, "password": self.password},
        )

        self.assertRedirects(response, reverse("cart:detail"))

    def test_invalid_login_is_rejected(self):
        self.create_user()
        response = self.client.post(
            reverse("accounts:login"),
            {"identifier": "member@example.com", "password": "wrong-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid email/phone or password.")
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_deactivated_user_cannot_log_in(self):
        user = self.create_user(is_active=False)
        response = self.client.post(
            reverse("accounts:login"),
            {"identifier": user.email, "password": self.password},
        )

        self.assertContains(response, "Invalid email/phone or password.")
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_logout_requires_post_and_ends_session(self):
        user = self.create_user()
        self.client.force_login(user)

        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        response = self.client.post(reverse("accounts:logout"))

        self.assertRedirects(response, reverse("store:home"))
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_remember_me_session_behaviour(self):
        user = self.create_user()
        remembered_client = Client()
        remembered_client.post(
            reverse("accounts:login"),
            {"identifier": user.email, "password": self.password, "remember_me": "on"},
        )
        temporary_client = Client()
        temporary_client.post(
            reverse("accounts:login"),
            {"identifier": user.email, "password": self.password},
        )

        self.assertFalse(remembered_client.session.get_expire_at_browser_close())
        self.assertTrue(temporary_client.session.get_expire_at_browser_close())

    def test_password_reset_page_loads_and_does_not_expose_account_existence(self):
        self.create_user()
        self.assertEqual(self.client.get(reverse("accounts:password_reset")).status_code, 200)
        response = self.client.post(
            reverse("accounts:password_reset"), {"email": "member@example.com"}
        )

        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/reset-password/", mail.outbox[0].body)

    def test_password_reset_confirmation_sets_a_new_password(self):
        user = self.create_user()
        initial_url = reverse(
            "accounts:password_reset_confirm",
            kwargs={
                "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
                "token": default_token_generator.make_token(user),
            },
        )
        redirect_response = self.client.get(initial_url)
        response = self.client.post(
            redirect_response["Location"],
            {"new_password1": "New-strong-passphrase-42", "new_password2": "New-strong-passphrase-42"},
        )
        user.refresh_from_db()

        self.assertRedirects(response, reverse("accounts:password_reset_complete"))
        self.assertTrue(user.check_password("New-strong-passphrase-42"))

    def test_account_page_requires_login(self):
        response = self.client.get(reverse("accounts:account"))

        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('accounts:account')}",
        )

    def test_authenticated_user_can_access_account_page(self):
        user = self.create_user()
        self.client.force_login(user)
        response = self.client.get(reverse("accounts:account"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, user.full_name)
        self.assertContains(response, "Account status")

    def test_login_rejects_an_external_next_url(self):
        user = self.create_user()
        response = self.client.post(
            reverse("accounts:login"),
            {
                "identifier": user.email,
                "password": self.password,
                "next": "https://attacker.example/",
            },
        )

        self.assertRedirects(response, reverse("store:home"))

    def test_staff_user_can_access_custom_user_admin(self):
        user = self.create_user(is_staff=True)
        user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="accounts",
                content_type__model="customuser",
                codename="view_customuser",
            )
        )
        self.client.force_login(user)
        response = self.client.get(reverse("admin:accounts_customuser_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Custom users")


class AddressBookTests(TestCase):
    password = "A-strong-passphrase-42"

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="address@example.com",
            phone="01712345678",
            full_name="Address Member",
            password=self.password,
        )
        self.other = get_user_model().objects.create_user(
            email="other-address@example.com",
            phone="01812345678",
            full_name="Other Member",
            password=self.password,
        )
        self.client.force_login(self.user)

    def address_data(self, **overrides):
        data = {
            "full_name": "Address Member",
            "phone": "01712345678",
            "address": "House 12, Road 3, Dhanmondi",
            "area": "Dhaka",
        }
        data.update(overrides)
        return data

    def test_address_pages_require_login(self):
        self.client.logout()
        for name in (
            "accounts:address_list",
            "accounts:address_add",
            "accounts:change_password",
        ):
            response = self.client.get(reverse(name))
            self.assertRedirects(
                response, f"{reverse('accounts:login')}?next={reverse(name)}"
            )

    def test_first_saved_address_becomes_default(self):
        response = self.client.post(
            reverse("accounts:address_add"), self.address_data()
        )

        self.assertRedirects(response, reverse("accounts:address_list"))
        address = Address.objects.get(user=self.user)
        self.assertTrue(address.is_default)
        self.assertEqual(address.address, "House 12, Road 3, Dhanmondi")

    def test_setting_new_default_unsets_previous(self):
        first = Address.objects.create(user=self.user, **self.address_data())
        second = Address.objects.create(
            user=self.user, **self.address_data(area="Khulna")
        )

        self.client.post(
            reverse("accounts:address_set_default", kwargs={"address_id": first.pk})
        )
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertTrue(first.is_default)
        self.assertFalse(second.is_default)

        self.client.post(
            reverse("accounts:address_set_default", kwargs={"address_id": second.pk})
        )
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)

    def test_address_edit_and_delete_are_owner_scoped(self):
        other_address = Address.objects.create(user=self.other, **self.address_data())

        response = self.client.get(
            reverse("accounts:address_edit", kwargs={"address_id": other_address.pk})
        )
        self.assertEqual(response.status_code, 404)
        self.client.post(
            reverse("accounts:address_delete", kwargs={"address_id": other_address.pk})
        )
        self.assertTrue(Address.objects.filter(pk=other_address.pk).exists())

        own = Address.objects.create(user=self.user, **self.address_data())
        response = self.client.post(
            reverse("accounts:address_edit", kwargs={"address_id": own.pk}),
            self.address_data(area="Chattogram", address="Agrabad, House 5"),
        )
        self.assertRedirects(response, reverse("accounts:address_list"))
        own.refresh_from_db()
        self.assertEqual(own.area, "Chattogram")

        self.client.post(
            reverse("accounts:address_delete", kwargs={"address_id": own.pk})
        )
        self.assertFalse(Address.objects.filter(pk=own.pk).exists())

    def test_invalid_address_is_rejected(self):
        response = self.client.post(
            reverse("accounts:address_add"),
            self.address_data(phone="123", full_name=""),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Address.objects.count(), 0)

    def test_deleting_default_promotes_remaining_address(self):
        default_address = Address.objects.create(
            user=self.user, is_default=True, **self.address_data()
        )
        remaining = Address.objects.create(
            user=self.user, **self.address_data(area="Sylhet")
        )

        self.assertEqual(
            self.client.get(
                reverse(
                    "accounts:address_delete",
                    kwargs={"address_id": default_address.pk},
                )
            ).status_code,
            405,
        )
        self.client.post(
            reverse(
                "accounts:address_delete", kwargs={"address_id": default_address.pk}
            )
        )
        remaining.refresh_from_db()
        self.assertTrue(remaining.is_default)


class ChangePasswordTests(TestCase):
    password = "A-strong-passphrase-42"
    new_password = "Another-strong-passphrase-77"

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="changepw@example.com",
            phone="01912345678",
            full_name="Change Password Member",
            password=self.password,
        )
        self.client.force_login(self.user)

    def test_change_password_page_loads(self):
        response = self.client.get(reverse("accounts:change_password"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Change password")
        self.assertContains(response, "Old password")

    def test_change_password_rejects_wrong_current_password(self):
        response = self.client.post(
            reverse("accounts:change_password"),
            {
                "old_password": "totally-wrong",
                "new_password1": self.new_password,
                "new_password2": self.new_password,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "old password")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.password))

    def test_change_password_updates_and_keeps_session(self):
        response = self.client.post(
            reverse("accounts:change_password"),
            {
                "old_password": self.password,
                "new_password1": self.new_password,
                "new_password2": self.new_password,
            },
        )

        self.assertRedirects(response, reverse("accounts:account"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))
        account_response = self.client.get(reverse("accounts:account"))
        self.assertEqual(account_response.status_code, 200)


class PasswordToggleMarkupTests(TestCase):
    """Every password field must expose the Show/Hide hook that site.js binds to."""

    def assert_toggle_present(self, response, field_id):
        with self.subTest(field_id=field_id):
            self.assertContains(response, f'id="{field_id}"')
            self.assertContains(response, f'data-password-toggle="{field_id}"')

    def test_login_password_toggle_targets_the_password_input(self):
        response = self.client.get(reverse("accounts:login"))

        self.assert_toggle_present(response, "id_password")

    def test_register_password_toggles_target_both_inputs(self):
        response = self.client.get(reverse("accounts:register"))

        self.assert_toggle_present(response, "id_password1")
        self.assert_toggle_present(response, "id_password2")

    def test_change_password_toggles_target_every_password_input(self):
        user = get_user_model().objects.create_user(
            email="toggle@example.com",
            phone="01711111111",
            full_name="Toggle Member",
            password="A-strong-passphrase-42",
        )
        self.client.force_login(user)
        response = self.client.get(reverse("accounts:change_password"))

        for field_id in ("id_old_password", "id_new_password1", "id_new_password2"):
            self.assert_toggle_present(response, field_id)

    def test_password_reset_confirm_toggle_targets_every_password_input(self):
        user = get_user_model().objects.create_user(
            email="reset-toggle@example.com",
            phone="01722222222",
            full_name="Reset Toggle",
            password="A-strong-passphrase-42",
        )
        response = self.client.get(
            reverse(
                "accounts:password_reset_confirm",
                kwargs={
                    "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
                    "token": default_token_generator.make_token(user),
                },
            ),
            follow=True,
        )

        for field_id in ("id_new_password1", "id_new_password2"):
            self.assertContains(response, f'data-password-toggle="{field_id}"')

