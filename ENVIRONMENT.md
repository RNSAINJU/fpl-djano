# Local and production environment

Set DJANGO_SECRET_KEY before running any manage.py command. There is no fallback
key, and DEBUG defaults to false. Environment variables must be supplied by your
shell or service configuration; this app does not automatically load .env files.

For a local WSL shell, generate a key for this session and explicitly enable debug:

```bash
cd /mnt/c/projects/fpl-djano
export DJANGO_SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(64))')"
export DJANGO_DEBUG=true
.venv/bin/python manage.py migrate
.venv/bin/python manage.py test fantasy
.venv/bin/python manage.py runserver
```

For production, persist a private random key in the service environment so it
survives restarts. Set DJANGO_DEBUG=false, DJANGO_ALLOWED_HOSTS to your domain,
and DJANGO_CSRF_TRUSTED_ORIGINS to its HTTPS origin. Configure these before
restarting with the new settings. A missing key now deliberately stops startup.
If production used the old checked-in key, replace it; existing signed sessions
will no longer be valid. Never commit the production key.

Run `manage.py check --deploy` under the production environment to review its
HTTPS/cookie configuration. Local checks do not verify the VPS environment.

Season archives require a finished season, synced gameweek scores, and successful
responses for every standings/winner section. An upstream failure rolls back the
archive, and the admin reports an error so you can retry later.
