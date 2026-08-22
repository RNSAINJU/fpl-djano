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
                tbody.innerHTML = '<tr><td colspan="6">No rankings available yet.</td></tr>';
                return;
            }

            tbody.innerHTML = rows
                .map((row) => `
                    <tr>
                        <td>#${row.rank}</td>
                        <td>${row.manager_name}</td>
                        <td>${row.team_name}</td>
                        <td>#${row.league_rank}</td>
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
                container.innerHTML = '<div class="player-fallback">-</div><p class="stat-name">No data</p><p class="stat-value">-</p>';
                return;
            }
            const image = stat.photo_url
                ? `<img src="${stat.photo_url}" alt="${stat.name}">`
                : `<div class="player-fallback">${(stat.name || '-').slice(0, 1)}</div>`;
            container.innerHTML = `${image}<p class="stat-name">${stat.name}</p><p class="stat-value">${stat[valueKey] || 0} ${unitLabel}</p>`;
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

            const liveLabel = document.querySelector('[data-home-live-fixtures-label]');
            if (liveLabel) {
                liveLabel.textContent = dashboard.live_fixtures_label || 'Upcoming';
            }

            const liveGrid = document.querySelector('[data-home-live-fixtures-grid]');
            if (liveGrid) {
                const liveFixtures = dashboard.live_fixtures || [];
                if (!liveFixtures.length) {
                    liveGrid.innerHTML = '<article class="live-fixture-card"><p>No live fixture data available right now.</p></article>';
                } else {
                    liveGrid.innerHTML = liveFixtures
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
                }
            }

            const topPicksRows = document.querySelector('[data-home-top-picks-rows]');
            if (topPicksRows) {
                const players = dashboard.top_players || [];
                topPicksRows.innerHTML = players.length
                    ? players
                        .map((player) => `
                            <tr>
                                <td>${player.name} <small>${player.team_short_name}</small></td>
                                <td>${player.position_label}</td>
                                <td>${player.price}</td>
                                <td>${player.total_points}</td>
                                <td>${player.selected_by_percent}%</td>
                            </tr>
                        `)
                        .join('')
                    : '<tr><td colspan="5">No player data available right now.</td></tr>';
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
});
