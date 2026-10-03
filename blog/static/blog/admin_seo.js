/* Live Google preview, character counters and an SEO checklist for the post editor.
   Plain JavaScript, no libraries. Everything is computed in the writer's browser. */
(function () {
  'use strict';
  function $(id) { return document.getElementById(id); }
  function init() {
  var title = $('id_title'), seo = $('id_seo_title'), meta = $('id_meta_description'),
      slug = $('id_slug'), kw = $('id_focus_keyword'), excerpt = $('id_excerpt');
  if (!title || !seo || !meta) return;

  function counter(input, min, max, unit) {
    var el = document.createElement('div');
    el.className = 'seo-count';
    input.parentNode.appendChild(el);
    function update() {
      var n = input.value.length;
      var state = n === 0 ? '' : (n < min ? 'bad' : (n > max ? 'bad' : 'good'));
      el.className = 'seo-count ' + state;
      el.textContent = n + ' characters. Aim for ' + min + '-' + max + (unit || '') + '.';
    }
    input.addEventListener('input', update);
    update();
  }
  counter(seo, 40, 60);
  counter(meta, 110, 155);

  var panel = document.createElement('div');
  panel.id = 'seo-panel';
  panel.innerHTML = '<h3>How this will look on Google</h3><div class="serp"><div class="url"></div>' +
    '<div class="ttl"></div><div class="dsc"></div></div>' +
    '<h3>SEO checklist</h3><p class="score"></p><ul class="checks"></ul>';
  var fieldset = seo.closest('fieldset');
  var firstRow = fieldset && fieldset.querySelector('.form-row');
  if (fieldset && firstRow) fieldset.insertBefore(panel, firstRow);
  else seo.parentNode.parentNode.insertBefore(panel, seo.parentNode);

  var urlEl = panel.querySelector('.url'), ttlEl = panel.querySelector('.ttl'),
      dscEl = panel.querySelector('.dsc'), listEl = panel.querySelector('.checks'),
      scoreEl = panel.querySelector('.score');

  function clip(text, n) { text = (text || '').trim(); return text.length > n ? text.slice(0, n - 1).trim() + '…' : text; }
  function bodyHtml() {
    var ed = document.querySelector('.ck-editor__editable');
    if (ed && ed.ckeditorInstance) return ed.ckeditorInstance.getData();
    var ta = $('id_body');
    return ta ? ta.value : '';
  }
  function words(text) { var t = text.replace(/\s+/g, ' ').trim(); return t ? t.split(' ') : []; }

  function run() {
    var html = bodyHtml();
    var box = document.createElement('div');
    box.innerHTML = html;
    var plain = box.textContent || '';
    var all = words(plain);
    var firstPara = box.querySelector('p');
    var first100 = words(firstPara ? firstPara.textContent : plain).slice(0, 100).join(' ').toLowerCase();
    var headline = (seo.value || (title.value ? title.value + ' — Tandem Journal' : '')).trim();
    var desc = (meta.value || (excerpt ? excerpt.value : '')).trim();
    var keyword = (kw.value || '').trim().toLowerCase();
    var slugText = (slug.value || '').toLowerCase();

    urlEl.textContent = 'tandemretreat.com › blog › ' + (slug.value || 'your-post-address');
    ttlEl.textContent = clip(headline, 60) || 'Your headline appears here';
    dscEl.textContent = clip(desc, 155) || 'Your description appears here. Write 120-155 characters that make people want to click.';

    var checks = [];
    function add(ok, text, level) { checks.push({ ok: ok, text: text, level: level || (ok ? 'ok' : 'warn') }); }

    var tl = headline.length;
    add(tl >= 30 && tl <= 60, 'Google title is ' + tl + ' characters (aim for 30-60).');
    var dl = desc.length;
    add(dl >= 110 && dl <= 160, 'Google description is ' + dl + ' characters (aim for 110-160).');
    add(all.length >= 300, 'Story has ' + all.length + ' words (300+ is a healthy minimum; guides often do better at 800+).');
    add(box.querySelectorAll('h2').length >= 1, 'Story has at least one heading (use "Heading" in the toolbar to break up long text).');

    var imgs = box.querySelectorAll('img');
    var noAlt = 0;
    imgs.forEach(function (im) { if (!(im.getAttribute('alt') || '').trim()) noAlt++; });
    if (imgs.length) add(noAlt === 0, noAlt === 0 ? 'All ' + imgs.length + ' image(s) have a description.' : noAlt + ' of ' + imgs.length + ' image(s) have no description (click the image, then the "text alternative" button).');
    else add(false, 'No images in the story yet. Pictures keep readers and help Google Images.', 'info');

    var internal = 0;
    box.querySelectorAll('a[href]').forEach(function (a) {
      var h = a.getAttribute('href') || '';
      if (h.charAt(0) === '/' || h.indexOf('tandemretreat.com') !== -1) internal++;
    });
    add(internal >= 1, internal ? internal + ' link(s) to other Tandem pages.' : 'No links to other Tandem pages yet. Link to a related post or the homepage.');

    if (!keyword) {
      add(false, 'Add a main keyword above to unlock the keyword checks.', 'info');
    } else {
      add(headline.toLowerCase().indexOf(keyword) !== -1, 'Main keyword appears in the Google title.');
      add(slugText.indexOf(keyword.replace(/\s+/g, '-')) !== -1, 'Main keyword appears in the web address.');
      add(desc.toLowerCase().indexOf(keyword) !== -1, 'Main keyword appears in the Google description.');
      add(first100.indexOf(keyword) !== -1, 'Main keyword appears in the first paragraph.');
    }

    var scored = checks.filter(function (c) { return c.level !== 'info'; });
    var passed = scored.filter(function (c) { return c.ok; }).length;
    scoreEl.textContent = passed + ' of ' + scored.length + ' checks passed';
    listEl.innerHTML = '';
    checks.forEach(function (c) {
      var li = document.createElement('li');
      li.className = c.level;
      li.textContent = c.text;
      listEl.appendChild(li);
    });
  }

  [title, seo, meta, slug, kw, excerpt].forEach(function (el) { if (el) el.addEventListener('input', run); });
  run();

  // The editor starts a moment after the page; hook into it when ready, and keep a slow safety refresh.
  var tries = 0;
  var wait = setInterval(function () {
    var ed = document.querySelector('.ck-editor__editable');
    if (ed && ed.ckeditorInstance) {
      clearInterval(wait);
      ed.ckeditorInstance.model.document.on('change:data', run);
      run();
    } else if (++tries > 60) {
      clearInterval(wait);
    }
  }, 300);
  setInterval(run, 4000);
  }
  /* Django loads this file in the page <head>, before the form exists: wait for the page. */
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
