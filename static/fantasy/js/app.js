// Shared onerror handler for player headshots, used from inline `onerror`
// attributes (so it has to live on window). Not every player has a photo
// uploaded on the FPL CDN yet (recent transfers/lesser-known players 403) -
// first try the player's team jersey icon (always available, served from a
// different, reliable FPL asset host), then finally fall back to a plain
// initial-letter badge if even that somehow fails.
window.handlePlayerPhotoError = function handlePlayerPhotoError(img, shirtUrl) {
    if (shirtUrl && img.src !== shirtUrl) {
        img.onerror = () => handlePlayerPhotoError(img, null);
        img.src = shirtUrl;
        img.classList.add('is-shirt-fallback');
        return;
    }
    img.style.display = 'none';
    if (img.nextElementSibling) {
        img.nextElementSibling.style.display = 'grid';
    }
};

// Shared player-photo markup (headshot -> team jersey -> initial letter),
// built once and reused by every dashboard card that shows a player -
// keeps that same 3-step fallback chain consistent everywhere instead of
// each section rebuilding it slightly differently.
window.buildPlayerAvatar = function buildPlayerAvatar(name, photoUrl, shirtUrl, className) {
    const initial = (name || '-').slice(0, 1);
    const fallback = `<span class="${className} ${className}--fallback" style="display:none;">${initial}</span>`;
    if (photoUrl) {
        return `<img class="${className}" src="${photoUrl}" alt="${name}" onerror="window.handlePlayerPhotoError(this, '${shirtUrl || ''}')">${fallback}`;
    }
    if (shirtUrl) {
        return `<img class="${className} is-shirt-fallback" src="${shirtUrl}" alt="${name}" onerror="window.handlePlayerPhotoError(this, '')">${fallback}`;
    }
    return `<span class="${className} ${className}--fallback">${initial}</span>`;
};

// Shared Live Fixtures card markup - the dashboard's default (current
// gameweek) load and its prev/next gameweek pager both need to render the
// exact same card shape.
window.renderLiveFixturesGrid = function renderLiveFixturesGrid(grid, fixtures) {
    if (!fixtures || !fixtures.length) {
        grid.innerHTML = '<article class="live-fixture-card"><p>No live fixture data available right now.</p></article>';
        return;
    }
    grid.innerHTML = fixtures
        .map((fixture) => `
            <article class="live-fixture-card">
                <div class="fixture-teams">
                    <div class="fixture-team">
                        ${fixture.home_team.shirt_url ? `<img class="fixture-team__shirt" src="${fixture.home_team.shirt_url}" alt="${fixture.home_team.short_name} shirt" loading="lazy">` : ''}
                        <strong>${fixture.home_team.short_name}</strong>
                    </div>
                    <span>vs</span>
                    <div class="fixture-team">
                        ${fixture.away_team.shirt_url ? `<img class="fixture-team__shirt" src="${fixture.away_team.shirt_url}" alt="${fixture.away_team.short_name} shirt" loading="lazy">` : ''}
                        <strong>${fixture.away_team.short_name}</strong>
                    </div>
                </div>
                <div class="fixture-status${fixture.status === 'LIVE' ? ' fixture-status--live' : ''}">${fixture.status}</div>
                ${fixture.status === 'Upcoming'
                    ? `<p>${fixture.kickoff_display}</p>`
                    : `<p class="fixture-score">${fixture.home_score || 0} - ${fixture.away_score || 0}</p>`}
            </article>
        `)
        .join('');
};

