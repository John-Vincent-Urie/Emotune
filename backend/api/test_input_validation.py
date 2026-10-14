"""The analyze input checks: gibberish, non-English, emotion words, off-topic
and unclear text get a prompt instead of a guessed emotion, and the crisis and
concern paths are untouched."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from api.input_validation import (
    CLARIFY_MESSAGES,
    STATUS_GIBBERISH,
    STATUS_NON_ENGLISH,
    STATUS_OFF_TOPIC,
    STATUS_UNCLEAR,
    check_input,
    model_result_is_unclear,
)
from users.models import PromptHistory


def _prediction(emotion='sad', confidence=0.95, margin=0.9, source='bert'):
    return {
        'emotion': emotion, 'confidence': confidence,
        'all_scores': {emotion: confidence},
        'top_emotions': [{'emotion': emotion, 'confidence': confidence}],
        'prediction_source': source, 'prediction_strategy': 'bert_high_confidence',
        'confidence_band': 'high', 'confidence_margin': margin,
        'fallback_used': False, 'fallback_reason': None, 'needs_review': False,
        'secondary_emotion': None,
    }


class InputRuleTests(SimpleTestCase):
    def assertStatus(self, text, status):
        self.assertEqual(check_input(text).status, status, text)

    def test_keyboard_mash_is_gibberish(self):
        for text in ('dfhskksdnkjskbkjsb', 'asdfghjkl', 'qwe rty uio', 'aaaaaaa', '!!!!', '12345'):
            self.assertStatus(text, STATUS_GIBBERISH)

    def test_a_typo_in_a_real_sentence_is_not_gibberish(self):
        self.assertNotEqual(check_input('im so stresed about school').status, STATUS_GIBBERISH)

    def test_tagalog_and_taglish_are_non_english_not_gibberish(self):
        for text in ('pagod na ako', 'kinikilig', 'malungkot ako', 'I feel so pagod today',
                     'sobrang stressed ako', 'happy ako today'):
            self.assertStatus(text, STATUS_NON_ENGLISH)

    def test_english_with_filipino_names_and_look_alikes_stays_english(self):
        for text in ('I miss Manila so much', 'my lola cooked adobo and I felt so loved',
                     'I may cry after this movie', 'my pa called and I feel happy',
                     'I watched kung fu panda and I feel happy'):
            self.assertNotEqual(check_input(text).status, STATUS_NON_ENGLISH, text)

    def test_a_named_emotion_is_taken_as_said(self):
        cases = {
            'sad': 'sad', "i'm so stressed": 'stressed', 'feeling nostalgic today': 'nostalgic',
            'in love': 'romantic', 'scared': 'fear', 'depressed': 'depressing',
            'surprised': 'surprising', 'motivated': 'motivational', 'sooo happy': 'happy',
            'sadd': 'sad', '😭': 'sad', 'mixed feelings': 'mixed',
        }
        for text, emotion in cases.items():
            check = check_input(text)
            self.assertEqual((check.route, check.emotion), ('emotion_word', emotion), text)

    def test_negated_or_double_emotions_go_to_the_model(self):
        for text in ('not happy', "i'm not sad", 'happy and sad'):
            self.assertIsNone(check_input(text).emotion, text)

    def test_questions_commands_and_facts_are_off_topic(self):
        for text in ('what is 2+2', 'play something for coding', 'the weather is nice',
                     'recommend a movie', 'the sky is blue', 'who won the game last night'):
            self.assertStatus(text, STATUS_OFF_TOPIC)

    def test_a_question_about_own_feelings_is_not_off_topic(self):
        self.assertEqual(check_input('why do I feel so sad lately?').status, 'pass')

    def test_requests_about_an_emotion_are_off_topic(self):
        for text in ('define loneliness', 'write a poem about being angry',
                     'tell me about nostalgia', 'what does it mean to be motivated'):
            self.assertStatus(text, STATUS_OFF_TOPIC)
        # ...but asking about your own feeling is about you.
        for text in ('why do I feel so sad lately?', 'how do i stop feeling sad',
                     'what is wrong with me, I feel so empty'):
            self.assertNotEqual(check_input(text).status, STATUS_OFF_TOPIC, text)

    def test_short_taglish_with_an_english_emotion_word_is_non_english(self):
        for text in ('sad na me', 'stressed sa work', 'excited na', 'bored na me'):
            self.assertStatus(text, STATUS_NON_ENGLISH)
        # Capitalised, NA and SA are English abbreviations.
        self.assertNotEqual(check_input('I live in SA and feel happy').status, STATUS_NON_ENGLISH)

    def test_swapped_letter_typos_of_emotion_words(self):
        for text, emotion in (('lonley', 'lonely'), ('scraed', 'fear'), ('hapyp', 'happy'),
                              ('stressde', 'stressed')):
            self.assertEqual(check_input(text).emotion, emotion, text)

    def test_vague_answers_are_unclear(self):
        for text in ('meh', 'feeling meh', 'idk', 'fine', 'okay i guess', 'same as usual'):
            self.assertStatus(text, STATUS_UNCLEAR)

    def test_model_confidence_gate(self):
        with_affect = check_input('I failed my exam and I feel terrible')
        without_affect = check_input('i drank some water')
        self.assertFalse(model_result_is_unclear(_prediction(confidence=0.6, margin=0.3), with_affect))
        self.assertTrue(model_result_is_unclear(_prediction(confidence=0.35, margin=0.3), with_affect))
        self.assertTrue(model_result_is_unclear(_prediction(confidence=0.6, margin=0.05), with_affect))
        # BERT is overconfident on plain facts, so no emotional words means near-certain only.
        self.assertTrue(model_result_is_unclear(_prediction(confidence=0.95), without_affect))
        self.assertTrue(model_result_is_unclear(_prediction(source='keyword'), with_affect))


class AnalyzeInputStatusTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='inputs', email='inputs@example.com', password='pw12345!',
        )
        self.client.force_authenticate(user=self.user)

    def _analyze(self, text):
        return self.client.post('/api/analyze/', {'text': text}, format='json')

    def _assert_clarify(self, response, status):
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['input_status'], status)
        self.assertEqual(body['clarify_message'], CLARIFY_MESSAGES[status])
        self.assertIsNone(body['input_route'])
        self.assertIsNone(body['emotion'])
        self.assertIsNone(body['emotion_info'])
        self.assertEqual(body['tracks'], [])
        self.assertEqual(body['total'], 0)
        self.assertIsNone(body['history_id'])
        self.assertFalse(PromptHistory.objects.filter(user=self.user).exists())

    @patch('api.views.get_classifier')
    def test_rule_rejections_never_reach_the_model(self, mock_classifier):
        cases = {
            'dfhskksdnkjskbkjsb': STATUS_GIBBERISH,
            'pagod na ako': STATUS_NON_ENGLISH,
            'what is 2+2': STATUS_OFF_TOPIC,
            'feeling meh': STATUS_UNCLEAR,
        }
        for text, status in cases.items():
            self._assert_clarify(self._analyze(text), status)
        mock_classifier.assert_not_called()

    @patch('api.views.get_classifier')
    def test_an_emotion_word_skips_the_model_and_returns_its_songs(self, mock_classifier):
        body = self._analyze('sad').json()

        mock_classifier.assert_not_called()
        self.assertEqual(body['input_status'], 'ok')
        self.assertIsNone(body['clarify_message'])
        self.assertEqual(body['input_route'], 'emotion_word')
        self.assertEqual(body['emotion'], 'sad')
        self.assertEqual(body['prediction_source'], 'emotion_word')
        self.assertEqual(body['confidence'], 100.0)
        self.assertEqual(body['total'], 9)
        self.assertTrue(PromptHistory.objects.filter(user=self.user).exists())

    @patch('api.views.get_classifier')
    def test_an_unsure_model_answer_asks_to_clarify(self, mock_classifier):
        mock_classifier.return_value.predict.return_value = _prediction(confidence=0.3, margin=0.02)

        self._assert_clarify(self._analyze('I feel strange about everything today'), STATUS_UNCLEAR)

    @patch('api.views.get_classifier')
    def test_a_clear_feeling_goes_through_the_model(self, mock_classifier):
        mock_classifier.return_value.predict.return_value = _prediction('sad', 0.92)

        body = self._analyze('I failed my exam and I feel terrible about it').json()

        self.assertEqual(body['input_status'], 'ok')
        self.assertEqual(body['input_route'], 'model')
        self.assertEqual(body['emotion'], 'sad')
        self.assertEqual(body['total'], 9)

    @patch('api.views.get_classifier')
    def test_crisis_language_still_wins_even_in_tagalog(self, mock_classifier):
        for text in ('I want to kill myself', 'gusto ko nang mamatay'):
            body = self._analyze(text).json()
            self.assertEqual(body['risk_level'], 'crisis', text)
            self.assertEqual(body['total'], 0)
            self.assertNotIn('input_status', body)
        mock_classifier.assert_not_called()

    @patch('api.views.get_classifier')
    def test_concern_language_bypasses_the_clarify_rules(self, mock_classifier):
        # "I'm done" has no emotion word and would otherwise be unclear; the
        # concern check-in must still happen, so it goes to the model as before.
        mock_classifier.return_value.predict.return_value = _prediction('depressing', 0.5, 0.05)

        body = self._analyze("i'm done").json()

        mock_classifier.return_value.predict.assert_called_once()
        self.assertEqual(body['input_status'], 'ok')
        self.assertEqual(body['risk_level'], 'concern')
