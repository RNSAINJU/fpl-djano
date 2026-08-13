document.addEventListener('DOMContentLoaded', () => {
    const items = document.querySelectorAll('.reveal');
    items.forEach((item, index) => {
        item.style.animationDelay = `${index * 100}ms`;
    });

    const sidebar = document.getElementById('sidebar');
    const toggle = document.getElementById('sidebar-toggle');
    if (sidebar && toggle) {
        const backdrop = document.createElement('div');
        backdrop.className = 'nav-backdrop';
        backdrop.setAttribute('aria-hidden', 'true');
        document.body.appendChild(backdrop);

        const closeButton = document.createElement('button');
        closeButton.type = 'button';
        closeButton.className = 'sidebar-close';
        closeButton.setAttribute('aria-label', 'Close navigation');
        closeButton.textContent = '✕';
        const brandBlock = sidebar.querySelector('.brand-block');
        if (brandBlock) {
            brandBlock.appendChild(closeButton);
        }

        toggle.setAttribute('aria-expanded', 'false');

        const openSidebar = () => {
            sidebar.classList.add('is-open');
            backdrop.classList.add('is-visible');
            document.body.classList.add('nav-open');
            toggle.setAttribute('aria-expanded', 'true');
        };

        const closeSidebar = () => {
            sidebar.classList.remove('is-open');
            backdrop.classList.remove('is-visible');
            document.body.classList.remove('nav-open');
            toggle.setAttribute('aria-expanded', 'false');
        };

        toggle.addEventListener('click', () => {
            if (sidebar.classList.contains('is-open')) {
                closeSidebar();
            } else {
                openSidebar();
            }
        });

        closeButton.addEventListener('click', closeSidebar);
        backdrop.addEventListener('click', closeSidebar);

        sidebar.querySelectorAll('a').forEach((link) => {
            link.addEventListener('click', closeSidebar);
        });

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                closeSidebar();
            }
        });

        window.addEventListener('resize', () => {
            if (window.innerWidth > 1020) {
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

        const sourceLabel = (source) => {
            if (source === 'live') {
                return 'Live FPL code 6232';
            }
            if (source === 'local') {
                return 'Local fallback data';
            }
            return 'No data source';
        };

        const setSharedMeta = (payload) => {
            const name = document.querySelector('[data-league-name]');
            if (name) {
                name.textContent = payload.league_name || 'FPL League 6232';
            }

            const source = document.querySelector('[data-source-badge]');
            if (source) {
                source.textContent = sourceLabel(payload.league_source);
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
            const winner = payload.gameweek.winner;
            const chip = document.querySelector('[data-gameweek-winner-chip]');
            if (chip) {
                chip.textContent = winner ? `#1 ${winner.manager_name}` : 'No winner yet';
            }

            const winnerName = document.querySelector('[data-gameweek-winner-name]');
            const winnerTeam = document.querySelector('[data-gameweek-winner-team]');
            const winnerPoints = document.querySelector('[data-gameweek-winner-points]');
            if (winnerName) {
                winnerName.textContent = winner ? winner.manager_name : 'No winner yet';
            }
            if (winnerTeam) {
                winnerTeam.textContent = winner ? winner.team_name : '-';
            }
            if (winnerPoints) {
                winnerPoints.textContent = winner ? winner.gameweek_points : '0';
            }

            const tbody = document.querySelector('[data-gameweek-rows]');
            if (!tbody) {
                return;
            }

            const rows = payload.gameweek.entries || [];
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
            const winner = payload.monthly.winner;
            const chip = document.querySelector('[data-monthly-winner-chip]');
            if (chip) {
                chip.textContent = winner ? `Winner ${winner.manager_name}` : 'No winner yet';
            }

            const winnerName = document.querySelector('[data-monthly-winner-name]');
            const winnerTeam = document.querySelector('[data-monthly-winner-team]');
            const winnerScore = document.querySelector('[data-monthly-winner-score]');
            if (winnerName) {
                winnerName.textContent = winner ? winner.manager_name : 'No winner yet';
            }
            if (winnerTeam) {
                winnerTeam.textContent = winner ? winner.team_name : '-';
            }
            if (winnerScore) {
                winnerScore.textContent = winner ? winner.monthly_score : '0';
            }

            const tbody = document.querySelector('[data-monthly-rows]');
            if (!tbody) {
                return;
            }

            const rows = payload.monthly.rankings || [];
            if (!rows.length) {
                tbody.innerHTML = '<tr><td colspan="4">No rankings available yet.</td></tr>';
                return;
            }

            tbody.innerHTML = rows
                .map((row) => `
                    <tr>
                        <td>#${row.rank}</td>
                        <td>${row.manager_name}</td>
                        <td>${row.team_name}</td>
                        <td>${row.monthly_score}</td>
                    </tr>
                `)
                .join('');
        };

        const renderChase = (payload) => {
            const safeLine = document.querySelector('[data-chase-safe-line]');
            if (safeLine) {
                safeLine.textContent = `Safe line ${payload.chase.safe_line_points} pts`;
            }

            const tbody = document.querySelector('[data-chase-rows]');
            if (!tbody) {
                return;
            }

            const rows = payload.chase.rows || [];
            if (!rows.length) {
                tbody.innerHTML = '<tr><td colspan="5">No chase data available yet.</td></tr>';
                return;
            }

            tbody.innerHTML = rows
                .map((row) => {
                    const gap = row.gap > 0 ? `+${row.gap}` : `${row.gap}`;
                    const statusClass = row.status === 'Safe' ? 'status-pill--safe' : 'status-pill--chasing';
                    return `
                        <tr>
                            <td>#${row.rank}</td>
                            <td>${row.manager_name}</td>
                            <td>${row.total_points}</td>
                            <td>${gap}</td>
                            <td><span class="status-pill ${statusClass}">${row.status}</span></td>
                        </tr>
                    `;
                })
                .join('');
        };

        const refreshLeaguePage = async () => {
            try {
                const response = await fetch(endpoint, {
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
                } else if (pageType === 'chase') {
                    renderChase(payload);
                }
            } catch (err) {
                // Silent fail: keep server-rendered content if polling fails.
            }
        };

        setInterval(refreshLeaguePage, 45000);
    }
});
