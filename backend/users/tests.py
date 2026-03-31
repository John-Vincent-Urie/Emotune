from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient


User = get_user_model()


class RegistrationTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_stores_terms_acceptance_and_personalization_preference(self):
        response = self.client.post(
            '/api/users/register/',
            {
                'username': 'Avery',
                'email': 'avery@example.com',
                'password': 'password123',
                'confirm_password': 'password123',
                'accept_terms': True,
                'personalization_opt_in': False,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body['user']['username'], 'Avery')
        self.assertFalse(body['user']['personalization_opt_in'])
        self.assertIsNotNone(body['user']['terms_accepted_at'])

        user = User.objects.get(email='avery@example.com')
        self.assertFalse(user.personalization_opt_in)
        self.assertIsNotNone(user.terms_accepted_at)

    def test_register_requires_terms_acceptance(self):
        response = self.client.post(
            '/api/users/register/',
            {
                'username': 'Jordan',
                'email': 'jordan@example.com',
                'password': 'password123',
                'confirm_password': 'password123',
                'accept_terms': False,
                'personalization_opt_in': True,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('accept_terms', response.json())
        self.assertFalse(User.objects.filter(email='jordan@example.com').exists())
