# FPL Bhaktapur — Design & Code Change Manual

Operational reference for making changes to https://fplbhaktapur.com — how the
project is laid out, how to safely edit and deploy a change to one page, and
the pitfalls that have already bitten this codebase once (so they don't bite
it again).

## 1. How the project is laid out

Django project `fplsite`, single app `fantasy`, on the VPS at
`/home/rnsainju/fpl_django` (server alias `nirmala-vps`, public site
https://fplbhaktapur.com). Served by Gunicorn (`fpl_django.service`, 3
workers, port 8005) behind nginx.

| Layer | Path |
|---|---|
| View logic | `fantasy/views.py` (one large file — all page views, all data-fetching helpers) |
| Templates | `templates/fantasy/*.html` (one per page) + `templates/admin/*.html` (custom admin) |
| Public CSS | `static/fantasy/css/style.css` (one file, whole site) |
| Admin CSS | `static/fantasy/css/admin_theme.css` |
| JS | `static/fantasy/js/app.js` (one file, whole site) |
| Models | `fantasy/models.py` |
| Admin config | `fantasy/admin.py` (custom `FantasyAdminSite`, mounted at `/control-center/`) |
| Data sync | `fantasy/management/commands/sync_fpl_data.py` |
| URLs | `fantasy/urls.py` |

### Page → template → view map

| URL | Template | View function |
|---|---|---|
| `/` | `home.html` | `home` |
| `/live-gameweek/` | `live_gameweek.html` | `live_gameweek` |
| `/captain-mode/` | `captain_mode.html` | `captain_mode` |
| `/classic-league/` | `classic_league.html` | `classic_league` |
| `/gameweek-winners/` | `gameweek_winners.html` | `gameweek_winners` |
| `/manager-of-the-month/` | `manager_of_the_month.html` | `manager_of_the_month` |
| `/prizes/` | `prizes.html` | `prizes` |
| `/past-seasons/` + `/past-seasons/<id>/` | `past_seasons.html`, `season_detail.html` | `past_seasons`, `season_detail` |
| `/api/league-live-data/` | — (JSON) | `league_live_data` |

Shared partial: `templates/fantasy/_league_banner.html` (site logo + league
name + per-page ad slot), included by captain_mode, classic_league,
gameweek_winners, manager_of_the_month — **not** home or live_gameweek.

## 2. The edit → deploy workflow

This local environment (Windows, Git Bash) has **no local Python** and a
fragile bash shell for anything with embedded `${...}`/multi-line
heredocs. The only reliable workflow is:

1. **Pull** the target file down with `scp` into the scratchpad directory.
2. **Edit** it locally with the `Read` + `Edit`/`Write` tools (never sed/awk
   over SSH for anything non-trivial).
3. **Back up** the current server file first (`cp x.py /tmp/x.py.pre-<change>`
   on the server) before overwriting — cheap insurance, and several past
   sessions have needed to diff back against it.
4. **Push** the edited file back up with `scp`.
5. **Deploy checklist**, in this order, every time:
   ```bash
   .venv/bin/python3 manage.py check
   .venv/bin/python3 manage.py makemigrations fantasy   # only if models.py changed
   .venv/bin/python3 manage.py migrate                  # only if a migration was created
   .venv/bin/python3 manage.py collectstatic --noinput  # only if CSS/JS changed
   rm -f .django_cache/*.djcache                        # always, if views.py/models.py changed
   sudo systemctl restart fpl_django.service
   sleep 2 && systemctl is-active fpl_django.service
   ```
6. **Verify live** — `curl` the affected page/API endpoint and grep for the
   expected content, or drive the Browser tool for anything visual/JS-driven
   (mobile-width checks, computed styles, actual rendered values — not just
   "the HTML contains the string").
7. **Commit and push to git immediately** — see §6. Never leave a deployed
   change uncommitted.

## 3. Shared UI components (reuse these, don't reinvent)

