// Scriptable is an iOS host. This harness executes its JavaScript and records
// the documented widget calls; it does not emulate WidgetKit's native renderer.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const fixture = Object.freeze({
  aggiornato_alle: '2026-11-12T12:10:00Z',
  ticket_aperti: 7,
  ticket_nuovi_oggi: 2,
  aziende_registrate: 103,
  aziende_in_prova: 11,
  aziende_abbonate: 37,
  nuove_aziende_mese: 5,
  mrr_stimato: 1184.5,
  giri_in_corso: 8,
  giri_oggi: 24,
  errori_24h: 3,
});

function walk(root) {
  return root ? [root, ...(root.children || []).flatMap(walk)] : [];
}

function texts(root) {
  return walk(root).filter(node => node.type === 'text').map(node => node.text);
}

async function runWidget({
  family = 'large', width = 390, height = 844, data = fixture, status = 200,
  networkError = null, runsInWidget = true, now = '2026-11-12T12:11:00Z',
  url = 'https://girofacile.example', key = 'gfw_test_only_not_a_real_key', source,
} = {}) {
  const widgets = [];
  const requests = [];
  const presented = [];
  let selectedWidget;
  let complete = false;

  class Node {
    constructor(type, properties = {}) {
      this.type = type;
      this.children = [];
      this.direction = type === 'widget' ? 'vertical' : 'horizontal';
      Object.assign(this, properties);
    }
    addStack() { const node = new Node('stack'); this.children.push(node); return node; }
    addText(value) { const node = new Node('text', {text: String(value)}); this.children.push(node); return node; }
    addImage(image) { const node = new Node('image', {image}); this.children.push(node); return node; }
    addSpacer(length = null) { const node = new Node('spacer', {length}); this.children.push(node); return node; }
    layoutVertically() { this.direction = 'vertical'; }
    layoutHorizontally() { this.direction = 'horizontal'; }
    centerAlignContent() { this.alignment = 'center'; }
    topAlignContent() { this.alignment = 'top'; }
    bottomAlignContent() { this.alignment = 'bottom'; }
    setPadding(...padding) { this.padding = padding; }
  }
  class ListWidget extends Node {
    constructor() { super('widget'); widgets.push(this); }
    async presentLarge() { presented.push('large'); }
    async presentMedium() { presented.push('medium'); }
    async presentSmall() { presented.push('small'); }
  }
  class Color {
    constructor(hex, alpha = 1) { this.hex = '#' + hex.replace(/^#/, ''); this.alpha = alpha; }
    static white() { return new Color('ffffff'); }
    static black() { return new Color('000000'); }
  }
  class Size {
    constructor(width, height) { this.width = width; this.height = height; }
  }
  class Request {
    constructor(url) { this.url = url; requests.push(this); }
    async loadJSON() {
      if (networkError) throw networkError;
      this.response = {statusCode: status};
      return data;
    }
  }
  class Clock extends Date {
    constructor(...arguments_) { super(...(arguments_.length ? arguments_ : [now])); }
    static now() { return new Date(now).getTime(); }
  }
  const Font = Object.fromEntries([
    'boldRoundedSystemFont', 'mediumSystemFont', 'heavySystemFont', 'systemFont',
    'semiboldSystemFont', 'boldSystemFont',
  ].map(name => [name, size => ({name, size})]));
  const context = vm.createContext({
    ListWidget, Color, Size, Request, Font, Date: Clock, Intl,
    SFSymbol: {named: name => ({image: {symbol: name}})},
    Device: {screenSize: () => new Size(width, height)},
    config: {widgetFamily: family, runsInWidget},
    Script: {
      setWidget(widget) { selectedWidget = widget; },
      complete() { complete = true; },
    },
  });
  const template = source ?? fs.readFileSync(path.resolve(__dirname, '../../static/admin/widget-scriptable.js'), 'utf8');
  const script = template.replace('__GF_URL__', url).replace('__GF_KEY__', key);
  await vm.runInContext('(async () => {\n' + script + '\n})()', context, {filename: 'widget-scriptable.js'});
  return {widget: selectedWidget || widgets[0], requests, presented, complete};
}

module.exports = {runWidget, walk, texts, fixture};
