#!/usr/bin/env node
// Chess Scenes — test suite
// Run with: node test.js  (no dependencies required)

const { readFileSync } = require('fs');
const html = readFileSync('./index.html', 'utf8');

let passed = 0, failed = 0;

function test(name, fn) {
  try { fn(); console.log(`  ✅ ${name}`); passed++; }
  catch (e) { console.log(`  ❌ ${name}\n     ${e.message}`); failed++; }
}
function assert(cond, msg) { if (!cond) throw new Error(msg || 'Assertion failed'); }
function assertEqual(a, b, msg) { if (a !== b) throw new Error(msg || `Expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`); }

// ─── EXTRACT FUNCTIONS ────────────────────────────────────────────────────────

function extractFn(name, src) {
  const re = new RegExp(`function ${name}\\s*\\([^)]*\\)\\s*\\{`);
  const start = src.search(re);
  if (start === -1) throw new Error(`Could not find function: ${name}`);
  let depth = 0, i = start;
  while (i < src.length) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (depth === 0) return src.slice(start, i + 1); }
    i++;
  }
  throw new Error(`Could not extract function: ${name}`);
}

const scripts = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].map(m => m[1]).join('\n');
const toSlugSrc = extractFn('toSlug', scripts);
const makeSlugSrc = extractFn('makeSlug', scripts);
const locMatchesSrc = extractFn('locMatchesFilters', scripts)
  .replace('function locMatchesFilters(loc)', 'function locMatchesFilters(loc, activeLabels, activeDays, activeCity)');

const { toSlug, makeSlug, locMatchesFilters } = new Function(`
  ${toSlugSrc}
  ${makeSlugSrc}
  ${locMatchesSrc}
  return { toSlug, makeSlug, locMatchesFilters };
`)();

// ─── PARSE VENUES ─────────────────────────────────────────────────────────────

function parseVenuesFromHTML(html) {
  // The venue data lives in a comment starting with <!--=== and ending with -->
  const start = html.indexOf('<!--=');
  const end = html.indexOf('-->', start);
  if (start === -1 || end === -1) throw new Error('Venue data comment not found');
  const raw = html.slice(start, end);
  // skip past the header separator line
  const dataStart = raw.indexOf("\nname:");
  const cleanRaw = dataStart !== -1 ? raw.slice(dataStart) : raw;

  const venues = [];
  let current = {};
  for (const line of cleanRaw.split('\n')) {
    const stripped = line.trim();
    if (!stripped) {
      if (current.name) { venues.push({ ...current }); current = {}; }
      continue;
    }
    const m = stripped.match(/^(\w+)\s*:\s*(.+)/);
    if (m) current[m[1].toLowerCase()] = m[2].trim();
  }
  if (current.name) venues.push({ ...current });

  return venues.filter(v => v.name && v.coordinates).map(v => {
    const [lat, lng] = v.coordinates.split(',').map(Number);
    return {
      name: v.name,
      labels: (v.labels || '').split(',').map(s => s.trim()).filter(Boolean),
      days: v.days ? v.days.split(',').map(s => s.trim()).filter(Boolean) : null,
      lat, lng,
      note: v.note || '',
      gmap: v.gmap || '',
      link: v.link || '',
      image: v.image || '',
      city: v.city || '',
      id: v.id || '',
    };
  });
}

const VENUES = parseVenuesFromHTML(html);

// ─── TESTS ────────────────────────────────────────────────────────────────────

console.log('\n── Data integrity ───────────────────────────────────────────');

test('parses at least 100 venues from HTML', () => {
  assert(VENUES.length >= 100, `Only got ${VENUES.length} venues`);
});

test('every venue has a name', () => {
  const bad = VENUES.filter(v => !v.name);
  assert(bad.length === 0, `${bad.length} venues missing name`);
});

test('every venue has valid coordinates', () => {
  const bad = VENUES.filter(v => isNaN(v.lat) || isNaN(v.lng));
  assert(bad.length === 0, `Invalid coordinates: ${bad.map(v => v.name).join(', ')}`);
});

test('every venue has at least one label', () => {
  const bad = VENUES.filter(v => v.labels.length === 0);
  assert(bad.length === 0, `Missing labels: ${bad.map(v => v.name).join(', ')}`);
});

test('all labels are from the known taxonomy', () => {
  const VALID = new Set(['chess board','chess shop','chess memorial','chess bar','chess club','chess meetup','chess museum']);
  const bad = [];
  for (const v of VENUES)
    for (const l of v.labels)
      if (!VALID.has(l)) bad.push(`"${l}" on "${v.name}"`);
  assert(bad.length === 0, `Unknown labels:\n     ${bad.join('\n     ')}`);
});

