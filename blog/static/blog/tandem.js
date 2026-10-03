/* Tandem homepage motion: smooth scroll (Lenis) + GSAP ScrollTrigger.
   If anything fails to load, or the visitor prefers reduced motion, the page
   simply shows its static layout (the "motion" class is removed). */
(function () {
  var root = document.documentElement;
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce || !window.gsap || !window.ScrollTrigger) {
    root.classList.remove('motion');
    return;
  }

  gsap.registerPlugin(ScrollTrigger);
  ScrollTrigger.config({ ignoreMobileResize: true });

  /* ---------- smooth scroll, synced with ScrollTrigger ---------- */
  var lenis = null;
  if (window.Lenis) {
    lenis = new Lenis({ lerp: 0.1, smoothWheel: true });
    lenis.on('scroll', ScrollTrigger.update);
    gsap.ticker.add(function (t) { lenis.raf(t * 1000); });
    gsap.ticker.lagSmoothing(0);
  }
  document.querySelectorAll('a[href^="#"]').forEach(function (a) {
    a.addEventListener('click', function (e) {
      var target = document.querySelector(a.getAttribute('href'));
      if (!target) return;
      e.preventDefault();
      if (lenis) lenis.scrollTo(target, { offset: -20 });
      else target.scrollIntoView({ behavior: 'smooth' });
    });
  });

  /* ---------- helpers ---------- */
  function wrapWords(node) {
    Array.prototype.slice.call(node.childNodes).forEach(function (n) {
      if (n.nodeType === 3) {
        var frag = document.createDocumentFragment();
        n.textContent.split(/(\s+)/).forEach(function (tok) {
          if (!tok) return;
          if (/^\s+$/.test(tok)) { frag.appendChild(document.createTextNode(' ')); return; }
          var mask = document.createElement('span');
          mask.className = 'w';
          var inner = document.createElement('span');
          inner.className = 'wi';
          inner.textContent = tok;
          mask.appendChild(inner);
          frag.appendChild(mask);
        });
        n.parentNode.replaceChild(frag, n);
      } else if (n.nodeType === 1) {
        wrapWords(n);
      }
    });
  }
  function words(el) { wrapWords(el); return el.querySelectorAll('.wi'); }

  /* ---------- nav + page progress ---------- */
  var nav = document.querySelector('.tm-nav');
  if (nav) {
    ScrollTrigger.create({
      start: 80, end: 99999,
      onToggle: function (self) { nav.classList.toggle('is-solid', self.isActive); }
    });
  }
  var bar = document.querySelector('.tm-progress i');
  if (bar) {
    gsap.to(bar, { scaleY: 1, ease: 'none', scrollTrigger: { start: 0, end: 'max', scrub: 0.3 } });
  }

  /* ---------- hero intro ---------- */
  var heroLines = document.querySelectorAll('[data-hero-words]');
  heroLines.forEach(function (el) {
    var w = words(el);
    gsap.set(w, { yPercent: 115 });
    gsap.set(el, { opacity: 1 });
    el._words = w;
  });
  var intro = gsap.timeline({ delay: 0.15 });
  intro.fromTo('.tm-hero-logo', { opacity: 0, scale: 0.94 }, { opacity: 1, scale: 1, duration: 1.8, ease: 'power3.out' }, 0);
  heroLines.forEach(function (el) {
    intro.to(el._words, { yPercent: 0, duration: 1.1, ease: 'power4.out', stagger: 0.08 }, 0.7);
  });
  document.querySelectorAll('[data-hero]:not([data-hero-words]):not(.tm-hero-logo)').forEach(function (el, i) {
    if (el.hasAttribute('data-hero-o')) {
      intro.fromTo(el, { opacity: 0 }, { opacity: 1, duration: 1, ease: 'power2.out' }, 1.5);
    } else {
      intro.fromTo(el, { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: 1, ease: 'power2.out' }, 0.5 + i * 0.5);
    }
  });
  gsap.to('.tm-hero-inner', {
    yPercent: -10, opacity: 0, ease: 'none',
    scrollTrigger: { trigger: '.tm-hero', start: 'top top', end: 'bottom top', scrub: true }
  });

  /* ---------- manifesto: words light up as you scroll ---------- */
  var manifesto = document.querySelector('.tm-manifesto .big');
  if (manifesto) {
    gsap.fromTo(words(manifesto), { opacity: 0.16 }, {
      opacity: 1, ease: 'none', stagger: 0.12,
      scrollTrigger: { trigger: '.tm-manifesto', start: 'top 72%', end: 'bottom 58%', scrub: true }
    });
  }

  /* ---------- generic fade-up reveals ---------- */
  gsap.utils.toArray('.reveal').forEach(function (el) {
    gsap.to(el, {
      opacity: 1, y: 0, duration: 1, ease: 'power3.out',
      scrollTrigger: { trigger: el, start: 'top 86%' }
    });
  });

  /* ---------- pinned four-chapter story ---------- */
  var story = document.querySelector('#story');
  if (story) {
    var stage = story.querySelector('.story-stage');
    var chapters = gsap.utils.toArray('.chapter', story);
    var n = chapters.length;
    var frame = story.querySelector('.story-frame');
    var skies = story.querySelectorAll('.sky');
    var sun = story.querySelector('.sun');
    var ridges = story.querySelectorAll('.ridge');
    var bars = story.querySelectorAll('.story-progress i');
    var counter = story.querySelector('.story-index .cur');

    /* Optional image sequence: set data-count on <canvas id="seq"> once frames exist. */
    var seq = document.getElementById('seq');
    var frameCount = seq ? parseInt(seq.getAttribute('data-count') || '0', 10) : 0;
    var imgs = [];
    function drawFrame(i) {
      var im = imgs[i];
      if (!im || !im.complete || !im.naturalWidth) return;
      var w = seq.clientWidth, h = seq.clientHeight, dpr = Math.min(window.devicePixelRatio || 1, 2);
      if (seq.width !== w * dpr) { seq.width = w * dpr; seq.height = h * dpr; }
      var ctx = seq.getContext('2d');
      var s = Math.max(seq.width / im.naturalWidth, seq.height / im.naturalHeight);
      var dw = im.naturalWidth * s, dh = im.naturalHeight * s;
      ctx.drawImage(im, (seq.width - dw) / 2, (seq.height - dh) / 2, dw, dh);
    }
    if (seq && frameCount > 0) {
      frame.classList.add('has-frames');
      var base = seq.getAttribute('data-base');
      for (var i = 1; i <= frameCount; i++) {
        var im = new Image();
        im.src = base + 'frame_' + String(i).padStart(4, '0') + '.jpg';
        if (i === 1) im.onload = function () { drawFrame(0); };
        imgs.push(im);
      }
    }

    skies.forEach(function (s, i) { gsap.set(s, { opacity: i === 0 ? 1 : 0 }); });
    chapters.forEach(function (c, i) { gsap.set(c, { autoAlpha: i === 0 ? 1 : 0 }); });
    gsap.set(sun, { yPercent: 190 });

    var tl = gsap.timeline({
      defaults: { ease: 'none' },
      onUpdate: function () {
        var idx = Math.min(n - 1, Math.max(0, Math.floor(tl.time() + 0.35)));
        if (counter) counter.textContent = '0' + (idx + 1);
        if (frameCount > 0) drawFrame(Math.round(tl.progress() * (frameCount - 1)));
      },
      scrollTrigger: {
        trigger: story, start: 'top top', end: '+=' + (n * 85) + '%',
        pin: stage, scrub: 1, anticipatePin: 1
      }
    });

    chapters.forEach(function (c, i) {
      if (i > 0) tl.fromTo(c, { autoAlpha: 0, y: 46 }, { autoAlpha: 1, y: 0, duration: 0.35 }, i - 0.15);
      if (i < n - 1) tl.to(c, { autoAlpha: 0, y: -46, duration: 0.35 }, i + 0.65);
      if (bars[i]) tl.fromTo(bars[i], { scaleX: 0 }, { scaleX: 1, duration: 1 }, i);
    });
    skies.forEach(function (s, i) { if (i > 0) tl.to(s, { opacity: 1, duration: 0.9 }, i - 0.5); });
    /* sun: low at dawn -> high at noon -> lower -> sinks behind the ridges at sunset */
    tl.to(sun, { yPercent: 0, duration: 1 }, 0)
      .to(sun, { yPercent: 95, duration: 1 }, 1.4)
      .to(sun, { yPercent: 210, duration: 1 }, 2.4);
    ridges.forEach(function (r, i) {
      tl.fromTo(r, { yPercent: 0 }, { yPercent: -5 * (i + 1), duration: n }, 0);
    });
    tl.to({}, { duration: 0.5 }, n - 1 + 0.2); /* hold on the last chapter */
  }

  /* ---------- horizontal menu strip (desktop only; swipeable on phones) ---------- */
  var menu = document.querySelector('#menu');
  if (menu) {
    var track = menu.querySelector('.tm-track');
    ScrollTrigger.matchMedia({
      '(min-width: 768px)': function () {
        function dist() { return Math.max(0, track.scrollWidth - window.innerWidth); }
        gsap.to(track, {
          x: function () { return -dist(); }, ease: 'none',
          scrollTrigger: {
            trigger: menu, start: 'top top', end: function () { return '+=' + dist(); },
            pin: true, scrub: 1, invalidateOnRefresh: true
          }
        });
      }
    });
  }

  /* layout can shift once web fonts arrive */
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { ScrollTrigger.refresh(); });
  window.addEventListener('load', function () { ScrollTrigger.refresh(); });
})();
