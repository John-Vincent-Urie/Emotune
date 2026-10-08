"""Crisis-risk text should short-circuit straight to a support message and never
reach the classifier or a music recommendation. See docs/music_therapy_guidelines.md
and api/safety.py for why this exists as a separate concern from emotion -> music
mapping.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from api.models import SupportEvent, SupportResource
from api.management.commands.eval_crisis_detection import SETS, load_items, score
from api.safety import (
    SEVERITY_IMMINENT,
    assess_concern,
    assess_crisis_risk,
    assess_crisis_severity,
    support_subject,
)
from users.models import PromptHistory

User = get_user_model()


class AssessCrisisRiskTests(TestCase):
    def test_flags_direct_self_harm_and_suicide_phrasing(self):
        risky = [
            "I want to kill myself",
            "i just want to end my life tonight",
            "im so suicidal right now",
            "there's no reason to live anymore",
            "I've been cutting myself again",
        ]
        for text in risky:
            with self.subTest(text=text):
                self.assertTrue(assess_crisis_risk(text))

    def test_flags_filipino_and_taglish_phrasing(self):
        risky = [
            "gusto ko na mamatay",
            "papatayin ko na lang sarili ko",
            "ayoko na sa buhay, ang hirap na",
        ]
        for text in risky:
            with self.subTest(text=text):
                self.assertTrue(assess_crisis_risk(text))

    def test_does_not_flag_ordinary_negative_emotion(self):
        safe = [
            "I'm feeling really sad and lonely today",
            "work has been so stressful this week",
            "im so angry at my group mates right now",
            "malungkot lang ako ngayon",
        ]
        for text in safe:
            with self.subTest(text=text):
                self.assertFalse(assess_crisis_risk(text))

    def test_flags_indirect_ideation_found_in_qa(self):
        """Each of these got a normal playlist in QA on 2026-10-04."""
        risky = [
            "Everyone would be better off without me",
            "I took a bunch of pills",
            "There's no point in living anymore",
            "I just want to disappear forever and not wake up",
            "Pagod na ako sa buhay, sana di na ako magising",
            "Wala na akong silbi, mas okay pa kung wala ako",
            "kms fr",
            "unalive myself",
        ]
        for text in risky:
            with self.subTest(text=text):
                self.assertTrue(assess_crisis_risk(text))

    def test_does_not_flag_hyperbole_and_lookalikes(self):
        safe = [
            "This exam is killing me lol",
            "I'm dying of laughter",
            "I could die for some pizza right now",
            "My phone died",
            "try not to wake up the baby",
            "I hope I don't wake up late tomorrow",
            "I'd rather not wake up early on sundays",
            "no point in trying to fix this bug tonight",
            "I took a bunch of photos at the beach",
            "this song is not worth the hype",
        ]
        for text in safe:
            with self.subTest(text=text):
                self.assertFalse(assess_crisis_risk(text))

    def test_flags_paraphrases_qa_found_missed(self):
        """Each of these got a normal playlist in QA on 2026-10-04 (second round)."""
        for text in ["I wanna die", "i want to dieeee", "wanna end it all", "kms",
                     "gusto q n mamatay", "ayoko nang mabuhay"]:
            with self.subTest(text=text):
                self.assertTrue(assess_crisis_risk(text))

    def test_plan_method_or_timeline_is_imminent(self):
        for text in [
            "I'm going to jump off the building tonight",
            "I'll take all my pills tonight",
            "tatalon ako sa tulay mamayang gabi",
            "I bought a rope",
        ]:
            with self.subTest(text=text):
                self.assertEqual(assess_crisis_severity(text), SEVERITY_IMMINENT)

    def test_eval_sets_meet_release_bar(self):
        """Zero misses on clear intent; few false alarms (see eval_crisis_detection)."""
        for name in SETS:
            with self.subTest(set=name):
                result = score(load_items(name))
                self.assertEqual(
                    [i['text'] for i in result['missed'] if i.get('clear')], [],
                )
                self.assertGreaterEqual(result['recall'], 0.95)
                self.assertLessEqual(result['false_positive_rate'], 0.10)

    def test_empty_text_is_never_flagged(self):
        self.assertFalse(assess_crisis_risk(""))
        self.assertFalse(assess_crisis_risk(None))


class CrisisResponseViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='crisis-user',
            email='crisis@example.com',
            password='password123',
        )
        self.client.force_authenticate(user=self.user)

    @patch('api.views.spotify_service.get_recommendations_with_details')
    @patch('api.views.get_classifier')
    def test_analyze_emotion_short_circuits_on_crisis_text(
        self,
        mock_get_classifier,
        mock_get_recommendations_with_details,
    ):
        response = self.client.post(
            '/api/analyze/',
            {'text': 'I just want to kill myself, nothing matters anymore'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['crisis'])
        self.assertEqual(payload['tracks'], [])
        self.assertIn('please contact your local emergency number', payload['ai_response'])
        mock_get_classifier.assert_not_called()
        mock_get_recommendations_with_details.assert_not_called()
        # A crisis prompt is not logged into prompt history as ordinary content.
        self.assertEqual(PromptHistory.objects.count(), 0)

    @override_settings(CRISIS_HOTLINE_TEXT="Call the NCMH Crisis Hotline at 1553.")
    def test_crisis_message_includes_configured_hotline(self):
        response = self.client.post(
            '/api/analyze/',
            {'text': 'i want to end my life'},
            format='json',
        )

        self.assertIn('NCMH Crisis Hotline', response.json()['ai_response'])

    def test_crisis_message_omits_hotline_when_unconfigured(self):
        response = self.client.post(
            '/api/analyze/',
            {'text': 'i want to end my life'},
            format='json',
        )

        # Default test settings leave CRISIS_HOTLINE_TEXT empty -- must not
        # fabricate a number that was never configured/verified.
        self.assertNotIn('1553', response.json()['ai_response'])

    @patch('api.views.spotify_service.get_recommendations_with_details')
    @patch('api.views.get_classifier')
    def test_recommend_by_emotion_short_circuits_on_crisis_text(
        self,
        mock_get_classifier,
        mock_get_recommendations_with_details,
    ):
        response = self.client.post(
            '/api/recommend-by-emotion/',
            {'emotion': 'sad', 'text': 'i want to end my life'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['crisis'])
        self.assertEqual(payload['tracks'], [])
        mock_get_classifier.assert_not_called()
        mock_get_recommendations_with_details.assert_not_called()

    # Patched like its siblings: unpatched, this test fetched a real Spotify
    # token and searched with the dev credentials on every suite run.
    @patch('api.views.spotify_service.get_recommendations_with_details')
    def test_recommend_by_emotion_ignores_template_default_text(self, mock_recs):
        """The templated default ('Play songs for a sad mood.') must never trip
        the crisis check -- only caller-supplied text is inspected."""
        mock_recs.side_effect = RuntimeError('spotify unavailable')
        response = self.client.post(
            '/api/recommend-by-emotion/',
            {'emotion': 'sad'},
            format='json',
        )

        self.assertNotIn('crisis', response.json())


def _prediction(emotion, band):
    return {
        'emotion': emotion,
        'confidence': 0.9 if band == 'high' else 0.5,
        'all_scores': {emotion: 0.9, 'mixed': 0.1},
        'top_emotions': [{'emotion': emotion, 'confidence': 0.9}],
        'prediction_source': 'bert',
        'prediction_strategy': 'bert_high_confidence',
        'confidence_band': band,
        'confidence_margin': 0.8,
        'fallback_used': False,
        'fallback_reason': None,
        'needs_review': False,
        'secondary_emotion': None,
    }


class SupportSubjectTests(TestCase):
    def test_about_someone_else_only_when_nothing_else_is_about_the_user(self):
        cases = {
            'my best friend told me she wants to kill herself, what do I do': 'someone_else',
            'my sister is suicidal and I am scared for her': 'someone_else',
            'gusto niyang magpakamatay, ano gagawin ko': 'someone_else',
            'my friend is suicidal and honestly I want to die too': 'self',
            # QA 2026-10-07: when the crisis rules fire on someone else's
            # danger, the helper needs the "stay with them, call 911" words.
            "my sister just texted me goodbye and says she's going to jump off a bridge tonight": 'someone_else',
            "my friend says she's going to jump off a bridge tonight": 'someone_else',
            'my brother told me he took a bunch of pills': 'someone_else',
            "my dad keeps saying he'd be better off dead": 'someone_else',
            "my mom said she doesn't want to live anymore": 'someone_else',
            "I'm worried my roommate is cutting herself": 'someone_else',
            'sabi ni kuya gusto na niyang mamatay': 'someone_else',
            'sinabi ng kaibigan ko na ayaw na niyang mabuhay': 'someone_else',
            'she broke up with me and i want to kill myself': 'self',
            'my friend told me to kill myself': 'self',
            'gusto ko na mamatay, sabi ko kay ate': 'self',
            'great day with my sister at the beach': 'self',
            'I want to die': 'self',
            "I don't know what to do anymore": 'self',
            '': 'self',
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(support_subject(text), expected)


class ThirdPersonRiskTests(TestCase):
    def test_someone_elses_wish_not_to_live_is_flagged(self):
        """QA 2026-10-07: these got plain music and no contacts."""
        for text in ["my mom said she doesn't want to live anymore", 'sinabi ng kaibigan ko na ayaw na niyang mabuhay']:
            with self.subTest(text=text):
                self.assertTrue(assess_crisis_risk(text))


class AssessConcernTests(TestCase):
    def test_flags_hopeless_phrasing(self):
        concerning = [
            "I don't know what to do anymore",
            "I feel so hopeless about everything",
            "honestly I can't take this anymore",
            "Sometimes living is nonesence",
            "nobody cares if I'm here",
            "hindi ko na kaya, pagod na pagod na ako sa lahat",
            "suko na ako sa thesis na to",
            "wala akong silbi",
        ]
        for text in concerning:
            with self.subTest(text=text):
                self.assertEqual(assess_concern(text), 'phrase')

    def test_does_not_flag_ordinary_negative_emotion(self):
        for text in [
            "I'm feeling really sad and lonely today",
            "work has been so stressful this week",
            "malungkot lang ako ngayon",
            "play something for a rainy night",
        ]:
            with self.subTest(text=text):
                self.assertIsNone(assess_concern(text))

    def test_confident_depressing_prediction_is_a_concern(self):
        self.assertEqual(
            assess_concern("everything feels grey", _prediction('depressing', 'high')),
            'model',
        )

    def test_unconfident_or_other_predictions_are_not(self):
        self.assertIsNone(assess_concern("meh", _prediction('depressing', 'medium')))
        self.assertIsNone(assess_concern("meh", _prediction('sad', 'high')))
        self.assertIsNone(assess_concern("", None))

    def test_crisis_phrases_are_not_downgraded_to_concern_by_views(self):
        # Views check crisis first; this guards that crisis text is still crisis.
        self.assertTrue(assess_crisis_risk("I don't know what to do anymore, I want to die"))


class SeededSupportResourceTests(TestCase):
    def test_owner_verified_contact_survives_a_fresh_database(self):
        # The test DB is built from migrations, so this is what a fresh deploy shows.
        resources = APIClient().get('/api/support-resources/').json()['resources']
        dial = {r['name']: r['phone_uri'] for r in resources}

        # 911 and the NCMH Crisis Hotline (migration 0004) are deactivated by
        # migration 0006 pending replacement contacts (owner decision,
        # 2026-10-08), so only the therapist rows are visible() right now.
        self.assertEqual(list(dial.items()), [
            ('Music Cares Studio (Globe)', 'tel:09173255789'),
            ('Music Cares Studio (Smart)', 'tel:09189296012'),
        ])
        therapist = [r for r in resources if r['name'].startswith('Music Cares')]
        self.assertTrue(all('Not a 24/7' in r['description'] for r in therapist))


class SupportResourceTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        # Start from known rows rather than the seeded contacts.
        SupportResource.objects.all().delete()
        SupportResource.objects.create(
            name='Verified Line', kind='hotline', phone='1234', is_verified=True, sort_order=1,
        )
        SupportResource.objects.create(name='Unverified Line', kind='hotline', phone='9999')
        SupportResource.objects.create(
            name='Retired Line', kind='hotline', phone='5555', is_verified=True, is_active=False,
        )

    def test_public_endpoint_lists_only_verified_active_resources(self):
        # Unauthenticated on purpose: an expired login must not block this.
        response = self.client.get('/api/support-resources/')

        self.assertEqual(response.status_code, 200)
        names = [r['name'] for r in response.json()['resources']]
        self.assertEqual(names, ['Verified Line'])
        self.assertIn('emergency number', response.json()['message'])

    def test_crisis_about_someone_else_gets_words_for_the_helper(self):
        user = User.objects.create_user(username='helper', email='helper@example.com', password='password123')
        self.client.force_authenticate(user=user)

        payload = self.client.post(
            '/api/analyze/', {'text': "my sister says she's going to jump off a bridge tonight"}, format='json',
        ).json()

        self.assertEqual(payload['crisis_severity'], 'imminent')
        self.assertEqual(payload['support_about'], 'someone_else')
        self.assertIn('someone you care about may be in danger', payload['ai_response'])
        self.assertEqual([r['name'] for r in payload['support_resources']], ['Verified Line'])

    def test_crisis_payload_embeds_resources_and_records_event_without_text(self):
        user = User.objects.create_user(username='u', email='u@example.com', password='password123')
        self.client.force_authenticate(user=user)

        payload = self.client.post(
            '/api/analyze/', {'text': 'i want to end my life'}, format='json',
        ).json()

        self.assertEqual(payload['risk_level'], 'crisis')
        self.assertEqual(payload['crisis_severity'], 'crisis')
        self.assertEqual([r['name'] for r in payload['support_resources']], ['Verified Line'])
        event = SupportEvent.objects.get()
        self.assertEqual((event.level, event.trigger, event.source), ('crisis', 'phrase', 'analyze_emotion'))
        stored = {f.name for f in SupportEvent._meta.get_fields()}
        self.assertFalse(stored & {'text', 'user', 'prompt'})


class ConcernResponseViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='concern-user', email='concern@example.com', password='password123',
        )
        self.client.force_authenticate(user=self.user)

    @patch('api.views.spotify_service.get_recommendations_with_details')
    @patch('api.views.get_classifier')
    def test_hopeless_phrase_keeps_music_and_adds_check_in(self, mock_get_classifier, mock_recs):
        mock_get_classifier.return_value.predict.return_value = _prediction('sad', 'high')
        mock_recs.side_effect = RuntimeError('spotify unavailable')

        payload = self.client.post(
            '/api/analyze/', {'text': "I don't know what to do anymore"}, format='json',
        ).json()

        self.assertNotIn('crisis', payload)
        self.assertEqual(payload['emotion'], 'sad')
        self.assertEqual(payload['risk_level'], 'concern')
        self.assertEqual(payload['support_check_in']['trigger'], 'phrase')
        self.assertIn('counselor', payload['support_check_in']['message'])
        mock_get_classifier.assert_called_once()
        self.assertEqual(SupportEvent.objects.get().level, 'concern')

    @patch('api.views.spotify_service.get_recommendations_with_details')
    @patch('api.views.get_classifier')
    def test_confident_depressing_prediction_adds_check_in(self, mock_get_classifier, mock_recs):
        mock_get_classifier.return_value.predict.return_value = _prediction('depressing', 'high')
        mock_recs.side_effect = RuntimeError('spotify unavailable')

        payload = self.client.post(
            '/api/analyze/', {'text': 'everything feels grey lately'}, format='json',
        ).json()

        self.assertEqual(payload['support_check_in']['trigger'], 'model')

    @patch('api.views.spotify_service.get_recommendations_with_details')
    @patch('api.views.get_classifier')
    def test_worry_about_a_friend_gets_the_hotlines_and_its_own_words(self, mock_get_classifier, mock_recs):
        """Owner decision 2026-10-06: third-party disclosures must get the hotline list."""
        SupportResource.objects.create(name='Hotline', kind='hotline', phone='1553', is_verified=True)
        mock_get_classifier.return_value.predict.return_value = _prediction('fear', 'high')
        mock_recs.side_effect = RuntimeError('spotify unavailable')

        payload = self.client.post(
            '/api/analyze/',
            {'text': 'my best friend told me she wants to kill herself, what do I do'},
            format='json',
        ).json()

        self.assertEqual(payload['risk_level'], 'concern')
        self.assertEqual(payload['support_about'], 'someone_else')
        check_in = payload['support_check_in']
        self.assertEqual(check_in['about'], 'someone_else')
        self.assertIn('worried about someone', check_in['message'])
        self.assertIn('tel:1553', [r['phone_uri'] for r in check_in['resources']])

    @patch('api.views.spotify_service.get_recommendations_with_details')
    @patch('api.views.get_classifier')
    def test_own_hopelessness_keeps_self_wording(self, mock_get_classifier, mock_recs):
        mock_get_classifier.return_value.predict.return_value = _prediction('sad', 'high')
        mock_recs.side_effect = RuntimeError('spotify unavailable')

        payload = self.client.post(
            '/api/analyze/', {'text': "I don't know what to do anymore"}, format='json',
        ).json()

        self.assertEqual(payload['support_about'], 'self')
        self.assertEqual(payload['support_check_in']['about'], 'self')
        self.assertTrue(payload['support_check_in']['resources'] is not None)

    @patch('api.views.spotify_service.get_recommendations_with_details')
    @patch('api.views.get_classifier')
    def test_ordinary_text_has_no_risk_fields(self, mock_get_classifier, mock_recs):
        mock_get_classifier.return_value.predict.return_value = _prediction('happy', 'high')
        mock_recs.side_effect = RuntimeError('spotify unavailable')

        payload = self.client.post(
            '/api/analyze/', {'text': 'great day at the beach'}, format='json',
        ).json()

        self.assertNotIn('risk_level', payload)
        self.assertNotIn('support_check_in', payload)
        self.assertFalse(SupportEvent.objects.exists())

    @patch('api.views.spotify_service.get_recommendations_with_details')
    def test_picking_the_depressing_tab_is_not_a_concern(self, mock_recs):
        mock_recs.side_effect = RuntimeError('spotify unavailable')

        payload = self.client.post(
            '/api/recommend-by-emotion/', {'emotion': 'depressing'}, format='json',
        ).json()

        self.assertNotIn('support_check_in', payload)
        self.assertFalse(SupportEvent.objects.exists())