test('days field is null or a non-empty array', () => {
  const bad = VENUES.filter(v => v.days !== null && (!Array.isArray(v.days) || v.days.length === 0));
  assert(bad.length === 0, `Bad days: ${bad.map(v => v.name).join(', ')}`);
});

test('gmap and link fields start with http if set', () => {
  const bad = VENUES.filter(v =>
    (v.gmap && !v.gmap.startsWith('http')) || (v.link && !v.link.startsWith('http'))
  );
  assert(bad.length === 0, `Bad URLs: ${bad.map(v => v.name).join(', ')}`);
});

console.log('\n── Slug generation ──────────────────────────────────────────');

test('toSlug lowercases', () => assertEqual(toSlug('Amsterdam'), 'amsterdam'));
test('toSlug strips accents', () => assertEqual(toSlug('Göteborg'), 'goteborg'));
test('toSlug replaces spaces with hyphens', () => assertEqual(toSlug('Max Euwe Centrum'), 'max-euwe-centrum'));
test('toSlug strips leading and trailing hyphens', () => assertEqual(toSlug('  hello  '), 'hello'));

test('makeSlug uses id if present', () => {
  assertEqual(makeSlug({ id: 'my-custom-id', name: 'Something', city: 'Amsterdam' }), 'my-custom-id');
});
test('makeSlug combines city and name', () => {
  assertEqual(makeSlug({ id: '', name: 'Max Euwe Centrum', city: 'Amsterdam' }), 'amsterdam-max-euwe-centrum');
});
test('makeSlug works without city', () => {
  assertEqual(makeSlug({ id: '', name: 'Chess Board', city: '' }), 'chess-board');
});

test('all venues produce non-empty slugs', () => {
  const bad = VENUES.filter(v => !makeSlug(v));
  assert(bad.length === 0, `Empty slugs: ${bad.map(v => v.name).join(', ')}`);
});

test('no venue slug contains the word undefined', () => {
  const bad = VENUES.filter(v => makeSlug(v).includes('undefined'));
  assert(bad.length === 0, `Slugs with "undefined": ${bad.map(v => v.name).join(', ')}`);
});

test('no two venues share a slug', () => {
  const seen = new Map(), collisions = [];
  for (const v of VENUES) {
    const slug = makeSlug(v);
    if (seen.has(slug)) collisions.push(`"${v.name}" collides with "${seen.get(slug)}" (${slug})`);
    else seen.set(slug, v.name);
  }
  assert(collisions.length === 0, `Slug collisions:\n     ${collisions.join('\n     ')}`);
});

console.log('\n── Filter logic ─────────────────────────────────────────────');

const loc = { name: 'Test', labels: ['chess bar', 'chess meetup'], days: ['Monday', 'Wednesday'], city: 'Amsterdam' };

test('no filters — venue passes', () => assert(locMatchesFilters(loc, new Set(), new Set(), '')));
test('matching label — venue passes', () => assert(locMatchesFilters(loc, new Set(['chess bar']), new Set(), '')));
test('non-matching label — venue blocked', () => assert(!locMatchesFilters(loc, new Set(['chess club']), new Set(), '')));
test('matching day — venue passes', () => assert(locMatchesFilters(loc, new Set(), new Set(['Monday']), '')));
test('non-matching day — venue blocked', () => assert(!locMatchesFilters(loc, new Set(), new Set(['Friday']), '')));
test('null days passes any day filter', () => assert(locMatchesFilters({ ...loc, days: null }, new Set(), new Set(['Friday']), '')));
test('matching city — venue passes', () => assert(locMatchesFilters(loc, new Set(), new Set(), 'Amsterdam')));
test('non-matching city — venue blocked', () => assert(!locMatchesFilters(loc, new Set(), new Set(), 'Utrecht')));
test('label + day both match — venue passes', () => assert(locMatchesFilters(loc, new Set(['chess bar']), new Set(['Monday']), '')));
test('label matches but day does not — venue blocked', () => assert(!locMatchesFilters(loc, new Set(['chess bar']), new Set(['Friday']), '')));

// ─── SUMMARY ──────────────────────────────────────────────────────────────────
console.log(`\n── Results ───────────────────────────────────────────────────`);
console.log(`   ${passed} passed, ${failed} failed\n`);
process.exit(failed > 0 ? 1 : 0);
