# Developer Setup

## 1. Backend Setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

Activating is a convenience, not a requirement. `backend/manage.py` and every
`ml_model/` entry point re-launch themselves under `backend/venv` when the
interpreter running them has no dependencies, so `python3 backend/manage.py
runserver` works from a plain shell, from any directory. The venv is found
relative to the script, so this holds for anyone who cloned the repo -- no
hardcoded path. Create it first: with no `backend/venv` on disk the scripts
fall through to their normal import error.

The songs come from the therapist-approved collection in the database (tables
`emotions`, `songs`, `emotion_songs`), seeded from `docs/music.md` by migration
`api/0008_seed_therapist_songs` -- `migrate` is all it needs; no Spotify call
picks songs. To change the collection, add a new data migration (a migration
must replay the same data forever, so don't edit the seed one).

Backend base URL:

- local machine: `http://127.0.0.1:8000/api`
- Android emulator: `http://10.0.2.2:8000/api`

### Running the backend in Docker

Instead of the venv, the backend can run in a container (Docker Engine with the
Compose plugin; on Ubuntu see https://docs.docker.com/engine/install/ubuntu/).
From the repository root, with `.env` in place:

```bash
docker compose up --build -d      # serves http://127.0.0.1:8000, same URLs as above
docker compose logs -f backend
docker compose exec backend python manage.py createsuperuser
docker compose down               # stops it; the database volumes are kept
```

Docker runs three services: the backend, **MySQL 8.4** (`db`) and **phpMyAdmin**.
Before the first `up`, add the MySQL credentials to `.env` (choose your own
password; it is fixed when the MySQL volume is first created):

```
MYSQL_DATABASE=emotune
MYSQL_USER=emotune
MYSQL_PASSWORD=<a strong password>
```

There is no root password to set: MySQL generates a random one at first start
(shown once in `docker compose logs db` as `GENERATED ROOT PASSWORD`). Nothing
in the project needs it.

- **phpMyAdmin:** http://127.0.0.1:8081. Log in with `MYSQL_USER` /
  `MYSQL_PASSWORD`. It is bound to localhost only.
- MySQL itself listens on `127.0.0.1:3307` (localhost only) for host tools and
  for running the tests against MySQL from the venv:
  `DJANGO_DB_ENGINE=mysql MYSQL_HOST=127.0.0.1 MYSQL_PORT=3307 MYSQL_USER=... MYSQL_PASSWORD=... python manage.py test`.
  Without `DJANGO_DB_ENGINE=mysql` the venv and the tests use SQLite as before.
- Memory is capped for this laptop: a 128 MB InnoDB buffer pool, no
  performance_schema, a 512 MB container limit.

What differs from the venv setup:

- It serves with gunicorn (one worker, four threads, since each worker loads its
  own copy of the emotion models) and WhiteNoise for the admin's static files.
- The database is MySQL in the `emotune-mysql` volume, not `backend/db.sqlite3`.
  Migrations run on every start. Uploaded profile pictures stay in the
  `emotune-data` volume, which also keeps the pre-MySQL SQLite database
  (`/data/db.sqlite3`) as a backup. To copy data from a SQLite database into
  MySQL, dump it with `manage.py dumpdata --natural-foreign --natural-primary
  --exclude contenttypes --exclude auth.permission` and load it with
  `manage.py loaddata` against the MySQL settings.
- The models are not in the image. `backend/ml/models` is mounted read-only,
  so `ML_MODEL_PATH` must be relative (`ml/models/...`) or point under
  `/app/backend/ml/models`. The host's Hugging Face cache is mounted for the
  GoEmotions fallback (override with `HF_CACHE_DIR`).
- Set `EMOTUNE_PORT=8001` if a local `runserver` already holds port 8000.

## 2. Flutter Setup

```bash
cd flutter_app
flutter pub get
flutter run
```

Use `--dart-define=API_BASE_URL=...` when the default backend host is not correct.

Examples:

```bash
flutter run --dart-define=API_BASE_URL=http://127.0.0.1:8000/api
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000/api
flutter run --dart-define=API_BASE_URL=http://192.168.1.5:8000/api
```

For a physical Android phone connected over USB:

```bash
adb reverse tcp:8000 tcp:8000
```

## 3. Environment Variables

Copy the root `.env.example` to `.env` and fill in real values.

Required:

- `DJANGO_SECRET_KEY`
- `SPOTIFY_CLIENT_ID`
- `SPOTIFY_CLIENT_SECRET`

Recommended:

- `DJANGO_ALLOWED_HOSTS`
- `SPOTIFY_REDIRECT_URI`
- `SPOTIFY_APP_REMOTE_REDIRECT_URI`
- `EMOTION_HIGH_CONFIDENCE_THRESHOLD`
- `EMOTION_MEDIUM_CONFIDENCE_THRESHOLD`
- `EMOTION_MIN_MARGIN_THRESHOLD`

## 4. Spotify Configuration

In Spotify Developer Dashboard:

1. Open your Spotify app settings.
2. Register the redirect URI used by Django:
   `http://127.0.0.1:8000/api/spotify/callback/`
3. Register the Android App Remote redirect URI:
   `emotune://spotify-auth-callback`
4. If the app is in Development Mode, add every tester Spotify account to the dashboard allowlist.
5. Register the SHA-1 fingerprint of every signing key you build with -- see
   [Release Signing](#8-release-signing).

Notes:

- `0.0.0.0` is fine for `runserver`, but not as a Spotify redirect URI.
- The browser OAuth account, the phone Spotify app account, and the dashboard allowlisted account should all be the same account.

## 5. Emotion Model Workflow

Dataset inspection and cleaning:

```bash
cd ml_model
python inspect_dataset.py
```

Baseline model training:

```bash
cd ml_model
python train_baseline.py
```

BERT training:

```bash
cd ml_model
python train_bert.py
```

Artifacts:

- `ml_model/artifacts/data_quality_report.json`
- `ml_model/artifacts/baseline_results.json`
- `backend/ml/models/bert_emotion_model/`

## 6. Emotion Prediction Behavior

The runtime classifier now uses confidence bands:

- high confidence: trust the BERT prediction
- medium confidence: keep the BERT result but expose top emotion alternatives
- low confidence: use deterministic keyword fallback

The `/api/analyze/` response now includes:

- `top_emotions`
- `prediction_source`
- `prediction_strategy`
- `confidence_band`
- `prediction_fallback_used`
- `prediction_fallback_reason`
- `needs_review`

## 7. API Examples

### Analyze Emotion

Request:

```http
POST /api/analyze/
Content-Type: application/json
Authorization: Bearer <jwt>
```

```json
{
  "text": "I feel peaceful after a long walk."
}
```

Response:

```json
{
  "emotion": "calm",
  "confidence": 71.2,
  "top_emotions": [
    {"emotion": "calm", "confidence": 71.2},
    {"emotion": "mixed", "confidence": 14.8}
  ],
  "prediction_source": "bert",
  "prediction_strategy": "bert_high_confidence",
  "confidence_band": "high",
  "prediction_fallback_used": false,
  "needs_review": false,
  "tracks": [
    {"song_id": 41, "position": 1, "name": "...", "artist": "...",
     "uri": "spotify:track:...", "playable": true}
  ],
  "total": 10,
  "tracks_source": "therapist_list"
}
```

`tracks` is every active approved song for the emotion, in the therapist's
order. A song with no stored Spotify match has `"playable": false`, `"uri":
null` and a Spotify search link in `spotify_url`.

### Spotify Failures

When Spotify blocks or rejects a playback or auth request, the endpoint returns
structured error details. The song list itself never depends on Spotify.

Example:

```json
{
  "error": "Spotify playback failed.",
  "spotify": {
    "status_code": 403,
    "reason": "developer_allowlist_required",
    "message": "Check settings on https://developer.spotify.com/dashboard, the user may not be registered.",
    "recommended_action": "Spotify blocked this account because the app is still in Development Mode. Add the exact Spotify account to the Spotify Developer Dashboard user allowlist, then reconnect Spotify in EmoTune."
  }
}
```

## 8. Release Signing

Release builds are signed with a keystore that lives outside version control.
The Android SDK's debug keystore is a well-known shared key, so anything signed
with it can be impersonated by anyone; `flutter build apk --release` now refuses
to run rather than fall back to it.

`android/key.properties` and the `.jks` file it names are git-ignored. **Back
both up somewhere outside the repo.** If the keystore is lost, no future build
can update an app installed from the old one -- Android treats a differently
signed APK as a different app.

To create the keystore on a fresh machine:

```bash
cd flutter_app/android
keytool -genkeypair -v -keystore emotune-release.jks \
  -keyalg RSA -keysize 4096 -validity 10000 -alias emotune
```

Then write `flutter_app/android/key.properties`:

```properties
storePassword=<the store password you chose>
keyPassword=<the key password you chose>
keyAlias=emotune
storeFile=emotune-release.jks
```

Debug builds are unaffected and need none of this.

### Spotify and the signing fingerprint

Spotify's Android App Remote SDK authorises a client by package name **plus the
SHA-1 fingerprint of the signing key**, so a release build signed with the new
keystore is a different client to Spotify than a debug build. Register both
fingerprints in the Spotify Developer Dashboard, or App Remote will fail to
connect on release builds while working fine in debug.

Print a fingerprint with:

```bash
# release key
keytool -list -v -keystore flutter_app/android/emotune-release.jks -alias emotune
# debug key
keytool -list -v -keystore ~/.android/debug.keystore -alias androiddebugkey -storepass android
```

## 9. Security Checklist

- keep `.env` local only
- rotate leaked credentials if they were ever committed
- never document real passwords in README or setup guides
- use separate Spotify apps or secrets for production if the project gets deployed
- keep the release keystore and `key.properties` out of the repo and backed up
- set `DJANGO_DEBUG=false` in any deployment; it turns on HTTPS redirects,
  HSTS, secure cookies, and closes CORS by default
- replace the placeholder `DJANGO_SECRET_KEY` before deploying

## 10. Troubleshooting

- `Cannot reach the backend`: verify Django is running on port `8000`
- `developer_allowlist_required`: add the Spotify account to the app allowlist and reconnect
- `token_invalid`: reconnect Spotify in the app
- `prediction_strategy=keyword_fallback`: the BERT model confidence was too low or the saved model was missing