| Component | CSS class(es) | Used on |
|---|---|---|
| Hero hexagon-gradient "winner" card | `.winner-spotlight`, `--sealed` variant for season-long/hidden-until-finished results | Gameweek Winners, Manager of the Month, Captain Mode, Classic League |
| Small pill badges in a wrap list | `.chip-history`, `.chip-history__item`, `--title` variant | Live Tracker (chips used, league achievements, current standing) |
| Manager name + big score merged | `.manager-hero`, `.manager-stats` | Live Tracker |
| Football-pitch player layout | `.pitch`, `.pitch-row`, `.pitch-player`, `.pitch-bench` | Live Tracker (Current Squad) |
| Stat card w/ big number + photo | `.stat-spotlight`, `.stat-spotlight__media` | Home dashboard (Top Stats) |
| Team jersey icon | `.fixture-team__shirt` / `.pitch-player__shirt img` — built from `_shirt_url_from_code(team_code)` | Live Fixtures, pitch view |
| Player headshot w/ jersey fallback | `onerror="window.handlePlayerPhotoError(this, shirtUrl)"` (defined once, top of `app.js`) | Everywhere a player photo is shown |
| Ad banner (logo + league name + per-page ad) | `_league_banner.html` include | Captain Mode, Classic League, Gameweek Winners, Manager of the Month |

Brand palette (both public site and admin): deep purple `#37003c`
(`--brand`), signature green `#00ff87` (`--brand-bright`) — green is
**only** ever a background with dark text (`#04231a`), never text-on-white.

## 4. CSS pitfalls already hit once — don't reintroduce them

- **`overflow-x` alone promotes `overflow-y` too.** Setting
  `overflow-x: auto` on an element browsers *always* also promote
  `overflow-y` from `visible` to `auto` if the two axes differ — this
  cannot be overridden by explicitly setting `overflow-y: visible` on the
  same element. Fix: don't put `overflow-x` on a wide-scoped container;
  scope it to the actual narrow thing that needs to scroll (e.g.
  `.table-wrap`, not `.card`).
- **Specificity**: `a:link, a:visited` (0,1,1) beats a bare `.button`
  class (0,1,0) regardless of source order. Match Django's own convention
  and write `a.button` (element+class) when a link needs its own color.
- **Mobile tables**: base `table { min-width: 520px }` is deliberate (lets
  `.table-wrap { overflow-x: auto }` handle wide tables on tablet/desktop).
  Below `@media (max-width: 620px)`, this flips to `table-layout: fixed;
  min-width: 0` with a **generic** column-width rule assuming
  rank/name/team as columns 1–3. Any table that doesn't follow that shape
  (pure-stat tables like FPL ID History, or name-first tables like Top
  Picks) needs a scoped override keyed by an `id` on the wrapping
  `<section>` — see `#fpl-id-history` / `#top-picks` in `style.css` for the
  pattern. Always also add `white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis;` as a backstop so a too-long header clips
  instead of bleeding into the next cell.
- **Player photo URL**: `_photo_url_from_code()` builds
  `https://resources.premierleague.com/premierleague25/photos/players/110x140/{code}.png`
  (season-scoped bucket, **no** `p` prefix on the code, 110x140 size). An
  earlier version used `.../premierleague/photos/players/250x250/p{code}.png`
  (no season segment, `p`-prefixed, 250x250) which **403s for a lot of
  real current players** (Cherki, Mendy confirmed) — a genuine CDN
  "Access Denied", not a code bug. If photos start going missing again,
  suspect the URL pattern (FPL may rotate the season segment, e.g.
  `premierleague26` next season) before assuming the player has no photo.
  Every `<img>` for a player photo should still pair with
  `onerror="window.handlePlayerPhotoError(this, shirtUrl)"` as a backstop
  (falls back to the team jersey, then an initial-letter badge) — cheap
  insurance for whichever player/season the current URL pattern doesn't
  cover.
- **Breakpoints in use**: `1260px` (font/heading scale-down),
  `1020px` (sidebar becomes a drawer), `620px` (full mobile compaction),
  `380px` (extra-narrow tweaks). Put new mobile rules in the existing
  `620px` block rather than adding a new one.

## 5. Backend patterns

