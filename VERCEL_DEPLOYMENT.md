# Vercel deployment

Vercel detects this Django project from `manage.py` and serves it through `config.wsgi.application`.

## Required environment variables

- `DJANGO_SECRET_KEY`: a long, unique production secret.
- `DJANGO_DEBUG`: set to `false`.
- `DJANGO_ALLOWED_HOSTS`: the production host, for example `sovaro.vercel.app,.vercel.app`.
- `DJANGO_CSRF_TRUSTED_ORIGINS`: HTTPS origins, for example `https://sovaro.vercel.app,https://*.vercel.app`.
- `DATABASE_URL`: a persistent PostgreSQL connection string. Do not use SQLite in production.
- `GEMINI_API_KEY`: required for the current AI features.
- `GROQ_API_KEY`: recommended fallback when Gemini is unavailable or out of quota.
- `GROQ_MODEL`: optional; defaults to `openai/gpt-oss-120b`.
- `AI_REQUEST_TIMEOUT_MS`: optional; defaults to `20000` milliseconds per model attempt.

## Before production traffic

1. Add a Postgres integration in Vercel so `DATABASE_URL` is available in both Build and Runtime environments.
2. Run `python manage.py migrate --noinput` against that production database.
3. Add the environment variables above for Production and Preview as appropriate.
4. Import the GitHub repository in Vercel. The Django framework and static files are detected automatically.
5. Replace local media storage before relying on brand-image uploads. Vercel function filesystems are not durable; use object storage such as Vercel Blob, S3, R2, or Cloudinary.

Sovaro intentionally fails its Vercel build when `DJANGO_SECRET_KEY` or `DATABASE_URL` is missing. This prevents an apparently successful deployment from using an insecure secret or disposable SQLite database.

## Run production migrations

Do this once after connecting Postgres and again whenever a deployment adds migrations. Keep the connection string in the current PowerShell process only:

```powershell
$env:DATABASE_URL="<pooled production Postgres URL>"
$env:DJANGO_DEBUG="false"
$env:DJANGO_SECRET_KEY="<the same production secret configured in Vercel>"
.\.venv\Scripts\python.exe manage.py migrate --noinput
Remove-Item Env:DATABASE_URL
Remove-Item Env:DJANGO_DEBUG
Remove-Item Env:DJANGO_SECRET_KEY
```

Do not put the production database URL in `.env` or commit it to Git.

## Local production check

```powershell
$env:DJANGO_DEBUG="false"
$env:DJANGO_SECRET_KEY="temporary-local-check-only-change-this-to-a-long-random-value"
$env:DJANGO_ALLOWED_HOSTS="localhost,127.0.0.1,testserver,.vercel.app"
.\.venv\Scripts\python.exe manage.py check --deploy
```
