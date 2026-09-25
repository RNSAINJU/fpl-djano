const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { test } = require('node:test');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/fantasy/js/app.js'), 'utf8');
const attack = `<img src=x onerror="alert('x')"> &`;
const escaped = '&lt;img src=x onerror=&quot;alert(&#39;x&#39;)&quot;&gt; &amp;';

function setup(page, payload) {
    const elements = new Map();
    const element = () => ({ innerHTML: '', textContent: '', value: '', classList: { add() {}, remove() {} } });
    const context = {
        window: { location: { search: '' } }, URLSearchParams, setInterval() {},
        fetch: async () => ({ ok: true, json: async () => payload }),
        document: {
            addEventListener(event, callback) { context.ready = callback; },
            querySelectorAll() { return []; },
            getElementById() { return null; },
            querySelector(selector) {
                if (selector === '[data-league-page][data-live-endpoint]') {
                    return { getAttribute: (name) => name === 'data-league-page' ? page : '/api/league-live-data/' };
                }
                if (['.countdown[data-target]', '[data-achievements-loading]', '[data-gw-pager]'].includes(selector)) return null;
                if (!elements.has(selector)) elements.set(selector, element());
                return elements.get(selector);
            }
        }
    };
    vm.createContext(context);
    vm.runInContext(source, context);
    return { context, elements };
}

for (const [page, section, key] of [
    ['classic', 'classic', 'rows'], ['gameweek', 'gameweek', 'entries'],
    ['monthly', 'monthly', 'rankings'], ['captain', 'captain', 'leaderboard'],
]) {
    test(`${page}: manager and team markup remains text`, async () => {
        const row = { rank: 1, manager_name: attack, team_name: attack, captain_name: attack };
        const { context, elements } = setup(page, { [section]: { [key]: [row] } });
        context.ready();
        await new Promise(setImmediate);
        const html = elements.get(`[data-${page}-rows]`).innerHTML;
        assert.ok(html.includes(escaped));
        assert.ok(!html.includes(attack));
        assert.ok(html.includes('<tr>'));
    });
}

test('avatar attributes escape quotes and keep fallback URLs out of handler code', () => {
    const { context } = setup();
    const html = context.window.buildPlayerAvatar(attack, attack, "');alert(1);//", 'photo');
    assert.ok(html.includes(`alt="${escaped}"`));
    assert.ok(html.includes(`src="${escaped}"`));
    assert.ok(html.includes('data-shirt-url="&#39;);alert(1);//"'));
    assert.ok(html.includes('onerror="window.handlePlayerPhotoError(this, this.dataset.shirtUrl)"'));
    assert.ok(!html.includes(attack));
    assert.equal(context.escapeHtml(`O'Brien & Sons <FC> "A"`), 'O&#39;Brien &amp; Sons &lt;FC&gt; &quot;A&quot;');
    assert.equal(context.escapeHtml('&lt;script&gt;'), '&amp;lt;script&amp;gt;');
});

test('fixture cards escape names, scores, and image attributes', () => {
    const { context } = setup();
    const grid = {};
    context.window.renderLiveFixturesGrid(grid, [{
        home_team: { short_name: attack, shirt_url: attack },
        away_team: { short_name: attack, shirt_url: attack },
        status: attack, home_score: attack, away_score: attack,
    }]);
    assert.ok(grid.innerHTML.includes(escaped));
    assert.ok(!grid.innerHTML.includes(attack));
});

test('dashboard cards and mini leaderboards escape API text', async () => {
    const row = { manager_name: attack, rank: 1, total_points: 10 };
    const player = { name: attack, news: attack, team_short_name: attack, photo_url: attack, shirt_url: attack };
    const { context, elements } = setup('home', {
        classic: { rows: [row] }, dashboard: {
            top_scorer: { name: attack, team_name: attack, photo_url: attack, shirt_url: attack },
            top_players: [player], top_picks_next_gw: [player], team_of_the_week: [player], injuries: [player],
        }
    });
    context.ready();
    await new Promise(setImmediate);
    for (const selector of ['[data-home-classic-list]', '[data-home-top-scorer]', '[data-home-top-picks-rows]', '[data-home-top-picks-next]', '[data-home-totw-row]', '[data-home-injuries-list]']) {
        const html = elements.get(selector).innerHTML;
        assert.ok(html.includes(escaped), selector);
        assert.ok(!html.includes(attack), selector);
    }
});