document.addEventListener('DOMContentLoaded', () => {
    const items = document.querySelectorAll('.reveal');
    items.forEach((item, index) => {
        item.style.animationDelay = `${index * 100}ms`;
    });

    const sidebar = document.getElementById('sidebar');
    const toggle = document.getElementById('sidebar-toggle');
    if (sidebar && toggle) {
        // Keep the sidebar's own scroll position consistent across page
        // navigations - without this, clicking a link partway down the nav
        // list lands you back at the top of the sidebar on the new page.
        try {
            const savedScroll = sessionStorage.getItem('sidebarScrollTop');
            if (savedScroll !== null) {
                sidebar.scrollTop = parseInt(savedScroll, 10) || 0;
            }
        } catch (err) {
            // sessionStorage unavailable (e.g. private browsing) - ignore.
        }

        sidebar.addEventListener('scroll', () => {
            try {
                sessionStorage.setItem('sidebarScrollTop', sidebar.scrollTop);
            } catch (err) {
                // ignore
            }
        }, { passive: true });

        const overlay = document.createElement('div');
        overlay.className = 'sidebar-overlay';
        document.body.appendChild(overlay);

        toggle.setAttribute('aria-expanded', 'false');

        const openSidebar = () => {
            sidebar.classList.add('is-open');
            overlay.classList.add('is-visible');
            toggle.setAttribute('aria-expanded', 'true');
            document.body.classList.add('sidebar-lock');
        };

        const closeSidebar = () => {
            sidebar.classList.remove('is-open');
            overlay.classList.remove('is-visible');
            toggle.setAttribute('aria-expanded', 'false');
            document.body.classList.remove('sidebar-lock');
        };

        toggle.addEventListener('click', () => {
            if (sidebar.classList.contains('is-open')) {
                closeSidebar();
            } else {
                openSidebar();
            }
        });

        overlay.addEventListener('click', closeSidebar);

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && sidebar.classList.contains('is-open')) {
                closeSidebar();
            }
        });

        sidebar.querySelectorAll('a').forEach((link) => {
            link.addEventListener('click', () => {
                try {
                    sessionStorage.setItem('sidebarScrollTop', sidebar.scrollTop);
                } catch (err) {
                    // ignore
                }
                if (window.matchMedia('(max-width: 1020px)').matches) {
                    closeSidebar();
                }
            });
        });

        // If the viewport grows back past the mobile breakpoint (e.g. a
        // rotation or window resize) while the mobile nav is open, close it
        // rather than leaving it stuck open in the now-desktop layout.
        window.addEventListener('resize', () => {
            if (window.innerWidth > 1020 && sidebar.classList.contains('is-open')) {
                closeSidebar();
            }
        });
    }

    const countdown = document.querySelector('.countdown[data-target]');
    if (countdown) {
        const targetAttr = countdown.getAttribute('data-target');
        const targetTime = targetAttr ? new Date(targetAttr).getTime() : 0;

        const update = () => {
            const now = Date.now();
            const remainingMs = Math.max(0, targetTime - now);
            const days = Math.floor(remainingMs / 86400000);
            const hours = Math.floor((remainingMs % 86400000) / 3600000);
            const minutes = Math.floor((remainingMs % 3600000) / 60000);
            const seconds = Math.floor((remainingMs % 60000) / 1000);

            const set = (key, value) => {
                const element = countdown.querySelector(`[data-count="${key}"]`);
                if (element) {
                    element.textContent = String(value).padStart(2, '0');
                }
            };

            set('days', days);
            set('hours', hours);
            set('minutes', minutes);
            set('seconds', seconds);
        };

        update();
        setInterval(update, 1000);
    }

    const leagueMain = document.querySelector('[data-league-page][data-live-endpoint]');
    if (leagueMain) {
        const pageType = leagueMain.getAttribute('data-league-page');
        const endpoint = leagueMain.getAttribute('data-live-endpoint');

        const setSharedMeta = (payload) => {
            const name = document.querySelector('[data-league-name]');
            if (name) {
                name.textContent = payload.league_name || 'FPL League 6232';
            }

            const error = document.querySelector('[data-league-error]');
            if (error) {
                if (payload.league_error) {
                    error.textContent = payload.league_error;
                    error.classList.remove('is-hidden');
                } else {
                    error.textContent = '';
                    error.classList.add('is-hidden');
                }
            }
        };

        const renderClassic = (payload) => {
            const leader = document.querySelector('[data-classic-leader]');
            if (leader) {
                leader.textContent = `Leader ${payload.classic.leader_points} pts`;
            }

            const tbody = document.querySelector('[data-classic-rows]');
            if (!tbody) {
                return;
            }

            const rows = payload.classic.rows || [];
            if (!rows.length) {
                tbody.innerHTML = '<tr><td colspan="5">No league standings available yet.</td></tr>';
                return;
            }

            tbody.innerHTML = rows
                .map((row) => {
                    const formClass = row.form === 'On Fire'
                        ? 'status-pill--fire'
                        : row.form === 'Hot'
                            ? 'status-pill--hot'
                            : row.form === 'Steady'
                                ? 'status-pill--steady'
                                : row.form === 'Cooling'
                                    ? 'status-pill--cooling'
                                    : 'status-pill--cold';
                    return `
                        <tr>
                            <td>#${row.rank}</td>
                            <td>${row.manager_name}</td>
                            <td>${row.team_name}</td>
                            <td>${row.total_points}</td>
                            <td><span class="status-pill ${formClass}">${row.form_emoji} ${row.form}</span></td>
                        </tr>
                    `;
                })
                .join('');
        };

        const renderGameweek = (payload) => {
            const data = payload.gameweek;
            if (!data) {
                return;
            }
            const winner = data.winner;
            const finished = data.selected_gameweek_finished;

            const chip = document.querySelector('[data-gameweek-winner-chip]');
            if (chip) {
                chip.textContent = winner ? `#1 ${winner.manager_name}` : (finished ? 'No entries yet' : 'Still in progress');
            }

            const spotlightLabel = document.querySelector('[data-gameweek-spotlight-label]');
            if (spotlightLabel) {
                spotlightLabel.textContent = data.selected_gameweek
                    ? `Gameweek ${data.selected_gameweek} ${finished ? 'Winner' : 'Highest Scorer'}`
                    : 'Winner';
            }

            const winnerName = document.querySelector('[data-gameweek-winner-name]');
            const winnerTeam = document.querySelector('[data-gameweek-winner-team]');
            const winnerPoints = document.querySelector('[data-gameweek-winner-points]');
            if (winnerName) {
                winnerName.textContent = winner ? winner.manager_name : 'No entries yet';
            }
            if (winnerTeam) {
                winnerTeam.textContent = winner ? (winner.team_name + (finished ? '' : ' · scores still live')) : '-';
            }
            if (winnerPoints) {
                winnerPoints.textContent = winner ? winner.gameweek_points : '0';
            }

            const errorEl = document.querySelector('[data-gameweek-error]');
            if (errorEl) {
                if (data.gameweek_error) {
                    errorEl.textContent = data.gameweek_error;
                    errorEl.classList.remove('is-hidden');
                } else {
                    errorEl.textContent = '';
                    errorEl.classList.add('is-hidden');
                }
            }

            const select = document.getElementById('gameweek-select');
            if (select && data.available_gameweeks && data.available_gameweeks.length) {
                const current = select.value || String(data.selected_gameweek || '');
                select.innerHTML = data.available_gameweeks
                    .map((gw) => `<option value="${gw.value}"${String(gw.value) === current ? ' selected' : ''}>${gw.label}</option>`)
                    .join('');
            }

            if (data.selected_gameweek) {
                const label = `Gameweek ${data.selected_gameweek}`;
                ['[data-gameweek-select-label]', '[data-gameweek-table-label]'].forEach((sel) => {
                    const el = document.querySelector(sel);
                    if (el) {
                        el.textContent = label;
                    }
                });
            }

            const tbody = document.querySelector('[data-gameweek-rows]');
            if (!tbody) {
                return;
            }

            const rows = data.entries || [];
            if (!rows.length) {
                tbody.innerHTML = '<tr><td colspan="5">No entries available yet.</td></tr>';
                return;
            }

            tbody.innerHTML = rows
                .map((row) => `
                    <tr>
                        <td>#${row.rank}</td>
                        <td>${row.manager_name}</td>
                        <td>${row.team_name}</td>
                        <td>${row.gameweek_points}</td>
                        <td>${row.total_points}</td>
                    </tr>
                `)
                .join('');
        };

        const renderMonthly = (payload) => {
            const data = payload.monthly;
            if (!data) {
                return;
            }
            const winner = data.winner;
            const finished = data.selected_month_finished;

            const chip = document.querySelector('[data-monthly-winner-chip]');
            if (chip) {
                chip.textContent = winner ? `#1 ${winner.manager_name}` : (finished ? 'No entries yet' : 'Still in progress');
            }

            const winnerName = document.querySelector('[data-monthly-winner-name]');
            const winnerTeam = document.querySelector('[data-monthly-winner-team]');
            const winnerScore = document.querySelector('[data-monthly-winner-score]');
            if (winnerName) {
                winnerName.textContent = winner ? winner.manager_name : 'No entries yet';
            }
            if (winnerTeam) {
                winnerTeam.textContent = winner ? (winner.team_name + (finished ? '' : ' · scores still live')) : '-';
            }
            if (winnerScore) {
                winnerScore.textContent = winner ? winner.monthly_points : '0';
            }

            const errorEl = document.querySelector('[data-monthly-error]');
            if (errorEl) {
                if (data.monthly_error) {
                    errorEl.textContent = data.monthly_error;
                    errorEl.classList.remove('is-hidden');
                } else {
                    errorEl.textContent = '';
                    errorEl.classList.add('is-hidden');
                }
            }

            const select = document.getElementById('month-select');
            if (select && data.available_months && data.available_months.length) {
                const current = select.value || data.selected_month || '';
                select.innerHTML = data.available_months
                    .map((month) => `<option value="${month.value}"${month.value === current ? ' selected' : ''}>${month.label}</option>`)
                    .join('');
            }

            const monthLabel = data.selected_month_label;
            if (monthLabel) {
                document.querySelectorAll('[data-monthly-month-label], [data-monthly-ranking-label]').forEach((el) => {
                    el.textContent = monthLabel;
                });
                const spotlightLabel = document.querySelector('[data-monthly-spotlight-label]');
                if (spotlightLabel) {
                    spotlightLabel.textContent = `${monthLabel} ${finished ? 'Winner' : 'Highest Scorer'}`;
                }
            }

            const tbody = document.querySelector('[data-monthly-rows]');
            if (!tbody) {
                return;
            }

            const rows = data.rankings || [];
            if (!rows.length) {
                tbody.innerHTML = '<tr><td colspan="5">No rankings available yet.</td></tr>';
                return;
            }

            tbody.innerHTML = rows
                .map((row) => `
                    <tr>
                        <td>#${row.rank}</td>
                        <td>${row.manager_name}</td>
                        <td>${row.team_name}</td>
                        <td>${row.monthly_hits ? `-${row.monthly_hits}` : '0'}</td>
                        <td>${row.monthly_points}</td>
                    </tr>
                `)
                .join('');
        };

        const renderCaptain = (payload) => {
            const data = payload.captain;
            if (!data) {
                return;
            }

            const status = document.querySelector('[data-captain-status]');
            if (status) {
                status.textContent = data.status || 'Season total';
            }

            const errorEl = document.querySelector('[data-captain-error]');
            if (errorEl) {
                if (data.error) {
                    errorEl.textContent = data.error;
                    errorEl.classList.remove('is-hidden');
                } else {
                    errorEl.textContent = '';
                    errorEl.classList.add('is-hidden');
                }
            }

            const tbody = document.querySelector('[data-captain-rows]');
            if (!tbody) {
                return;
            }

            const rows = data.leaderboard || [];
            if (!rows.length) {
                tbody.innerHTML = '<tr><td colspan="5">No captain data available yet.</td></tr>';
                return;
            }

            tbody.innerHTML = rows
                .map((row) => `
                    <tr>
                        <td>#${row.rank}</td>
                        <td>${row.manager_name}</td>
                        <td>${row.team_name}</td>
                        <td>${row.captain_name}</td>
                        <td>${row.captain_points}</td>
                    </tr>
                `)
                .join('');
        };

        const medalFor = (rank) => (rank === 1 ? '🥇' : rank === 2 ? '🥈' : rank === 3 ? '🥉' : `#${rank}`);

        const renderMiniLeaders = (selector, rows, scoreKey, count = 3) => {
            const list = document.querySelector(selector);
            if (!list) {
                return;
            }
            const topRows = (rows || []).slice(0, count);
            if (!topRows.length) {
                list.innerHTML = '<li class="mini-leaders__empty">No data yet</li>';
                return;
            }
            list.innerHTML = topRows
                .map((row) => `
                    <li${row.rank === 1 ? ' class="mini-leaders__item--first"' : ''}>
                        <span class="mini-leaders__rank">${medalFor(row.rank)}</span>
                        <span class="mini-leaders__name">${row.manager_name}</span>
                        <span class="mini-leaders__score">${row[scoreKey]}</span>
                    </li>
                `)
                .join('');
        };

        const renderStatSpotlight = (selector, stat, unitLabel, valueKey) => {
            const container = document.querySelector(selector);
            if (!container) {
                return;
            }
            if (!stat) {
                container.innerHTML = `<div class="stat-spotlight__text"><p class="stat-spotlight__value">-<span class="stat-spotlight__unit">${unitLabel}</span></p><p class="stat-name">No data</p><p class="stat-team"></p></div><div class="stat-spotlight__media"><div class="player-fallback">-</div></div>`;
                return;
            }
            // Not every player has a photo uploaded on the FPL CDN (it 403s
            // for some codes) - fall back to the initial-letter badge if the
            // image fails to load, instead of showing a broken-image icon.
            const initial = (stat.name || '-').slice(0, 1);
            const shirtUrl = stat.shirt_url || '';
            const media = stat.photo_url
                ? `<img src="${stat.photo_url}" alt="${stat.name}" onerror="window.handlePlayerPhotoError(this, '${shirtUrl}')"><div class="player-fallback" style="display:none;">${initial}</div>`
                : shirtUrl
                    ? `<img src="${shirtUrl}" alt="${stat.name}" class="is-shirt-fallback" onerror="window.handlePlayerPhotoError(this, '')"><div class="player-fallback" style="display:none;">${initial}</div>`
                    : `<div class="player-fallback">${initial}</div>`;
            container.innerHTML = `<div class="stat-spotlight__text"><p class="stat-spotlight__value">${stat[valueKey] || 0}<span class="stat-spotlight__unit">${unitLabel}</span></p><p class="stat-name">${stat.name}</p><p class="stat-team">${stat.team_name || ''}</p></div><div class="stat-spotlight__media">${media}</div>`;
        };

        const renderHome = (payload) => {
            const classicRows = (payload.classic && payload.classic.rows) || [];
            renderMiniLeaders('[data-home-classic-list]', classicRows, 'total_points');

            const gameweekData = payload.gameweek;
            if (gameweekData) {
                renderMiniLeaders('[data-home-gameweek-list]', gameweekData.entries, 'gameweek_points', 1);
                const gwLabel = document.querySelector('[data-home-gameweek-label]');
                if (gwLabel) {
                    gwLabel.textContent = gameweekData.selected_gameweek ? ` · GW${gameweekData.selected_gameweek}` : '';
                }
            }

            const captainRows = (payload.captain && payload.captain.leaderboard) || [];
            renderMiniLeaders('[data-home-captain-list]', captainRows, 'captain_points', 1);

            const monthlyData = payload.monthly;
            if (monthlyData) {
                renderMiniLeaders('[data-home-monthly-list]', monthlyData.rankings, 'monthly_points', 1);
                const monthLabel = document.querySelector('[data-home-monthly-label]');
                if (monthLabel) {
                    monthLabel.textContent = monthlyData.selected_month_label ? ` · ${monthlyData.selected_month_label}` : '';
                }
            }

            const dashboard = payload.dashboard;
            if (!dashboard) {
                return;
            }

            renderStatSpotlight('[data-home-top-scorer]', dashboard.top_scorer, 'Goals', 'goals');
            renderStatSpotlight('[data-home-top-assister]', dashboard.top_assister, 'Assists', 'assists');
            renderStatSpotlight('[data-home-top-clean-sheet]', dashboard.top_clean_sheet, 'Clean Sheets', 'clean_sheets');

            const gwPager = document.querySelector('[data-gw-pager]');
            // Only touch the Live Fixtures label/grid/pager state on its
            // very first render - the 45s background poll re-runs this
            // same code, and without this guard it was silently snapping
            // someone back to the current gameweek's fixtures while they
            // were browsing an earlier one.
            if (!gwPager || gwPager.dataset.userNavigated !== 'true') {
                const liveLabel = document.querySelector('[data-home-live-fixtures-label]');
                if (liveLabel) {
                    liveLabel.textContent = dashboard.live_fixtures_label || 'Upcoming';
                }

                const liveGrid = document.querySelector('[data-home-live-fixtures-grid]');
                if (liveGrid) {
                    window.renderLiveFixturesGrid(liveGrid, dashboard.live_fixtures || []);
                }
            }

            if (gwPager && gwPager.dataset.userNavigated !== 'true') {
                gwPager.dataset.gw = dashboard.live_fixtures_gameweek || '';
                gwPager.dataset.minGw = dashboard.live_fixtures_min_gw || 1;
                gwPager.dataset.maxGw = dashboard.live_fixtures_max_gw || 38;
                if (window.updateGwPagerButtons) {
                    window.updateGwPagerButtons(gwPager);
                }
            }

            const ownedGrid = document.querySelector('[data-home-top-picks-rows]');
            if (ownedGrid) {
                const players = dashboard.top_players || [];
                ownedGrid.innerHTML = players.length
                    ? players
                        .map(
                            (player) => `
                            <div class="owned-card">
                                <span class="owned-card__rank">#${player.rank}</span>
                                <div class="owned-card__media">${window.buildPlayerAvatar(player.name, player.photo_url, player.shirt_url, 'owned-card__photo')}</div>
                                <div class="owned-card__text">
                                    <strong>${player.name}</strong>
                                    <span>${player.team_short_name}</span>
                                </div>
                                <div class="owned-card__percent">
                                    <strong>${player.selected_by_percent}%</strong>
                                    <span>Selected</span>
                                </div>
                            </div>
                        `
                        )
                        .join('')
                    : '<p class="chip-history__empty">No player data available right now.</p>';
            }

            const nextGwLabel = document.querySelector('[data-home-next-gw]');
            if (nextGwLabel && dashboard.next_gameweek) {
                nextGwLabel.textContent = dashboard.next_gameweek;
            }

            const picksNextGrid = document.querySelector('[data-home-top-picks-next]');
            if (picksNextGrid) {
                const picks = dashboard.top_picks_next_gw || [];
                picksNextGrid.innerHTML = picks.length
                    ? picks
                        .map((player) => {
                            const fixture = player.next_fixture;
                            const fixtureLabel = fixture ? `${fixture.opponent} (${fixture.is_home ? 'H' : 'A'})` : 'TBC';
                            return `
                            <div class="pick-card">
                                <div class="pick-card__media">${window.buildPlayerAvatar(player.name, player.photo_url, player.shirt_url, 'pick-card__photo')}</div>
                                <span class="pick-card__points">${player.expected_points} pts</span>
                                <strong class="pick-card__name">${player.name}</strong>
                                <span class="pick-card__meta">${player.position_label} &middot; ${player.team_short_name} &middot; &pound;${player.price}m</span>
                                <span class="pick-card__fixture">${fixtureLabel}</span>
                            </div>
                        `;
                        })
                        .join('')
                    : '<p class="chip-history__empty">No pick data available right now.</p>';
            }

            const totwLabel = document.querySelector('[data-home-totw-label]');
            if (totwLabel) {
                totwLabel.textContent = dashboard.team_of_the_week_gameweek ? `GW ${dashboard.team_of_the_week_gameweek}` : '';
            }

            const totwRow = document.querySelector('[data-home-totw-row]');
            if (totwRow) {
                const totw = dashboard.team_of_the_week || [];
                totwRow.innerHTML = totw.length
                    ? totw
                        .map(
                            (player) => `
                            <div class="totw-player">
                                ${window.buildPlayerAvatar(player.name, player.photo_url, player.shirt_url, 'totw-player__photo')}
                                <span class="totw-player__name">${player.name}</span>
                                <span class="totw-player__points">${player.points} pts</span>
                            </div>
                        `
                        )
                        .join('')
                    : '<p>No Team of the Week data available yet.</p>';
            }

            const injuriesList = document.querySelector('[data-home-injuries-list]');
            if (injuriesList) {
                const injuries = dashboard.injuries || [];
                injuriesList.innerHTML = injuries.length
                    ? injuries
                        .map(
                            (player) => `
                            <li class="injury-item">
                                ${window.buildPlayerAvatar(player.name, player.photo_url, player.shirt_url, 'injury-item__photo')}
                                <div>
                                    <p><strong>${player.name}</strong> <span class="status-pill status-pill--${player.status_code || 'u'}">${player.status_label}</span></p>
                                    <small>${player.news}</small>
                                </div>
                            </li>
                        `
                        )
                        .join('')
                    : '<li><div><p>No injury or suspension news right now.</p></div></li>';
            }

            const fixturesList = document.querySelector('[data-home-fixtures-list]');
            if (fixturesList) {
                const fixtures = dashboard.fixtures || [];
                fixturesList.innerHTML = fixtures.length
                    ? fixtures
                        .map((fixture) => `
                            <li>
                                <div>
                                    <p>${fixture.home_team.short_name} vs ${fixture.away_team.short_name}</p>
                                    <small>${fixture.kickoff_display}</small>
                                </div>
                                <span class="difficulty difficulty-${fixture.difficulty}">D${fixture.difficulty}</span>
                            </li>
                        `)
                        .join('')
                    : '<li><div><p>No fixture data available right now.</p></div></li>';
            }
        };

        const sectionForPageType = {
            classic: 'classic',
            gameweek: 'gameweek',
            monthly: 'monthly',
            captain: 'captain',
        };

        // On the very first fetch the dropdown has no options yet (the
        // page renders without the data that would populate it), so it
        // can't tell us which gameweek/month was requested - fall back to
        // the URL's own query string, which is how a direct link or the
        // dropdown's own (full-page-reload) navigation got here.
        const urlParams = new URLSearchParams(window.location.search);

        const refreshLeaguePage = async () => {
            try {
                let requestUrl = endpoint;
                const section = sectionForPageType[pageType];
                if (section) {
                    requestUrl += (requestUrl.includes('?') ? '&' : '?') + 'section=' + section;
                }
                if (pageType === 'monthly') {
                    const monthSelect = document.getElementById('month-select');
                    const monthValue = (monthSelect && monthSelect.value) || urlParams.get('month');
                    if (monthValue) {
                        requestUrl += '&month=' + encodeURIComponent(monthValue);
                    }
                }
                if (pageType === 'gameweek') {
                    const gwSelect = document.getElementById('gameweek-select');
                    const gwValue = (gwSelect && gwSelect.value) || urlParams.get('gameweek');
                    if (gwValue) {
                        requestUrl += '&gameweek=' + encodeURIComponent(gwValue);
                    }
                }
                const response = await fetch(requestUrl, {
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });
                if (!response.ok) {
                    return;
                }

                const payload = await response.json();
                setSharedMeta(payload);

                if (pageType === 'classic') {
                    renderClassic(payload);
                } else if (pageType === 'gameweek') {
                    renderGameweek(payload);
                } else if (pageType === 'monthly') {
                    renderMonthly(payload);
                } else if (pageType === 'captain') {
                    renderCaptain(payload);
                } else if (pageType === 'home') {
                    renderHome(payload);
                }
            } catch (err) {
                // Silent fail: keep whatever's already shown if a fetch fails.
            }
        };

        // Fetch right away instead of waiting for the first 45s tick - the
        // page shell (nav, banner, dropdowns) renders instantly without
        // blocking on the live FPL API, and table/leaderboard data fills in
        // moments later once this resolves.
        refreshLeaguePage();
        setInterval(refreshLeaguePage, 45000);
    }

    // Live Tracker's own "League Achievements" / "Current Standing" -
    // fetched separately after the rest of the page has already rendered,
    // since checking a manager's position across 3 leaderboards' worth of
    // live data is too slow to compute inline with the page itself.
    const achievementsBox = document.querySelector('[data-achievements-loading]');
    if (achievementsBox) {
        const entryId = achievementsBox.getAttribute('data-entry-id');
        fetch(`/api/league-live-data/?section=achievements&entry_id=${encodeURIComponent(entryId)}`)
            .then((res) => res.json())
            .then((payload) => {
                const achievements = payload.achievements;
                if (!achievements || !achievements.in_league) {
                    achievementsBox.remove();
                    return;
                }

                const titles = achievements.titles || [];
                achievementsBox.innerHTML = titles.length
                    ? '<p class="chip-history__label">League Achievements</p><div class="chip-history__list">'
                        + titles
                            .map((title) => `<span class="chip-history__item chip-history__item--title">🏆 ${title.label} <small>${title.detail}</small></span>`)
                            .join('')
                        + '</div>'
                    : '<p class="chip-history__label">League Achievements</p><p class="chip-history__empty">No titles won yet this season.</p>';

                const positions = achievements.current_positions;
                const positionItems = [];
                if (positions && positions.classic_rank) {
                    positionItems.push(
                        `<span class="chip-history__item">Classic League #${positions.classic_rank} <small>of ${positions.classic_total_entries} &middot; ${positions.classic_points} pts</small></span>`
                    );
                }
                if (positions && positions.captain_rank) {
                    positionItems.push(
                        `<span class="chip-history__item">Captain Mode #${positions.captain_rank} <small>of ${positions.captain_total_entries} &middot; ${positions.captain_points} pts</small></span>`
                    );
                }
                if (positions && positions.monthly_rank) {
                    positionItems.push(
                        `<span class="chip-history__item">${positions.monthly_label} #${positions.monthly_rank} <small>of ${positions.monthly_total_entries} &middot; ${positions.monthly_points} pts</small></span>`
                    );
                }
                if (positionItems.length) {
                    const positionsBox = document.createElement('div');
                    positionsBox.className = 'chip-history';
                    positionsBox.innerHTML = `<p class="chip-history__label">Current Standing</p><div class="chip-history__list">${positionItems.join('')}</div>`;
                    achievementsBox.after(positionsBox);
                }
            })
            .catch(() => {
                achievementsBox.remove();
            });
    }

    // Dashboard's Live Fixtures prev/next gameweek pager.
    const gwPagerEl = document.querySelector('[data-gw-pager]');
    if (gwPagerEl) {
        const prevBtn = gwPagerEl.querySelector('[data-gw-prev]');
        const nextBtn = gwPagerEl.querySelector('[data-gw-next]');
        const label = gwPagerEl.querySelector('[data-home-live-fixtures-label]');
        const grid = gwPagerEl.querySelector('[data-home-live-fixtures-grid]');

        const updateButtons = () => {
            const gw = parseInt(gwPagerEl.dataset.gw, 10) || 1;
            const minGw = parseInt(gwPagerEl.dataset.minGw, 10) || 1;
            const maxGw = parseInt(gwPagerEl.dataset.maxGw, 10) || 38;
            prevBtn.disabled = gw <= minGw;
            nextBtn.disabled = gw >= maxGw;
        };
        window.updateGwPagerButtons = updateButtons;

        const loadGameweek = (gw) => {
            grid.innerHTML = '<article class="live-fixture-card"><p>Loading live fixtures&hellip;</p></article>';
            fetch(`/api/league-live-data/?section=live_fixtures&gameweek=${gw}`)
                .then((res) => res.json())
                .then((payload) => {
                    const page = payload.live_fixtures_page;
                    if (!page) {
                        return;
                    }
                    gwPagerEl.dataset.gw = page.gameweek;
                    gwPagerEl.dataset.minGw = page.min_gameweek;
                    gwPagerEl.dataset.maxGw = page.max_gameweek;
                    gwPagerEl.dataset.userNavigated = 'true';
                    if (label) {
                        label.textContent = `GW ${page.gameweek}`;
                    }
                    window.renderLiveFixturesGrid(grid, page.fixtures || []);
                    updateButtons();
                })
                .catch(() => {
                    grid.innerHTML = '<article class="live-fixture-card"><p>Could not load fixtures right now.</p></article>';
                });
        };

        prevBtn.addEventListener('click', () => {
            const gw = parseInt(gwPagerEl.dataset.gw, 10) || 1;
            const minGw = parseInt(gwPagerEl.dataset.minGw, 10) || 1;
            if (gw > minGw) {
                loadGameweek(gw - 1);
            }
        });
        nextBtn.addEventListener('click', () => {
            const gw = parseInt(gwPagerEl.dataset.gw, 10) || 1;
            const maxGw = parseInt(gwPagerEl.dataset.maxGw, 10) || 38;
            if (gw < maxGw) {
                loadGameweek(gw + 1);
            }
        });

        updateButtons();
    }
});
