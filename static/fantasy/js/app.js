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
                tbody.innerHTML = '<tr><td colspan="6">No league standings available yet.</td></tr>';
                return;
            }

            tbody.innerHTML = rows
                .map((row) => {
                    const formClass = row.form === 'Hot'
                        ? 'status-pill--safe'
                        : row.form === 'Steady'
                            ? 'status-pill--steady'
                            : 'status-pill--chasing';
                    return `
                        <tr>
                            <td>#${row.rank}</td>
                            <td>${row.manager_name}</td>
                            <td>${row.team_name}</td>
                            <td>${row.total_points}</td>
                            <td>${row.gap_to_leader}</td>
                            <td><span class="status-pill ${formClass}">${row.form}</span></td>
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
