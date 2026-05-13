# Google OAuth Setup (Gmail + Calendar)

Use this guide to configure Google OAuth for local development and MVP deployment.

## 1) Create Google Cloud project

1. Go to Google Cloud Console.
2. Create a new project (for example: `personal-assistant-mvp`).
3. Select the project before continuing.

## 2) Enable required APIs

Enable these APIs in `APIs & Services > Library`:

- Gmail API
- Google Calendar API

Optional later:
- People API (if you want richer contact info)

## 3) Configure OAuth consent screen

1. Open `APIs & Services > OAuth consent screen`.
2. User type:
   - External (recommended for personal non-Workspace account)
3. Fill app details:
   - App name
   - User support email
   - Developer contact email
4. Add scopes:
   - `.../auth/gmail.readonly`
   - `.../auth/calendar.readonly`
5. Add test users:
   - Add your Google account email here during development.

Notes:
- In testing mode, only test users can authorize.
- You can publish later when needed.

## 4) Create OAuth client credentials

1. Go to `APIs & Services > Credentials`.
2. Click `Create Credentials > OAuth client ID`.
3. Application type: `Web application`.
4. Set name (for example: `local-fastapi-client`).
5. Add authorized redirect URIs:
   - `http://localhost:8000/api/v1/auth/google/callback`
6. Save and copy:
   - Client ID
   - Client Secret

## 5) Local environment values

Set these in your backend `.env`:

```env
GOOGLE_CLIENT_ID=<from-google-console>
GOOGLE_CLIENT_SECRET=<from-google-console>
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback
GOOGLE_SCOPES=https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/calendar.readonly
```

## 6) OAuth route contract reminders

- `POST /api/v1/auth/google/start`
  - Builds auth URL with scopes and state.
- `GET /api/v1/auth/google/callback`
  - Validates state, exchanges code for tokens, stores refresh token.

Persist at least:
- access token
- refresh token
- token expiry
- scope list

## 7) Required implementation safeguards

- Use `state` parameter to prevent CSRF.
- Store tokens encrypted at rest.
- Refresh access token automatically when expired.
- Retry one time after refresh on 401 from Google API.
- Keep scopes read-only for MVP.

## 8) Production redirect URI checklist

When deploying:

- Add production redirect URI in Google Console, for example:
  - `https://api.yourdomain.com/api/v1/auth/google/callback`
- Keep local and production URIs both registered.
- Ensure backend `GOOGLE_REDIRECT_URI` matches environment exactly.

## 9) Common errors and fixes

### `redirect_uri_mismatch`

Cause:
- URI in app does not exactly match authorized URI.

Fix:
- Copy exact callback URL from config to Google Console credential.

### `access_denied`

Cause:
- User canceled auth or app not allowed by consent settings.

Fix:
- Verify test user is added; re-run auth.

### `invalid_scope`

Cause:
- Scope typo or missing API enablement.

Fix:
- Recheck scope strings and ensure Gmail/Calendar APIs are enabled.

### No refresh token returned

Cause:
- Google may not reissue refresh token on repeated consent.

Fix:
- Request offline access and force consent in auth URL parameters during dev.

## 10) MVP verification checklist

- [ ] OAuth start route returns valid Google auth URL.
- [ ] Callback stores tokens successfully.
- [ ] Refresh token exists for user.
- [ ] Gmail sync works with stored credentials.
- [ ] Calendar sync works with stored credentials.
- [ ] Token refresh succeeds after expiry simulation.