- **Cache wrapper convention**: every expensive fetch is split into
  `_fetch_X(...)` (thin `cache.get_or_set(key, lambda: _fetch_X_live(...),
  timeout=...)`) and `_fetch_X_live(...)` (the real work). Always follow
  this shape for a new data source — never call the FPL API directly from
  a view. `FPL_CACHE_TIMEOUT = 900` (15 min) is the default for
  league-wide leaderboards; per-manager "live" lookups
  (`_fetch_fpl_live_data`, `_fetch_entry_history`) use a short 60s cache
  instead, since they need to feel live but were measured taking 4–5s
  *each* with no caching at all.
- **The `is_current` trap.** FPL's bootstrap-static API does **not** flip
  `is_current` to the next gameweek the moment a gameweek finishes — it
  can stay on the just-finished one for days. Any function that does
  `current_gameweek = current_event.id if current_event else None` and
  then branches on `if current_gameweek:` to decide "fetch this live and
  add it to the stored total" **must** instead check
  `current_event and not current_event.get('finished')` — otherwise a
  finished-but-still-"current" gameweek gets double-counted (once from
  `CaptainGameweekScore`, once from a redundant live re-fetch). This bug
  hit Classic League, Captain Mode, Gameweek Winners, and Manager of the
  Month simultaneously in one incident — grep `is_current` before touching
  any season-aggregating function and check every usage follows this rule.
- **`CaptainGameweekScore`** is the single source of truth for every
  *finished* gameweek's points, backfilled only by `sync_fpl_data`
  (never overwritten for an already-stored (entry, gameweek) pair — a
  manual admin edit there is permanent). The currently in-progress
  gameweek (if any) is always computed live on top, never from this table.
- **Async-load slow sections.** Anything that loops over multiple
  gameweeks/months to compute a per-manager result (e.g. Live Tracker's
  "League Achievements") must **not** run synchronously inside the page
  view — it can take 15–20s+ cold and has already caused a gunicorn
  worker-timeout 500. Add a `section=` branch to `league_live_data`
  instead, render a `data-*-loading` placeholder server-side, and fetch +
  fill it in from `app.js` after the page has already rendered. See the
  `[data-achievements-loading]` block for the reference implementation.
- **`PositiveIntegerField` is often the wrong choice** for anything
  derived from FPL's `total_points` — a player's season total can go
  genuinely negative early on (red card / own goal before enough minutes
  to offset it). Use a plain `IntegerField` for point totals unless you're
  certain the value can never dip below zero.
- **Unique constraints on FPL-sourced rank/position fields are risky** —
  ties happen (`LeagueEntry.rank` hit this exact `IntegerError` on
  `bulk_create` once two managers tied on points).

## 6. Git discipline (non-negotiable)

An external sync process periodically overwrites uncommitted server-side
changes with whatever's committed in git — this has silently wiped
finished, verified features more than once. **Every deployed change must
be committed and pushed to `origin/main` immediately after the deploy
checklist passes**, not batched, not left for later:

```bash
git add -A && git commit -m "<what changed and why>" && git push origin main
```

Before considering *any* task fully done, also run a sync check:

```bash
git fetch origin
git status --short          # must be empty
git log -1 --oneline        # compare to
git log -1 --oneline origin/main   # — must match
```

If the server is ever behind `origin/main` (another session/computer
pushed first), `git pull` then re-run the deploy checklist — never force-push
over it.

## 7. Before calling a change "done"

- [ ] `manage.py check` passes
- [ ] Migrations created + applied if models changed
- [ ] Verified live with `curl` (or Browser tool for anything visual/mobile)
  — not just "no error", the actual rendered value/behavior
- [ ] Checked mobile width (375px) for horizontal overflow on anything
  touched: `document.documentElement.scrollWidth === window.innerWidth`
- [ ] `git status --short` clean, pushed to `origin/main`
- [ ] If touching a season-aggregating number, spot-checked it against a
  known-correct value (e.g. does Classic League's total match Gameweek
  Winners' total for the same manager, same gameweek?)
