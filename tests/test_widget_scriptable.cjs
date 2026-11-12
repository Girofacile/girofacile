const {test} = require('node:test');
const assert = require('node:assert/strict');
const {runWidget, walk, texts, fixture} = require('./helpers/scriptable-widget.cjs');

test('large Scriptable widget preserves all ten real indicators', async () => {
  const {widget, complete} = await runWidget();
  const content = texts(widget);
  for (const label of ['Ticket aperti', 'Aziende', 'In prova', 'Abbonate', 'Nuove nel mese', 'Giri oggi', 'In corso', 'Errori 24h', 'MRR stimato']) {
    assert.ok(content.includes(label), label);
  }
  assert.ok(content.includes('Ticket oggi · 2'));
  for (const value of [7, 103, 11, 37, 5, 24, 8, 3]) assert.ok(content.includes(String(value)), String(value));
  assert.ok(content.some(value => /^1\.?184,50€$/.test(value.replace(/\s/g, ''))));
  assert.equal(widget.backgroundColor.hex, '#f4f7fd');
  assert.equal(complete, true);
});

test('smaller widget families keep their original six and two indicators legible', async () => {
  const medium = texts((await runWidget({family: 'medium'})).widget);
  for (const label of ['Ticket aperti', 'Ticket oggi', 'Aziende', 'In prova', 'Abbonate', 'Giri in corso']) {
    assert.ok(medium.includes(label), label);
  }
  assert.equal(medium.includes('MRR stimato'), false);
  const small = texts((await runWidget({family: 'small'})).widget);
  for (const value of ['Ticket aperti', '7', 'Aziende', '103']) assert.ok(small.includes(value), value);
  assert.equal(small.includes('In prova'), false);
});

test('zeros remain actual counts and missing or invalid values are not invented', async () => {
  const zeros = Object.fromEntries(Object.keys(fixture).map(key => [key, key === 'aggiornato_alle' ? fixture[key] : 0]));
  const zeroContent = texts((await runWidget({data: zeros})).widget);
  assert.equal(zeroContent.filter(value => value === '0').length, 8);
  assert.ok(zeroContent.includes('Ticket oggi · 0'));
  assert.ok(zeroContent.some(value => value.replace(/\s/g, '') === '0€'));
  const invalid = {...fixture, ticket_aperti: null, aziende_registrate: undefined,
    aziende_abbonate: '37', giri_oggi: -4, mrr_stimato: Number.NaN};
  const invalidContent = texts((await runWidget({data: invalid})).widget);
  assert.equal(invalidContent.filter(value => value === '—').length, 5);
  assert.equal(invalidContent.some(value => /undefined|NaN|-4/.test(value)), false);
});

test('large values use Italian grouping and remain shrinkable', async () => {
  const {widget} = await runWidget({data: {...fixture, aziende_registrate: 1234567, mrr_stimato: 999999.95}});
  const count = walk(widget).find(node => node.text === '1.234.567');
  assert.ok(count);
  assert.ok(count.minimumScaleFactor > 0 && count.minimumScaleFactor < 1);
  assert.ok(texts(widget).some(value => value.replace(/\s/g, '') === '999.999,95€'));
});

test('read-only authorization, tap destination and refresh interval remain unchanged', async () => {
  const {widget, requests} = await runWidget();
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, 'https://girofacile.example/api/widget/stats');
  assert.deepEqual(JSON.parse(JSON.stringify(requests[0].headers)), {Authorization: 'Bearer gfw_test_only_not_a_real_key'});
  assert.equal(requests[0].timeoutInterval, 15);
  assert.equal(widget.url, 'https://girofacile.example/admin');
  assert.equal(widget.refreshAfterDate.getTime(), Date.parse('2026-11-12T12:26:00Z'));
});

test('auth and network failures show an honest state without server details or fake counts', async () => {
  const unauthorized = texts((await runWidget({status: 401, data: {detail: 'INTERNAL_SECRET_RESPONSE'}})).widget);
  assert.ok(unauthorized.includes('Collegamento da aggiornare'));
  assert.equal(unauthorized.some(value => /INTERNAL_SECRET_RESPONSE|Ticket aperti|^0$/.test(value)), false);
  const offline = texts((await runWidget({networkError: new Error('INTERNAL_SECRET_NETWORK')})).widget);
  assert.ok(offline.includes('Dati non disponibili'));
  assert.equal(offline.some(value => /INTERNAL_SECRET_NETWORK|Ticket aperti|^0$/.test(value)), false);
  const malformed = texts((await runWidget({data: []})).widget);
  assert.ok(malformed.includes('Dati non disponibili'));
});

test('timestamp fallback never presents an invalid date as a successful update', async () => {
  const content = texts((await runWidget({data: {...fixture, aggiornato_alle: 'invalid'}})).widget);
  assert.ok(content.includes('Orario non disponibile'));
  assert.equal(content.some(value => /Invalid Date|Aggiornato alle/.test(value)), false);
});

test('all supported phone widths create finite positive card sizes and preview can run in-app', async () => {
  for (const width of [320, 375, 390, 430]) {
    for (const family of ['small', 'medium', 'large']) {
      const {widget} = await runWidget({width, family});
      const sizes = walk(widget).filter(node => node.size).map(node => node.size);
      assert.ok(sizes.length > 0, `${width} ${family}`);
      for (const size of sizes) {
        assert.ok(Number.isFinite(size.width) && size.width > 0 && size.width < width, `${width} ${family} card width`);
        assert.ok(Number.isFinite(size.height) && size.height > 0, `${width} ${family} card height`);
      }
    }
  }
  const preview = await runWidget({runsInWidget: false});
  assert.deepEqual(preview.presented, ['large']);
  assert.equal(preview.complete, true);
});
