/* =========================================================================
   symblic-learn.js — Symblic Academy & Mastery Learning Platform
   Full interactive tutorial, active recall flashcards with SM-2 spaced
   repetition, cloze fill-in-the-blanks, single-line syntax drills, deep
   epistemic quizzes, guided projects, and live kernel playground.

   The learning page of the original host, kept as static files. It reads
   its course and source catalog from symblic-academy-content.js and its
   page library from the host (/studio.js) or, without one, from
   ../hub/standalone-shell.js (Studio.standalone is then true). Progress
   stays in this browser's localStorage. The research reader fetches catalog
   documents as static files ("../.." + the repository path in the catalog),
   so the repository root has to be served. HOST-ONLY: checking and
   previewing programs (Projects, Playground) call the host API
   (/api/automation/symblic/check and /preview); in the static copy those
   buttons say so and send nothing. Written by AI agents; see README.md.
   ========================================================================= */

(function () {
  'use strict';

  const { $, esc, att, toast, api } = Studio;
  const API = '/api/automation/symblic/';
  // Without the host's page library there is no host API: checking and preview say so instead of failing
  // silently or showing an invented result.
  const HOST_API = !Studio.standalone;
  const NEEDS_HOST = 'Not checked. Checking and capsule preview call the host API (/api/automation/symblic/check and '
    + '/preview, served by integration/host/symblic_engine.py), which this static copy does not have; nothing was sent. '
    + 'From a checkout of the repository, save the program as FILE.sym and run tools/symblic check FILE.sym '
    + '(diagnostics and plan) or tools/symblic preview FILE.sym (the request a model would be sent); '
    + 'neither calls a model.';
  const HOST_LABEL = HOST_API ? '' : ' (needs a host)';

  function needsHost(resultEl, statusEl) {
    resultEl.style.display = 'block';
    resultEl.textContent = NEEDS_HOST;
    resultEl.style.border = '1px solid var(--warn)';
    if (statusEl) statusEl.textContent = 'Needs the host API';
  }

  function staticSpecificationScore(value) {
    const score = Number.isFinite(value) ? `${value} / 100` : 'unavailable';
    return `Static specification heuristic: ${score}. Text/type cues, with exact statements scored 100; not measured model reliability.`;
  }

  // ---------------------------------------------------------------------------
  // Zero-to-Mastery Course State & Curriculum
  // ---------------------------------------------------------------------------
  const MASTERY_KEY = 'symblic_mastery_v1';
  let MASTERY_STATE = {
    lvl: 0,
    bite: 0,
    completed: {}, // 'lvl-bite' -> true
    xp: 0,
    streak: 0
  };
  try {
    const raw = localStorage.getItem(MASTERY_KEY);
    if (raw) MASTERY_STATE = Object.assign(MASTERY_STATE, JSON.parse(raw));
  } catch (_) {}

  function saveMastery() {
    try { localStorage.setItem(MASTERY_KEY, JSON.stringify(MASTERY_STATE)); } catch (_) {}
  }

  const CONTENT = window.SymblicAcademyContent;
  if (!CONTENT?.levels?.length) {
    document.body.textContent = 'The expanded academy content could not load. Reload this page to retry.';
    return;
  }
  const MASTERY_LEVELS = CONTENT.levels;
  // Catalog URLs are repository paths ("/docs/reference/SPEC.md") or external https links. Documents under these
  // roots open in the research reader; other repository files open directly; external links stay as they are.
  const READING_ROOTS = ['/docs/', '/examples/', '/benchmarks/', '/kits/'];
  const isRepoPath = url => typeof url === 'string' && url.startsWith('/') && !url.startsWith('//');
  // This page is web/academy/index.html, two folders below the repository root.
  const repoHref = url => '../..' + url.split('/').map(encodeURIComponent).join('/');
  function readingURL(url) {
    if (READING_ROOTS.some(root => String(url).startsWith(root)))
      return 'index.html?reading=' + encodeURIComponent(url) + '#research';
    if (isRepoPath(url)) return repoHref(url);
    return /^https?:\/\//i.test(String(url)) ? url : '#research';
  }

  // SHA-256 of fetched bytes as hex, or null where crypto.subtle is missing (browsers offer it on https and localhost).
  async function sha256Hex(bytes) {
    try {
      if (!window.crypto || !window.crypto.subtle) return null;
      const digest = new Uint8Array(await window.crypto.subtle.digest('SHA-256', bytes));
      return Array.from(digest, b => b.toString(16).padStart(2, '0')).join('');
    } catch (_) { return null; }
  }

  function renderMasteryPathway(m) {
    const curLvlIx = Math.max(0, Math.min(MASTERY_LEVELS.length - 1, MASTERY_STATE.lvl));
    const lvl = MASTERY_LEVELS[curLvlIx];
    const curBiteIx = Math.max(0, Math.min(lvl.bites.length - 1, MASTERY_STATE.bite));
    const bite = lvl.bites[curBiteIx];

    const biteKey = `${curLvlIx}-${curBiteIx}`;
    const isCompleted = !!MASTERY_STATE.completed[biteKey];
    let practiceMode = false;

    // Compute total progress
    let totalBites = 0, doneBites = 0;
    MASTERY_LEVELS.forEach((l, li) => {
      l.bites.forEach((b, bi) => {
        totalBites++;
        if (MASTERY_STATE.completed[`${li}-${bi}`]) doneBites++;
      });
    });
    const pct = totalBites > 0 ? Math.round((doneBites / totalBites) * 100) : 0;

    // Ranks based on XP
    const xp = MASTERY_STATE.xp || 0;
    let rank = '🌱 Novice Explorer';
    if (xp >= 250) rank = '👑 Symblic Master';
    else if (xp >= 180) rank = '🧠 Epistemic Architect';
    else if (xp >= 120) rank = '🛡️ Invariant Guardian';
    else if (xp >= 60) rank = '⚡ Syntax Apprentice';

    m.innerHTML = `
      <div class="sl-mastery-container">
        <!-- Top HUD -->
        <div class="sl-mastery-hud">
          <div class="sl-hud-rank">
            <span>${esc(rank)}</span>
            <span style="font-weight:400;font-size:12px;color:var(--tx3);">· ${doneBites}/${totalBites} Bites (${pct}%)</span>
          </div>
          <div class="sl-hud-stats">
            <span class="sl-hud-xp">🏆 ${xp} XP</span>
            <span class="sl-hud-streak">🔥 Streak: ${MASTERY_STATE.streak || 0}</span>
          </div>
          <div class="sl-track-progress-bar">
            <div class="sl-track-progress-fill" style="width:${pct}%;"></div>
          </div>
        </div>

        <!-- Level Selector Pills -->
        <div class="sl-level-selector" id="slLvlSelector">
          ${MASTERY_LEVELS.map((l, idx) => `
            <button class="sl-level-pill ${idx === curLvlIx ? 'active' : ''}" data-lvl="${idx}">
              ${idx} · ${esc(l.title.split(': ').slice(1).join(': '))}
            </button>
          `).join('')}
        </div>

        <!-- Bite Card -->
        <div class="sl-bite-card" id="slBiteCard">
          <div class="sl-bite-header">
            <span class="sl-bite-badge">Level ${curLvlIx} · Bite ${curBiteIx + 1} of ${lvl.bites.length}</span>
            <div class="sl-bite-dots">
              ${lvl.bites.map((_, bi) => {
                const k = `${curLvlIx}-${bi}`;
                const done = !!MASTERY_STATE.completed[k];
                const active = bi === curBiteIx;
                return `<span class="sl-bite-dot ${active ? 'active' : (done ? 'done' : '')}"></span>`;
              }).join('')}
            </div>
          </div>

          <div class="sl-bite-title" role="heading" aria-level="2">${esc(bite.title)}</div>

          <p class="sl-course-purpose">${esc(lvl.desc)}</p>
          <label class="sl-bite-picker">Choose a concept
            <select id="slBitePicker">${lvl.bites.map((b, i) => `<option value="${i}" ${i === curBiteIx ? 'selected' : ''}>${MASTERY_STATE.completed[`${curLvlIx}-${i}`] ? '✓ ' : ''}${i + 1}. ${esc(b.title)}</option>`).join('')}</select>
          </label>

          <div class="sl-bite-concept">
            ${esc(bite.concept)}
          </div>

          ${bite.metaphor ? `
            <div class="sl-bite-metaphor">
              <b>💡 Everyday Analogy:</b> ${esc(bite.metaphor)}
            </div>
          ` : ''}

          ${bite.code ? `
            <div class="sl-bite-code">${esc(bite.code)}</div>
          ` : ''}

          ${bite.worked ? `<section class="sl-worked-example"><h3>Worked example</h3>
            <ol>${bite.worked.steps.map(s => `<li>${esc(s)}</li>`).join('')}</ol>
            <p class="sl-scope-note"><strong>What this establishes:</strong> ${esc(bite.worked.takeaway)}</p>
          </section>` : ''}

          <!-- Interactive Checkpoint -->
          ${isCompleted ? '<button class="sl-btn-nav" id="slPractiseAgain">Practise this checkpoint again</button>' : ''}
          <div class="sl-checkpoint-box">
            <div class="sl-checkpoint-header">
              <span>⚡ Quick Checkpoint</span>
              <span style="opacity:0.7;">· Test your understanding immediately</span>
            </div>
            <div class="sl-checkpoint-q">${esc(bite.question)}</div>
            <div class="sl-checkpoint-opts" id="slCpOpts">
              ${bite.options.map((opt, oi) => {
                let cls = 'sl-checkpoint-opt';
                if (isCompleted) {
                  cls += ' locked';
                  if (oi === bite.ans) cls += ' correct';
                }
                return `
                  <button class="${cls}" data-opt="${oi}">
                    <span style="font-family:var(--mono);font-size:11px;font-weight:700;opacity:0.7;">
                      ${String.fromCharCode(65 + oi)}
                    </span>
                    <span>${esc(opt)}</span>
                  </button>
                `;
              }).join('')}
            </div>
            <div class="sl-checkpoint-feedback" id="slCpFeedback" style="display:${isCompleted ? 'block' : 'none'};">
              <b>${isCompleted ? '✓ Completed!' : ''}</b>
              <div style="margin-top:4px;">${esc(bite.explanation)}</div>
            </div>
          </div>

          ${bite.reflection ? `<section class="sl-transfer"><h3>Apply it to a new case</h3>
            <p>${esc(bite.reflection.prompt)}</p>
            <label for="slTransferDraft">Your explanation (saved on this browser)</label>
            <textarea id="slTransferDraft" rows="4" placeholder="Explain the mechanism, apply it, and state the limit…"></textarea>
            <span id="slDraftStatus" role="status"></span>
            <details><summary>Compare with a worked explanation</summary><p>${esc(bite.reflection.model)}</p>
              <p>Self-check: which assumption, step or limit did your explanation miss? Revise that part before moving on.</p></details>
          </section>` : ''}
          <section class="sl-lesson-sources"><h3>Follow the evidence</h3>
            ${(bite.references || []).map(r => `<a href="${att(readingURL(r.url))}" target="_blank" rel="noopener noreferrer">${esc(r.title)}</a>`).join('')}
            <p>Research essays can contain proposals and historical claims. Use the lesson’s scope notes and current language contracts when assessing them.</p>
          </section>

          <!-- Bottom Footer Navigation -->
          <div class="sl-bite-footer">
            <button class="sl-btn-nav" id="slBtnPrev" ${curLvlIx === 0 && curBiteIx === 0 ? 'disabled' : ''}>
              ← Previous Bite
            </button>
            <div style="font-family:var(--mono);font-size:12px;color:var(--tx3);">
              Bite ${curBiteIx + 1}/${lvl.bites.length}
            </div>
            <button class="sl-btn-nav sl-btn-next ${isCompleted ? 'glow' : ''}" id="slBtnNext" ${!isCompleted ? 'disabled' : ''}>
              ${curBiteIx === lvl.bites.length - 1 && curLvlIx === MASTERY_LEVELS.length - 1 ? '🎉 Course Completed!' : 'Next Concept →'}
            </button>
          </div>
        </div>
      </div>
    `;

    // Wire Level selector pills
    const picker = $('slBitePicker');
    if (picker) picker.onchange = () => { MASTERY_STATE.bite = Number(picker.value); saveMastery(); renderMasteryPathway(m); };
    const draft = $('slTransferDraft');
    if (draft) {
      const key = 'symblic_transfer_v2:' + biteKey;
      try { draft.value = localStorage.getItem(key) || ''; } catch (_) {}
      draft.oninput = () => {
        try { localStorage.setItem(key, draft.value); $('slDraftStatus').textContent = 'Saved on this browser.'; }
        catch (_) { $('slDraftStatus').textContent = 'Browser storage unavailable; copy your explanation before leaving.'; }
      };
    }
    m.querySelectorAll('.sl-level-pill').forEach(btn => {
      btn.onclick = () => {
        MASTERY_STATE.lvl = parseInt(btn.dataset.lvl, 10);
        MASTERY_STATE.bite = 0;
        saveMastery();
        renderMasteryPathway(m);
      };
    });

    // Wire Checkpoint options
    const optBtns = m.querySelectorAll('.sl-checkpoint-opt');
    const feedbackEl = $('slCpFeedback');
    const nextBtn = $('slBtnNext');
    const practise = $('slPractiseAgain');
    if (practise) practise.onclick = () => {
      practiceMode = true;
      optBtns.forEach(b => b.classList.remove('locked', 'correct', 'wrong'));
      feedbackEl.style.display = 'none';
      practise.hidden = true;
    };

    optBtns.forEach(btn => {
      btn.onclick = () => {
        if (MASTERY_STATE.completed[biteKey] && !practiceMode) return;
        const chosen = parseInt(btn.dataset.opt, 10);
        const isRight = (chosen === bite.ans);

        if (isRight) {
          btn.classList.add('correct');
          optBtns.forEach(b => b.classList.add('locked'));
          if (feedbackEl) {
            feedbackEl.className = 'sl-checkpoint-feedback correct';
            feedbackEl.innerHTML = `<b>${isCompleted ? '✓ Practice complete' : '✓ Correct! +10 XP'}</b><div style="margin-top:4px;">${esc(bite.explanation)}</div>`;
            feedbackEl.style.display = 'block';
          }

          if (!MASTERY_STATE.completed[biteKey]) {
            MASTERY_STATE.completed[biteKey] = true;
            MASTERY_STATE.xp = (MASTERY_STATE.xp || 0) + 10;
            MASTERY_STATE.streak = (MASTERY_STATE.streak || 0) + 1;
            saveMastery();
          }
          practiceMode = false;

          if (nextBtn) {
            nextBtn.removeAttribute('disabled');
            nextBtn.classList.add('glow');
          }
          toast(isCompleted ? 'Practice complete.' : 'Correct! +10 XP earned 🏆');
          if (navigator.vibrate) navigator.vibrate([15, 30, 20]);
        } else {
          btn.classList.add('wrong');
          if (feedbackEl) {
            feedbackEl.className = 'sl-checkpoint-feedback wrong';
            feedbackEl.innerHTML = `<b>Not quite.</b><div style="margin-top:4px;">${esc(bite.feedback?.[chosen] || bite.hint || 'Review the explanation above and try another option!')}</div>`;
            feedbackEl.style.display = 'block';
          }
          MASTERY_STATE.streak = 0;
          saveMastery();
          if (navigator.vibrate) navigator.vibrate(60);
        }
      };
    });

    // Wire Previous button
    const prevBtn = $('slBtnPrev');
    if (prevBtn) {
      prevBtn.onclick = () => {
        if (curBiteIx > 0) {
          MASTERY_STATE.bite--;
        } else if (curLvlIx > 0) {
          MASTERY_STATE.lvl--;
          MASTERY_STATE.bite = MASTERY_LEVELS[MASTERY_STATE.lvl].bites.length - 1;
        }
        saveMastery();
        renderMasteryPathway(m);
      };
    }

    // Wire Next button
    if (nextBtn) {
      nextBtn.onclick = () => {
        if (!MASTERY_STATE.completed[biteKey]) return;
        if (curBiteIx < lvl.bites.length - 1) {
          MASTERY_STATE.bite++;
        } else if (curLvlIx < MASTERY_LEVELS.length - 1) {
          MASTERY_STATE.lvl++;
          MASTERY_STATE.bite = 0;
        } else {
          toast('Congratulations! You have completed all levels in Symblic Academy! 🎓');
          return;
        }
        saveMastery();
        renderMasteryPathway(m);
      };
    }
  }

  // ---------------------------------------------------------------------------
  // Spaced Repetition (SM-2) Local Storage Store
  // ---------------------------------------------------------------------------
  const SM2_KEY = 'symblic_learn_sm2_v1';
  let SM2_DATA = {};
  try {
    SM2_DATA = JSON.parse(localStorage.getItem(SM2_KEY) || '{}');
  } catch (_) { SM2_DATA = {}; }

  function saveSM2() {
    try { localStorage.setItem(SM2_KEY, JSON.stringify(SM2_DATA)); } catch (_) {}
  }

  function getCardState(cardId) {
    if (!SM2_DATA[cardId]) {
      SM2_DATA[cardId] = { reps: 0, interval: 0, ease: 2.5, nextReview: 0, history: [] };
    }
    return SM2_DATA[cardId];
  }

  function rateCard(cardId, rating) {
    // rating: 1 (Again), 2 (Hard), 3 (Good), 4 (Easy)
    const st = getCardState(cardId);
    const now = Date.now();
    st.history.push({ time: now, rating });

    if (rating === 1) {
      st.reps = 0;
      st.interval = 1; // 1 min (scaled)
    } else if (rating === 2) {
      st.interval = Math.max(1, Math.round(st.interval * 1.2));
      st.ease = Math.max(1.3, st.ease - 0.15);
    } else if (rating === 3) {
      st.reps += 1;
      st.interval = st.reps === 1 ? 1 : (st.reps === 2 ? 6 : Math.round(st.interval * st.ease));
    } else if (rating === 4) {
      st.reps += 1;
      st.interval = st.reps === 1 ? 4 : Math.round(st.interval * st.ease * 1.3);
      st.ease += 0.15;
    }
    st.nextReview = now + (st.interval * 60 * 1000);
    saveSM2();
  }

  // ---------------------------------------------------------------------------
  // Flashcard Deck (Active Recall & Memory Solidification)
  // ---------------------------------------------------------------------------
  const FLASHCARDS = [
    {
      id: 'fc-01',
      cat: 'Syntax',
      q: 'How can you name a Symblic program, and what punctuation terminates statements?',
      a: 'Use the optional `program Name.` header to name a program. Statements end with an optional period (`.`). Lines can continue when brackets/strings are open, with a trailing backslash, or starting with `with`, `from`, `by`, `where`, or `for each`.',
      code: 'program InvoiceAuditor.\nlet tax_rate = 8 / 100.'
    },
    {
      id: 'fc-02',
      cat: 'Kernel',
      q: "Why does exact rational arithmetic help?",
      a: "It represents supported ratios exactly, so 1/10 + 2/10 = 3/10 without binary rounding. Measurement uncertainty, specification mistakes and approximate operations remain separate issues.",
      code: ''
    },
    {
      id: 'fc-03',
      cat: 'Kernel',
      q: 'What is the maximum integer digit limit in Symblic, and why does this bound exist?',
      a: 'MAX_DIGITS = 4000 bounds supported integer representations. Digit, work and process limits help contain resource use; a digit limit alone does not prove every operation safe or fast.',
      code: '# Numerators and denominators are subject to the supported digit bound'
    },
    {
      id: 'fc-04',
      cat: 'Models',
      q: "What does a capsule control?",
      a: "It makes the context supplied to an ask explicit. Include the inputs, definitions and evidence the task needs; missing referents can make a small capsule inadequate. Isolation does not guarantee attention or remove every prompt-injection risk.",
      code: ''
    },
    {
      id: 'fc-05',
      cat: 'Models',
      q: 'What happens under the hood during `ensure cond else retry` when the condition fails?',
      a: 'The runner restores internal state at the anchor `ask`, adds rejected-answer feedback and retries within its budget. External effects are fenced separately: restoring internal state cannot undo an action already performed.',
      code: 'ask legs: Int in 0..20 "How many legs does a spider have?" with effort=low\nensure legs = 8 else retry because "a spider has eight legs".'
    },
    {
      id: 'fc-06',
      cat: 'Models',
      q: 'What does `effort=ultra` do during an `ask` statement?',
      a: 'It samples 5 candidate answers from applicators. Then, in a second round, it presents up to 6 anonymized candidate answers with their reasoning to the applicators as a peer-review jury. The jury\'s deliberation round determines the final consensus.',
      code: 'ask classification: one of {safe, warning, critical} "Evaluate safety" with effort=ultra, agree=0.8'
    },
    {
      id: 'fc-07',
      cat: 'Datalog',
      q: 'How does Symblic handle relational knowledge and multi-hop graph queries?',
      a: 'Through an embedded Datalog engine with stratified negation. `fact` records ground relations; `rule` defines Horn clauses with logic variables (capital letters); `query` retrieves matching bindings without contacting any AI model.',
      code: 'fact parent(ada, ben).\nfact parent(ben, cleo).\nrule ancestor(X, Y) if parent(X, Y).\nrule ancestor(X, Z) if parent(X, Y) and ancestor(Y, Z).\nlet ans = query ancestor(Who, cleo).'
    },
    {
      id: 'fc-08',
      cat: 'Kernel',
      q: 'How are transcendental functions (sin, cos, exp, ln, sqrt) evaluated in the Kernel?',
      a: 'Supported transcendentals use a fixed Decimal implementation, with 40-digit working precision and half-even rounding to 30 places. These are approximations. Reproducibility claims depend on the pinned implementation and tested platforms.',
      code: 'let s = sin(pi / 6).\nassert round(s, 2) = 0.5.'
    },
    {
      id: 'fc-09',
      cat: 'Kernel',
      q: 'What is Canonical Form 3 and how is a fingerprint generated?',
      a: 'Canonical Form 3 gives supported values a stable representation: nonintegral rationals use `{"#q": "p/q"}`, sets and record keys are ordered, and text retains exact code points. Model Text coercion is a separate operation. Fingerprints identify canonical values; they do not prove input truth.',
      code: '# Fingerprint example: "2c624232cdd22177"'
    },
    // fc-10 was removed for publication; the ids of the other cards are unchanged.
    {
      id: 'fc-11',
      cat: 'Epistemics',
      q: "What does the question-order adapter calculate?",
      a: "It computes the predictions of a finite real rational projector model on supplied states and operators. Noncommuting projectors can give order effects. The calculation does not show that a person or model follows that account.",
      code: ''
    },
    {
      id: 'fc-12',
      cat: 'Epistemics',
      q: "What is the limit of the fluid-stability analogy?",
      a: "Fluid theorems require their own equations and hypotheses. Symblic does not inherit a hallucination-prevention theorem from them. Its finite quadratic adapter establishes a unique minimum only for a supplied symmetric positive-definite problem.",
      code: ''
    },
    {
      id: 'fc-13',
      cat: 'Syntax',
      q: 'What is the difference between a `function` and a `routine`?',
      a: 'In the verified profile, a `function` cannot transitively invoke model routines or effects, including through imports. A `routine` can contain typed asks and supports memoization. Legacy functions can bridge routines; purity is profile-dependent, and bounded evaluation can refuse.',
      code: 'function double(x: Int) -> Int = x * 2.\nroutine summarize(txt: Text) -> Text do\n  ask s: Text "Summarize: {txt}"\n  return s.\nend.'
    },
    {
      id: 'fc-14',
      cat: 'Geometry',
      q: 'How does `symblic_geometry` verify that a 3D shape is a valid polyhedron?',
      a: '`solid_check(s)` verifies: every face is a flat strictly convex polygon, Euler characteristic V - E + F = 2, every edge is shared by exactly two faces, consistently orientable, positive volume, and convex wrapping.',
      code: 'let cube = shape_cube(1).\nassert solid_check(cube).valid_solid = true.'
    },
    {
      id: 'fc-15',
      cat: 'Models',
      q: 'What does `solve` do when attached to an `ask` statement?',
      a: 'If an ask has a finite domain (<= 20,000 values) and anchored kernel checks, `solve` lets the Kernel enumerate and test all candidates. If exactly one candidate passes, the Kernel returns it directly with ZERO model calls!',
      code: 'ask x: Int in 1..10 "Find x such that x * x = 49" with solve\nensure x * x = 49.'
    },
    {
      id: 'fc-16',
      cat: 'External',
      q: 'How does Symblic track external observations and actions?',
      a: 'Use `observe` for external readings and `act` for admitted actions. Durable effect IDs, policy checks and recovery records help avoid duplicate actions. A remote timeout can leave an unknown outcome; the ledger cannot guarantee exactly-once behavior for every external service.',
      code: 'observe temp = weather.current(city = "New York").\nact ping = email.send(to = "admin@example.invalid", subject = "Alert") with key="alert-1".'
    }
  ];

  // ---------------------------------------------------------------------------
  // Fill In The Blanks (Cloze Tests)
  // ---------------------------------------------------------------------------
  // Stable new IDs append the expanded course to the existing spaced-repetition deck.
  MASTERY_LEVELS.forEach((level, li) => level.bites.forEach((bite, bi) => {
    if (!bite.reflection) return;
    FLASHCARDS.push({id: `depth-v2-${li}-${bi}`, cat: level.title.split(': ').slice(1).join(': '),
      q: bite.reflection.prompt, a: bite.reflection.model, code: bite.code || ''});
  }));
  const oldRationalCard = FLASHCARDS.find(c => c.id === 'fc-02');
  if (oldRationalCard) oldRationalCard.a = 'Rational arithmetic represents supported ratios exactly, so 1/10 + 2/10 = 3/10 without binary floating-point rounding. It does not remove uncertainty in measured inputs, defects in a specification, or approximation in other operations. Check the kernel and adapter contract.';

  const CLOZE_TESTS = [
    {
      id: 'cloze-01',
      title: 'Exact Rational Math and Invariant Verification',
      desc: 'Fill in the keyword for variable binding, the exact fraction calculation, and the hard kernel check.',
      template: 'program RationalMath.\n\n{b1} half = 1 / 2.\nlet quarter = 1 / 4.\nlet sum = half + quarter.\n\n{b2} sum = {b3} because "exact 3/4 rational sum".',
      blanks: [
        { id: 'b1', answer: 'let', hint: 'The keyword for single-assignment binding in the Kernel.' },
        { id: 'b2', answer: 'assert', hint: 'The hard check statement that halts if condition is false.' },
        { id: 'b3', answer: '3/4', hint: '1/2 + 1/4 in exact fraction form.' }
      ],
      expl: 'Pair `let` with `assert` to check an encoded condition on bound values. Exact arithmetic preserves supported ratios; it does not establish that input values accurately describe the world.'
    },
    {
      id: 'cloze-02',
      title: 'Typed Model Ask with Rollback Retry',
      desc: 'Fill in the model statement keyword, the bounded integer type, and the transactional retry clause.',
      template: 'program SpiderCheck.\n\n{b1} spider_legs: {b2} "How many legs does a spider have?" with effort=low\n\nensure spider_legs = 8 else {b3} because "a spider has eight legs".',
      blanks: [
        { id: 'b1', answer: 'ask', hint: 'The only statement in core Symblic that calls an AI model.' },
        { id: 'b2', answer: 'Int in 0..20', hint: 'An integer type constrained between 0 and 20.' },
        { id: 'b3', answer: 'retry', hint: 'The transactional recovery action when ensure fails.' }
      ],
      expl: 'Psychological note: `ask` delegates to an untrusted model under a typed contract. If the model fails `ensure`, `else retry` triggers a state rollback and passes corrective feedback.'
    },
    {
      id: 'cloze-03',
      title: 'Datalog Relational Knowledge and Transitive Horn Clauses',
      desc: 'Fill in the keywords for relational facts, Horn rules, and logic queries.',
      template: 'program AccessRules.\n\n{b1} role_perm("admin", "delete_db").\nfact user_role("Alice", "admin").\n\n{b2} has_access(U, P) if user_role(U, R) and role_perm(R, P).\n\nlet alice_access = {b3} has_access("Alice", P).',
      blanks: [
        { id: 'b1', answer: 'fact', hint: 'Keyword for ground relational facts without logic variables.' },
        { id: 'b2', answer: 'rule', hint: 'Keyword for defining Horn clauses with logic variables.' },
        { id: 'b3', answer: 'query', hint: 'Keyword for querying the Datalog knowledge base.' }
      ],
      expl: 'Datalog derives consequences of supplied facts and rules. Correct deduction does not independently verify the truth or completeness of those inputs.'
    },
    {
      id: 'cloze-04',
      title: 'Multi-Model Consensus & Jury Options',
      desc: 'Fill in the effort tier for 5 votes plus peer review, and the consensus threshold option.',
      template: 'program CriticalConsensus.\n\nask triage: one of {low, medium, high, emergency} "Triage patient symptoms"\n  with effort={b1}, {b2}=0.75, strict',
      blanks: [
        { id: 'b1', answer: 'ultra', hint: 'The tier that samples 5 votes and runs a 2nd round peer jury.' },
        { id: 'b2', answer: 'agree', hint: 'The option specifying the required consensus threshold (0.0 to 1.0).' }
      ],
      expl: 'Multiple candidates can expose disagreement but can also share errors. More agreement or deliberation does not guarantee correctness or independence.'
    }
  ];

  // ---------------------------------------------------------------------------
  // Single-Line Syntax Drills (Active Retrieval & Muscle Memory)
  // ---------------------------------------------------------------------------
  const SYNTAX_DRILLS = [
    {
      id: 'drill-01',
      title: 'Exact Rational Assertion',
      prompt: 'Write an assert statement verifying that the exact rational sum 0.1 + 0.2 equals 0.3.',
      placeholder: 'assert ...',
      validate: (src) => /^\s*assert\s+(0\.1\s*\+\s*0\.2|0\.1\s*\+\s*0\.2\s*=\s*0\.3|exact\s*=\s*0\.3)\s*(=\s*0\.3)?(\s*because\s+.*)?\.\s*$/i.test(src.trim()) ||
                         /^\s*assert\s+0\.1\s*\+\s*0\.2\s*=\s*0\.3\s*\.?\s*$/i.test(src.trim()),
      solution: 'assert 0.1 + 0.2 = 0.3.',
      hint: 'Starts with `assert`, compares `0.1 + 0.2 = 0.3`, ends with a period.'
    },
    {
      id: 'drill-02',
      title: 'Bounded Integer Input',
      prompt: 'Write a `given` statement defining an input named `retry_limit` as an Integer bounded between 1 and 10 with a default of 3.',
      placeholder: 'given ...',
      validate: (src) => /^\s*given\s+retry_limit\s*:\s*(Int|Integer)\s+in\s+1\.\.10\s*=\s*3\s*\.?\s*$/i.test(src.trim()),
      solution: 'given retry_limit: Int in 1..10 = 3.',
      hint: 'Format: `given name: Int in min..max = default.`'
    },
    {
      id: 'drill-03',
      title: 'Model Ask with Low Effort',
      prompt: 'Write an `ask` statement asking for `item_count` as an `Int in 1..100` from the prompt "Count items" with low effort.',
      placeholder: 'ask item_count: ...',
      validate: (src) => /^\s*ask\s+item_count\s*:\s*Int\s+in\s+1\.\.100\s+"Count items"\s+with\s+effort\s*=\s*low\s*\.?\s*$/i.test(src.trim()),
      solution: 'ask item_count: Int in 1..100 "Count items" with effort=low.',
      hint: 'Syntax: `ask name: Type "Instruction" with effort=low.`'
    },
    {
      id: 'drill-04',
      title: 'Transactional Ensure with Rollback',
      prompt: 'Write an `ensure` statement requiring `count > 0` with an `else retry` clause and the reason "count must be positive".',
      placeholder: 'ensure count > 0 ...',
      validate: (src) => /^\s*ensure\s+count\s*>\s*0\s+else\s+retry\s+because\s+"count must be positive"\s*\.?\s*$/i.test(src.trim()),
      solution: 'ensure count > 0 else retry because "count must be positive".',
      hint: 'Structure: `ensure cond else retry because "reason".`'
    },
    {
      id: 'drill-05',
      title: 'Pure Datalog Horn Clause',
      prompt: 'Write a Datalog rule stating that `connected(X, Y)` holds if `edge(X, Y)`.',
      placeholder: 'rule connected(X, Y) ...',
      validate: (src) => /^\s*rule\s+connected\(X,\s*Y\)\s+if\s+edge\(X,\s*Y\)\s*\.?\s*$/i.test(src.trim()),
      solution: 'rule connected(X, Y) if edge(X, Y).',
      hint: 'Logic variables must be uppercase. Syntax: `rule head(...) if body(...).`'
    },
    {
      id: 'drill-06',
      title: 'Closed Enum Definition',
      prompt: 'Write a `define` statement creating a named type `Status` that is one of `active`, `paused`, or `archived`.',
      placeholder: 'define Status as ...',
      validate: (src) => /^\s*define\s+Status\s+as\s+one\s+of\s*\{\s*active\s*,\s*paused\s*,\s*archived\s*\}\s*\.?\s*$/i.test(src.trim()),
      solution: 'define Status as one of {active, paused, archived}.',
      hint: 'Format: `define Name as one of {opt1, opt2, opt3}.`'
    }
  ];

  // ---------------------------------------------------------------------------
  // Deep Epistemic & Concept Quizzes (Elaborative Interrogation)
  // ---------------------------------------------------------------------------
  const CONCEPT_QUIZZES = [
    {
      id: 'quiz-01',
      q: 'Why check a model-produced calculation or proof independently?',
      opts: [
        'Because AI models lack floating-point execution units and use too much GPU power for addition.',
        'Because a precise request does not guarantee a correct answer; an independent checker can validate the declared conditions.',
        'Because Python arithmetic runs in C, which makes the whole runtime execute 10,000x faster than Claude.',
        'Because models are legally prohibited from executing financial and arithmetic formulas under open-weights licenses.'
      ],
      correct: 1,
      expl: 'A model can construct mathematical answers, programs and proof terms. A reusable checker validates a supported witness, while direct exact computation remains available. Accepted derivations are conditional on their premises and formalization.'
    },
    {
      id: 'quiz-02',
      q: 'What benefit and limitation come with explicit capsules in multi-step workflows?',
      opts: [
        'By compressing all prior conversation turns into an encrypted vector embedding.',
        'By restarting the Python runtime process after every single statement.',
        'They select declared inputs, definitions and schema; needed dependencies must still be included and fit the context budget.',
        'By instructing the model to forget all previous instructions in the system prompt.'
      ],
      correct: 2,
      expl: 'Explicit context can reduce irrelevant material and make dependencies reviewable. Too little context can omit a referent or exception. Capsule selection does not guarantee attention, truthful answers or immunity to malicious source text.'
    },
    {
      id: 'quiz-03',
      q: 'What distinguishes Symblic\'s transactional `ensure ... else retry` from an ordinary Python `while` loop?',
      opts: [
        'A Python while loop is faster because it does not write to the disk.',
        'The runner restores declared internal state at the anchor ask before feedback and a bounded retry; external effects follow separate recovery rules.',
        'The ensure statement only checks syntax, not runtime values.',
        'The ensure statement terminates the entire operating system if the condition fails.'
      ],
      correct: 1,
      expl: 'Retry restores the relevant internal bindings and state at its anchor. Feedback can help another attempt, but does not guarantee convergence or diagnose the true cause. Effects are fenced separately and cannot be erased by restoring variables.'
    },
    {
      id: 'quiz-04',
      q: 'What does the finite quadratic witness establish?',
      opts: ['That every model interpretation is true', 'That all physical boundary conditions were inferred correctly', 'A unique minimum for the encoded positive-definite quadratic', 'That retries always converge to the intended meaning'],
      correct: 2,
      expl: 'Positive definiteness and the verified algebra establish the finite quadratic result. The physical or semantic interpretation of the inputs requires separate evidence.'
    }
  ];

  // ---------------------------------------------------------------------------
  // Guided Capstone Projects
  // ---------------------------------------------------------------------------
  const PROJECTS = [
    {
      id: 'proj-01',
      title: 'Project 1: Exact Rational Invoice & Tax Checks',
      difficulty: 'Beginner → Intermediate',
      desc: 'Build an automated invoice processor that extracts items, computes exact rational sales tax, and verifies total integrity with rollback protection.',
      starter: `program InvoiceAuditor.
note The model extracts quantities and costs; the Kernel computes tax and validates totals.

given raw_invoice: Text = """
INVOICE #INV-8042
Date: 2026-10-03
Item: Wireless Trackball Mouse
Quantity: 2
Unit Price: $45.50
Subtotal: $91.00
State Tax Rate: 8.5%
Claimed Total: $98.735
"""

define Invoice as Record {
  invoice_id: Text,
  quantity: Int in 1..100,
  unit_price: Number,
  claimed_total: Number
}.

# 1. Ask the model to extract the typed record
ask inv: Invoice "Extract invoice data from the text." from raw_invoice with effort=low

# 2. Kernel verification rules
ensure starts_with(inv.invoice_id, "INV-") else retry because "Invoice ID must start with INV-".

# 3. Kernel exact rational arithmetic
let subtotal = inv.quantity * inv.unit_price.
let tax_rate = 85 / 1000.  # Exact 8.5%
let computed_total = subtotal + (subtotal * tax_rate).

# 4. Verify claimed total matches exact mathematical calculation
assert computed_total = inv.claimed_total.

show [inv.invoice_id, subtotal, computed_total] as "Audited Invoice".
`,
      spec: [
        'Define a Record type `Invoice` with `invoice_id`, `quantity`, `unit_price`, and `claimed_total`.',
        'Extract data from `raw_invoice` using `ask` with low effort.',
        'Verify `invoice_id` format with `ensure ... else retry`.',
        'Compute subtotal and 8.5% tax strictly in the Kernel using exact rational fractions.',
        'Assert exact equality between computed total and claimed total.'
      ]
    },
    {
      id: 'proj-02',
      title: 'Project 2: Zero-Trust Security Access Matrix with Datalog',
      difficulty: 'Intermediate',
      desc: 'Implement a zero-trust role-based access control (RBAC) engine with transitive group inheritance using Datalog Horn clauses. Results depend on the supplied permissions and rules.',
      starter: `program ZeroTrustRBAC.
note This example checks supplied access facts and rules without model calls.

# Ground facts: user memberships and role privileges
fact member("Alice", "Engineering").
fact member("Bob", "Contractors").
fact subrole("Engineering", "Deployer").
fact subrole("Deployer", "ProductionAdmin").

fact role_perm("Contractors", "ReadDocs").
fact role_perm("Engineering", "ReadSource").
fact role_perm("ProductionAdmin", "ModifyCluster").

# Transitive role inheritance rules
rule has_role(User, Role) if member(User, Role).
rule has_role(User, TargetRole) if member(User, Intermediate) and subrole(Intermediate, TargetRole).
rule has_role(User, TargetRole) if has_role(User, Intermediate) and subrole(Intermediate, TargetRole).

# Access derivation rule
rule can_perform(User, Perm) if has_role(User, Role) and role_perm(Role, Perm).

# Formal Invariant Assertions
let alice_perms = query can_perform("Alice", Action).
let bob_perms = query can_perform("Bob", Action).

assert {"Action": "ModifyCluster"} in alice_perms.
assert not ({"Action": "ModifyCluster"} in bob_perms).

show alice_perms as "Alice Authorized Permissions".
show bob_perms as "Bob Authorized Permissions".
`,
      spec: [
        'Declare ground membership and privilege facts.',
        'Formulate Horn clauses for transitive subrole inheritance.',
        'Formulate the access derivation rule `can_perform(User, Perm)`.',
        'Execute queries and verify that Alice inherits ProductionAdmin while Bob is restricted to ReadDocs.'
      ]
    },
    {
      id: 'proj-03',
      title: 'Project 3: Scientific Stoichiometry & Bounded Dilution',
      difficulty: 'Advanced',
      desc: 'Create an audit-proof chemical dilution protocol using the `units` and `lab` standard libraries, enforcing safety thresholds with bounded numbers.',
      starter: `program ChemicalDilution.
note Exact ratios check the encoded dilution calculation; units, measurements and suitability need separate validation.

given target_molarity: Number = 0.2.  # M (mol / L)
given target_volume_ml: Number = 500. # mL
given stock_molarity: Number = 2.0.   # M (mol / L)

# C1 * V1 = C2 * V2  ==>  V1 = (C2 * V2) / C1
let required_stock_ml = (target_molarity * target_volume_ml) / stock_molarity.
let solvent_water_ml = target_volume_ml - required_stock_ml.

# Kernel verifies exact rational dilution
assert required_stock_ml = 50.
assert solvent_water_ml = 450.
assert required_stock_ml + solvent_water_ml = target_volume_ml.

# Model classifies safety tier based on concentration
ask hazard_tier: one of {low_hazard, moderate_hazard, severe_hazard}
  "Classify safety tier for {target_molarity} M hydrochloric acid solution"
  with effort=low

show [required_stock_ml, solvent_water_ml, hazard_tier] as "Dilution Protocol".
`,
      spec: [
        'Use exact rational arithmetic to solve $C_1 V_1 = C_2 V_2$.',
        'Verify required stock volume and solvent volumes with exact `assert` statements.',
        'Use closed enum `one of {...}` to safely classify hazard tier.'
      ]
    }
  ];

  // ---------------------------------------------------------------------------
  // UI Render Functions
  // ---------------------------------------------------------------------------

  // Render Tab 01: Overview & The Grand Breakthrough
  function renderOverview(m) {
    m.innerHTML = `
      <div class="sl-hero">
        <span class="lbl">Neuro-Symbolic Mastery</span>
        <h1 class="sl-title">Construct, Check, and Compose with Symblic</h1>
        <p class="sl-sub">
          Symblic connects <strong>model-produced constructions</strong>, explicit evidence and reusable checks.
          Precise statements help define the task; checked proofs, source witnesses and recorded outcomes establish different kinds of assurance.
          A universal epistemic operating system is a research direction, not a demonstrated capability.
        </p>
        <div class="sl-badge-row">
          <span class="sl-badge acc">Versioned Language Contracts</span>
          <span class="sl-badge krn">Deterministic Kernel (Exact Q)</span>
          <span class="sl-badge mdl">AI Applicators (Typed Capsules)</span>
          <span class="sl-badge">Canonical Form 3</span>
          <span class="sl-badge">Evidence Limits</span>
        </div>
      </div>

      <div class="unit">
        <h3>1. The Core Architecture: Construction and Checking</h3>
        <p>A model can construct a program, proof, extraction or proposed answer. Symblic makes the inputs and acceptance conditions explicit, checks supported witnesses, and preserves uncertainty where the result needs empirical evidence.</p>

        <div class="sl-dual-box">
          <div class="sl-dual-col krn">
            <div class="sl-dual-hdr krn">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
              The Deterministic Kernel
            </div>
            <ul class="sl-dual-list">
              <li><strong>Exact Rational Arithmetic (Q):</strong> Supported ratios remain exact ($0.1 + 0.2 = 0.3$); input and measurement errors remain possible.</li>
              <li><strong>Pure Datalog Engine:</strong> Stratified Horn clauses, transitive relations, fixpoint graph traversal.</li>
              <li><strong>Finite 3D Geometry:</strong> Checks of explicit convex polyhedra, including topology, orientation and volume; Euler equality alone is insufficient.</li>
              <li><strong>Canonical Drawing:</strong> Versioned SVG generation with a fixed Decimal approximation policy.</li>
              <li><strong>Declared Checks:</strong> <code>assert</code> fails on a false condition; <code>ensure ... else retry</code> can restore internal state and retry within bounds.</li>
              <li><strong>Resource Controls:</strong> Admitted run workers apply process and work budgets; exceeding a bound is a visible outcome.</li>
            </ul>
          </div>

          <div class="sl-dual-col mdl">
            <div class="sl-dual-hdr mdl">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
              The AI Applicators
            </div>
            <ul class="sl-dual-list">
              <li><strong>Constructors:</strong> Available model routes can propose answers, code and supported proof terms.</li>
              <li><strong>Typed Contracts:</strong> Explicit asks specify answer types. Constrained decoding depends on provider support; replies still require validation.</li>
              <li><strong>Explicit Context:</strong> Declared inputs, definitions and evidence dependencies make selection reviewable; missing context can still invalidate an answer.</li>
              <li><strong>Consensus & Multi-Model Juries:</strong> <code>votes=N</code>, <code>ultra</code> second-round peer review.</li>
              <li><strong>Error Feedback Loop:</strong> Invariant failures inject rejected values back into retry prompts.</li>
              <li><strong>Bounded Authority:</strong> A model reply can influence program flow but cannot attest its own truth or grant itself an external capability.</li>
            </ul>
          </div>
        </div>

        <div class="sl-diagram-card">
          <div class="lbl">Visual Dual-Coding Architecture</div>
          <svg class="sl-diagram-svg" viewBox="0 0 720 300">
            <rect x="10" y="10" width="700" height="280" rx="8" fill="var(--bg2)" stroke="var(--brd)" stroke-width="1.5"/>
            <!-- Program Header -->
            <rect x="30" y="30" width="660" height="40" rx="4" fill="var(--bg1)" stroke="var(--acc)" stroke-width="2"/>
            <text x="360" y="55" font-family="var(--mono)" font-size="14" font-weight="bold" fill="var(--tx1)" text-anchor="middle">SYMBLIC PROGRAM (Controlled Natural Language AST)</text>

            <!-- Kernel Box -->
            <rect x="40" y="100" width="300" height="160" rx="6" fill="var(--krn-bg)" stroke="var(--krn-brd)" stroke-width="2"/>
            <text x="190" y="125" font-family="var(--sans)" font-size="15" font-weight="bold" fill="var(--krn-tx)" text-anchor="middle">DETERMINISTIC KERNEL</text>
            <text x="60" y="155" font-family="var(--mono)" font-size="11" fill="var(--krn-tx)">• Exact Rationals (p/q)</text>
            <text x="60" y="180" font-family="var(--mono)" font-size="11" fill="var(--krn-tx)">• Datalog Fixpoint Engine</text>
            <text x="60" y="205" font-family="var(--mono)" font-size="11" fill="var(--krn-tx)">• 3D Geometry (V - E + F = 2)</text>
            <text x="60" y="230" font-family="var(--mono)" font-size="11" fill="var(--krn-tx)">• Transactional State Rollback</text>

            <!-- Model Box -->
            <rect x="380" y="100" width="300" height="160" rx="6" fill="var(--mdl-bg)" stroke="var(--mdl-brd)" stroke-width="2"/>
            <text x="530" y="125" font-family="var(--sans)" font-size="15" font-weight="bold" fill="var(--mdl-tx)" text-anchor="middle">AI APPLICATORS (MODELS)</text>
            <text x="400" y="155" font-family="var(--mono)" font-size="11" fill="var(--mdl-tx)">• Answers, Programs and Proofs</text>
            <text x="400" y="180" font-family="var(--mono)" font-size="11" fill="var(--mdl-tx)">• Closed JSON Schema Target</text>
            <text x="400" y="205" font-family="var(--mono)" font-size="11" fill="var(--mdl-tx)">• Explicit Context and Evidence</text>
            <text x="400" y="230" font-family="var(--mono)" font-size="11" fill="var(--mdl-tx)">• Multi-Model Consensus (ultra)</text>

            <!-- Arrows -->
            <path d="M 340 150 L 380 150" stroke="var(--mdl-brd)" stroke-width="2" marker-end="url(#arr-mdl)"/>
            <path d="M 380 210 L 340 210" stroke="var(--krn-brd)" stroke-width="2" marker-end="url(#arr-krn)"/>
            <text x="360" y="142" font-family="var(--mono)" font-size="9" fill="var(--tx3)" text-anchor="middle">ask</text>
            <text x="360" y="225" font-family="var(--mono)" font-size="9" fill="var(--tx3)" text-anchor="middle">ensure</text>
          </svg>
        </div>

        <div class="sl-callout why">
          <div class="sl-callout-title">Why Separate Construction from Checking?</div>
          A small reusable checker can accept a supported proof or witness even when finding it was difficult.
          Direct exact computation remains useful, and empirical tasks still need source evidence and outcome measurements.
          Better agreement or a passed schema is not proof that the intended task was fulfilled.
        </div>
      </div>
    `;
  }

  // Render Tab 02: Foundations (In & Out: Kernel & Models)
  function renderFoundations(m) {
    m.innerHTML = `
      <div class="sl-hero">
        <span class="lbl">System Mechanics</span>
        <h1 class="sl-title">How Symblic Operates In and Out</h1>
        <p class="sl-sub">
          Follow the runtime contracts for bounded checking, model construction, explicit context and external actions.
          Each has a different assurance boundary; none turns arbitrary prose into guaranteed execution.
        </p>
      </div>

      <div class="unit">
        <h3>1. How Symblic Affects and Operates the Kernel</h3>
        <div class="sl-callout math">
          <div class="sl-callout-title">Mathematical Invariant: Exact Rational Field Q</div>
          Floating point arithmetic (IEEE 754) can be non-associative: $(a + b) + c \\neq a + (b + c)$.
          In formal logic, this can make a naive exact-equality comparison fail. Symblic represents supported rational values as exact elements of the field of fractions $\\mathbb{Q} = \\{p/q \\mid p, q \\in \\mathbb{Z}, q \\neq 0\\}$.
        </div>
        <p>The pure Python Kernel (<code>symblic.py</code>) enforces these mechanical invariants:</p>
        <ul style="padding-left:22px; line-height:1.7; margin-bottom:16px;">
          <li><strong>No Python eval():</strong> Symblic parses its own expression language without Python <code>eval</code>. Restricted evaluator contexts deny selected Symblic builtins through <code>EVAL_DENIED</code>; this is one boundary, not a complete security proof.</li>
          <li><strong>4000-Digit Bounds (MAX_DIGITS):</strong> Supported integer numerators and denominators have a 4,000-digit bound. Work counters and process limits address other resource costs; a digit bound alone does not prevent every expensive computation.</li>
          <li><strong>Process Limits in systemd Scopes:</strong> On the original host, admitted local execution units ran in bounded systemd scopes. Limits reduce a worker\'s resource impact; actual placement and configured limits must be read from its execution record.</li>
          <li><strong>Deterministic Rollback Snapshots:</strong> At a retry anchor, the runner captures relevant internal bindings and state. A failed <code>ensure ... else retry</code> restores that state before a bounded retry. External effect records follow separate recovery rules.</li>
          <li><strong>Stratified Datalog Fixpoint:</strong> Finite supplied facts and stratified rules derive further relations under work limits. Deduced relations depend on the supplied facts; refusal at a resource bound is not a proof that a relation is false.</li>
          <li><strong>Canonical Value Identity:</strong> Versioned canonicalization orders supported sets and record keys for stable hashing. A matching fingerprint identifies canonical values; it does not attest source truth or fresh-generation reproducibility.</li>
        </ul>

        <hr style="border:0; border-top:1px solid var(--hair); margin:24px 0;">

        <h3>2. How Symblic Affects and Constrains AI Models</h3>
        <p>Models are <strong>constructors whose outputs need validation</strong>. Their answers can affect program branches; host capabilities and policy govern external actions:</p>
        <ul style="padding-left:22px; line-height:1.7; margin-bottom:16px;">
          <li><strong>Explicit Capsules:</strong> Each ask selects inputs and definitions. Required referents and exceptions must fit the context budget. Smaller prompts can help focus but can also omit necessary evidence.</li>
          <li><strong>Schema and Validation:</strong> Answer types define permitted structure. Providers vary in constrained-decoding support; the runner validates the received value. Compatibility coercion and strict validation have different contracts.</li>
          <li><strong>Answer Diversity:</strong> Multiple samples can expose disagreement. Normalized answer entropy describes variation in those samples, not calibrated truth uncertainty. Unanimous answers can all be wrong.</li>
          <li><strong>Declared Model Families:</strong> Family requirements track support across model labels. Labels do not establish independent training data, architectures or errors; shared failure must be measured.</li>
          <li><strong>Specification Candidates:</strong> Tighten probes disagreement and proposes clarified wording. Candidate scores do not establish fidelity to owner intent; adoption and independent requirement checks remain separate.</li>
        </ul>

        <div class="sl-callout psych">
          <div class="sl-callout-title">Different Jobs, Different Evidence</div>
          A model may search for a construction that a small checker can validate. A deterministic adapter may compute a result directly.
          Human interpretation and external observations still require their own evidence. This engineering division does not classify an LLM as a human cognitive system.
        </div>
      </div>
    `;
  }

  // Render Tab 03: Full Language Reference
  function renderLanguage(m) {
    m.innerHTML = `
      <div class="sl-hero">
        <span class="lbl">Language Reference</span>
        <h1 class="sl-title">Statements, Types, and Builtin Functions</h1>
        <p class="sl-sub">
          Selected syntax and examples. Consult the installed language specification for supported profiles, fragments, bounds and complete adapter contracts.
        </p>
      </div>

      <div class="unit">
        <h3>Core Statements</h3>
        <div class="tblwrap" tabindex="0">
          <table class="tbl">
            <thead>
              <tr><th>Statement</th><th>Syntax Example</th><th>Kernel Behavior & Meaning</th></tr>
            </thead>
            <tbody>
              <tr><td><code>program</code></td><td><code>program OrderAudit.</code></td><td>Declares program identity and run scope.</td></tr>
              <tr><td><code>let</code></td><td><code>let total = price * qty.</code></td><td>Single assignment binding in Kernel scope. Immutable once bound.</td></tr>
              <tr><td><code>given</code></td><td><code>given rate: Number = 0.05.</code></td><td>External parameter with required type and optional default.</td></tr>
              <tr><td><code>ask</code></td><td><code>ask x: Int "Prompt" with effort=low</code></td><td>Invokes AI model within an isolated typed capsule.</td></tr>
              <tr><td><code>ensure</code></td><td><code>ensure x &gt; 0 else retry.</code></td><td>Postcondition. Fails trigger transactional rollback and feedback retry.</td></tr>
              <tr><td><code>assert</code></td><td><code>assert a = b because "...".</code></td><td>Hard invariant. Halts the entire run if false. Zero model calls.</td></tr>
              <tr><td><code>fact</code></td><td><code>fact parent(ada, ben).</code></td><td>Stores ground Datalog relational fact.</td></tr>
              <tr><td><code>rule</code></td><td><code>rule anc(X,Y) if parent(X,Y).</code></td><td>Datalog Horn clause. Logic variables are uppercase.</td></tr>
              <tr><td><code>query</code></td><td><code>let res = query anc(Who, cleo).</code></td><td>Queries relational knowledge base with unification.</td></tr>
              <tr><td><code>term</code></td><td><code>term vat means "Value added tax".</code></td><td>Injects domain definition into capsules where the term appears.</td></tr>
              <tr><td><code>observe</code></td><td><code>observe w = weather.get("NY").</code></td><td>Idempotent external environment observation via ledger.</td></tr>
              <tr><td><code>act</code></td><td><code>act p = mail.send(...) with key="k1".</code></td><td>Policy-governed external side effect with unique idempotency key.</td></tr>
              <tr><td><code>function</code></td><td><code>function dbl(x: Int) -&gt; Int = x*2.</code></td><td>Verified profile: transitively pure, including imports. Legacy functions may call routines; profile and runtime bounds matter.</td></tr>
              <tr><td><code>routine</code></td><td><code>routine r(x: Text) -&gt; Text do ... end.</code></td><td>Typed model procedure with internal asks and memoization.</td></tr>
              <tr><td><code>show</code></td><td><code>show [subtotal, tax] as "Summary".</code></td><td>Appends values to program output ledger.</td></tr>
            </tbody>
          </table>
        </div>

        <h3 style="margin-top:24px;">The Checked Type System</h3>
        <div class="tblwrap" tabindex="0">
          <table class="tbl">
            <thead>
              <tr><th>Type</th><th>Example</th><th>Coercion & Bounds Enforcement</th></tr>
            </thead>
            <tbody>
              <tr><td><code>Int</code></td><td><code>42</code>, <code>-10</code></td><td>Arbitrary precision integer up to 4000 digits.</td></tr>
              <tr><td><code>Int in a..b</code></td><td><code>Int in 1..100</code></td><td>Strict integer bounded within inclusive range [a, b].</td></tr>
              <tr><td><code>Number</code></td><td><code>3/4</code>, <code>0.75</code></td><td>Exact rational fraction in Q.</td></tr>
              <tr><td><code>Number to N places</code></td><td><code>Number to 2 places</code></td><td>Rational rounded half-even to N decimal places.</td></tr>
              <tr><td><code>Bool</code></td><td><code>true</code>, <code>false</code></td><td>Boolean. Coerced from "yes"/"no", case-insensitive.</td></tr>
              <tr><td><code>Text</code></td><td><code>"hello"</code></td><td>NFC normalized Unicode string.</td></tr>
              <tr><td><code>one of {a, b, c}</code></td><td><code>one of {red, green, blue}</code></td><td>Closed enum. Case/space/punctuation normalized.</td></tr>
              <tr><td><code>List of T [length N]</code></td><td><code>List of Int length 3</code></td><td>1-indexed ordered list with optional exact or bounded length.</td></tr>
              <tr><td><code>Set of T</code></td><td><code>{1, 2, 3}</code></td><td>Unordered set with unique elements, sorted in canonical JSON.</td></tr>
              <tr><td><code>Record {k: T, ...}</code></td><td><code>{name: Text, age: Int}</code></td><td>Typed dictionary with exact schema matching.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  // Render Tab 04: Spaced Repetition Flashcards
  let currentCardIndex = 0;
  let cardFlipped = false;
  let activeCat = 'All';

  function renderFlashcards(m) {
    const cats = ['All', 'Syntax', 'Kernel', 'Models', 'Datalog', 'Epistemics', 'Geometry', 'External'];
    const filtered = activeCat === 'All' ? FLASHCARDS : FLASHCARDS.filter(c => c.cat === activeCat);
    if (currentCardIndex >= filtered.length) currentCardIndex = 0;
    const card = filtered[currentCardIndex] || FLASHCARDS[0];
    const cardSt = getCardState(card.id);

    // Calculate stats
    const totalMastered = FLASHCARDS.filter(c => getCardState(c.id).reps >= 3).length;
    const totalLearning = FLASHCARDS.filter(c => getCardState(c.id).reps > 0 && getCardState(c.id).reps < 3).length;
    const totalNew = FLASHCARDS.filter(c => getCardState(c.id).reps === 0).length;

    m.innerHTML = `
      <div class="sl-hero">
        <span class="lbl">Active Recall & Spaced Practice</span>
        <h1 class="sl-title">Symblic Memory Solidification Deck</h1>
        <p class="sl-sub">
          Use retrieval practice and an <strong>SM-2-inspired scheduler with minute-scale practice intervals</strong>
          to practise syntax, checks, consensus mechanics and epistemic limits. Review ratings guide scheduling; they do not measure durable mastery.
        </p>
      </div>

      <div class="sl-stats-bar">
        <div class="sl-stat-box">
          <span class="sl-stat-val" style="color:var(--ok)">${totalMastered}</span>
          <span class="sl-stat-lbl">Reviewed (Reps ≥ 3)</span>
        </div>
        <div class="sl-stat-box">
          <span class="sl-stat-val" style="color:var(--warn)">${totalLearning}</span>
          <span class="sl-stat-lbl">Learning</span>
        </div>
        <div class="sl-stat-box">
          <span class="sl-stat-val" style="color:var(--tx2)">${totalNew}</span>
          <span class="sl-stat-lbl">No Good/Easy count</span>
        </div>
        <div class="sl-stat-box">
          <span class="sl-stat-val" style="color:var(--acc)">${cardSt.interval} min</span>
          <span class="sl-stat-lbl">Current Interval</span>
        </div>
      </div>

      <div class="sl-chip-row" id="slCatRow">
        ${cats.map(c => `<button class="sl-chip ${c === activeCat ? 'active' : ''}" data-cat="${att(c)}">${esc(c)}</button>`).join('')}
      </div>

      <div class="sl-flashcard-section">
        <div class="sl-fc-scene" id="slFcScene" title="Click or press Space to flip">
          <div class="sl-fc-card ${cardFlipped ? 'flipped' : ''}" id="slFcCard">
            <!-- Front -->
            <div class="sl-fc-face sl-fc-front">
              <div class="sl-fc-hdr">
                <span>${esc(card.cat)} · Card ${currentCardIndex + 1} of ${filtered.length}</span>
                <span class="sl-badge krn">Active Recall</span>
              </div>
              <div class="sl-fc-body">
                <div class="sl-fc-prompt">${esc(card.q)}</div>
              </div>
              <div class="sl-fc-ftr">
                <span class="hint">Click or press Spacebar to reveal answer</span>
              </div>
            </div>

            <!-- Back -->
            <div class="sl-fc-face sl-fc-back">
              <div class="sl-fc-hdr">
                <span style="color:var(--acc-tx)">Answer</span>
                <span class="sl-badge acc">Repetition ${cardSt.reps}</span>
              </div>
              <div class="sl-fc-body">
                <div class="sl-fc-ans">${esc(card.a)}</div>
                ${card.code ? `<div class="sl-fc-code">${esc(card.code)}</div>` : ''}
              </div>
              <div class="sl-fc-ftr">
                <span>Rate your recall difficulty below</span>
              </div>
            </div>
          </div>
        </div>

        <div class="sl-fc-controls">
          <button class="sl-rate-btn again" data-rate="1">
            <span>Again</span>
            <span class="lbl">1 min</span>
          </button>
          <button class="sl-rate-btn hard" data-rate="2">
            <span>Hard</span>
            <span class="lbl">10 min</span>
          </button>
          <button class="sl-rate-btn good" data-rate="3">
            <span>Good</span>
            <span class="lbl">1 day</span>
          </button>
          <button class="sl-rate-btn easy" data-rate="4">
            <span>Easy</span>
            <span class="lbl">4 days</span>
          </button>
        </div>
      </div>

      <div class="sl-callout psych">
        <div class="sl-callout-title">Psychology of Retrieval Practice</div>
        Attempting to retrieve an answer <em>before</em> seeing it produces the <strong>Hypercorrection Effect</strong>:
        when a high-confidence error is corrected immediately, the neural pathway is consolidated with higher synaptic strength than passive re-reading.
      </div>
    `;

    // Event listeners
    const scene = $('slFcScene');
    if (scene) {
      scene.onclick = () => {
        cardFlipped = !cardFlipped;
        $('slFcCard').classList.toggle('flipped', cardFlipped);
      };
    }

    $('slCatRow').querySelectorAll('.sl-chip').forEach(btn => {
      btn.onclick = () => {
        activeCat = btn.dataset.cat;
        currentCardIndex = 0;
        cardFlipped = false;
        renderFlashcards(m);
      };
    });

    m.querySelectorAll('.sl-rate-btn').forEach(btn => {
      btn.onclick = (e) => {
        e.stopPropagation();
        const rating = parseInt(btn.dataset.rate, 10);
        rateCard(card.id, rating);
        cardFlipped = false;
        currentCardIndex = (currentCardIndex + 1) % filtered.length;
        renderFlashcards(m);
        toast('Card scheduled with the practice interval (minutes)');
      };
    });
  }

  // Render Tab 05: Fill in the Blanks (Cloze Tests)
  function renderCloze(m) {
    m.innerHTML = `
      <div class="sl-hero">
        <span class="lbl">Cognitive Chunking</span>
        <h1 class="sl-title">Interactive Cloze Exercises</h1>
        <p class="sl-sub">
          Fill in the critical syntax tokens, type constraints, and logic clauses.
          Cloze tests leverage <strong>Cognitive Load Theory</strong> (Sweller) by isolating target syntactic chunks within complete, working code.
        </p>
      </div>

      <div class="unit">
        ${CLOZE_TESTS.map(t => `
          <div class="sl-cloze-card" id="cloze_${t.id}">
            <div class="sl-cloze-title">${esc(t.title)}</div>
            <div class="sl-cloze-desc">${esc(t.desc)}</div>
            <div class="sl-cloze-code">${formatClozeTemplate(t.id, t.template, t.blanks)}</div>
            <div class="sl-cloze-actions">
              <button class="btn sm" id="btn_check_${t.id}">Check Answers</button>
              <button class="btn sm alt" id="btn_hint_${t.id}">Toggle Hints</button>
              <span class="hint" id="status_${t.id}"></span>
            </div>
            <div class="sl-cloze-hint" id="hints_${t.id}">
              ${t.blanks.map(b => `<div><strong>${esc(b.id)}:</strong> ${esc(b.hint)}</div>`).join('')}
              <div style="margin-top:6px; color:var(--ok)"><em>${esc(t.expl)}</em></div>
            </div>
          </div>
        `).join('')}
      </div>
    `;

    // Bind Cloze interactions
    CLOZE_TESTS.forEach(t => {
      const checkBtn = $(`btn_check_${t.id}`);
      const hintBtn = $(`btn_hint_${t.id}`);
      const hintsEl = $(`hints_${t.id}`);
      const statusEl = $(`status_${t.id}`);

      if (hintBtn) {
        hintBtn.onclick = () => {
          hintsEl.style.display = hintsEl.style.display === 'block' ? 'none' : 'block';
        };
      }

      if (checkBtn) {
        checkBtn.onclick = () => {
          let allRight = true;
          t.blanks.forEach(b => {
            const input = $(`blank_${t.id}_${b.id}`);
            if (!input) { allRight = false; return; }
            const val = input.value.trim();
            if (val.toLowerCase() === b.answer.toLowerCase()) {
              input.classList.remove('wrong');
              input.classList.add('correct');
            } else {
              input.classList.remove('correct');
              input.classList.add('wrong');
              allRight = false;
            }
          });
          if (allRight) {
            statusEl.textContent = '✓ Perfectly correct!';
            statusEl.style.color = 'var(--ok)';
            toast('Cloze completed correctly!');
          } else {
            statusEl.textContent = 'Some tokens are incorrect. Check hints!';
            statusEl.style.color = 'var(--err)';
          }
        };
      }
    });
  }

  // Each blank's id includes its exercise id: that is the id the checker reads.
  function formatClozeTemplate(testId, template, blanks) {
    let out = esc(template);
    blanks.forEach(b => {
      const token = `{${b.id}}`;
      const html = `<input type="text" class="sl-blank-input" id="blank_${att(testId)}_${att(b.id)}" placeholder="${att(b.id)}" aria-label="${att('Blank ' + b.id)}" autocomplete="off" autocorrect="off">`;
      out = out.replace(token, html);
    });
    return out;
  }

  // Render Tab 06: Single-Line Syntax Drills
  function renderDrills(m) {
    m.innerHTML = `
      <div class="sl-hero">
        <span class="lbl">Deliberate Practice</span>
        <h1 class="sl-title">Single-Line Syntax Drills</h1>
        <p class="sl-sub">
          Rapid-fire micro-challenges to build unhesitating motor memory and syntactic fluency for Symblic commands.
        </p>
      </div>

      <div class="unit">
        ${SYNTAX_DRILLS.map((d, idx) => `
          <div class="sl-drill-card" id="drill_${d.id}">
            <div class="sl-drill-q">Drill ${idx + 1}: ${esc(d.title)}</div>
            <div class="sl-drill-spec">${esc(d.prompt)}</div>
            <div class="sl-drill-input-row">
              <input type="text" class="sl-drill-input" id="input_${att(d.id)}" placeholder="${att(d.placeholder)}" autocomplete="off">
              <button class="btn" id="btn_drill_${d.id}">Verify</button>
              <button class="btn alt" id="btn_sol_${d.id}">Solution</button>
            </div>
            <div class="sl-drill-feedback" id="feed_${d.id}"></div>
          </div>
        `).join('')}
      </div>
    `;

    SYNTAX_DRILLS.forEach(d => {
      const verifyBtn = $(`btn_drill_${d.id}`);
      const solBtn = $(`btn_sol_${d.id}`);
      const inputEl = $(`input_${d.id}`);
      const feedEl = $(`feed_${d.id}`);

      if (verifyBtn) {
        verifyBtn.onclick = () => {
          const val = inputEl.value;
          if (d.validate(val)) {
            feedEl.className = 'sl-drill-feedback ok';
            feedEl.textContent = '✓ Correct syntax! Statement conforms to Symblic grammar.';
            toast('Drill passed!');
          } else {
            feedEl.className = 'sl-drill-feedback err';
            feedEl.textContent = `Syntax mismatch. Hint: ${d.hint}`;
          }
        };
      }

      if (solBtn) {
        solBtn.onclick = () => {
          inputEl.value = d.solution;
          feedEl.className = 'sl-drill-feedback ok';
          feedEl.textContent = `Solution loaded: ${d.solution}`;
        };
      }

      if (inputEl) {
        inputEl.onkeydown = (e) => {
          if (e.key === 'Enter') verifyBtn.click();
        };
      }
    });
  }

  // Render Tab 07: Concept & Epistemic Quizzes
  function renderQuizzes(m) {
    m.innerHTML = `
      <div class="sl-hero">
        <span class="lbl">Elaborative Interrogation</span>
        <h1 class="sl-title">Epistemic & Architectural Quizzes</h1>
        <p class="sl-sub">
          Test your comprehension of the deep mathematical and philosophical principles behind Symblic.
          Each question probes the foundational <em>why</em>.
        </p>
      </div>

      <div class="unit">
        ${CONCEPT_QUIZZES.map((q, idx) => `
          <div class="sl-quiz-card" id="quiz_${q.id}">
            <div class="sl-quiz-q">Question ${idx + 1}: ${esc(q.q)}</div>
            <div class="sl-quiz-options">
              ${q.opts.map((opt, oIdx) => `
                <div class="sl-quiz-opt" data-qid="${q.id}" data-idx="${oIdx}">
                  <span class="mono" style="color:var(--tx3)">[${String.fromCharCode(65 + oIdx)}]</span>
                  <span>${esc(opt)}</span>
                </div>
              `).join('')}
            </div>
            <div class="sl-quiz-expl" id="expl_${q.id}">
              <div class="lbl" style="color:var(--ok)">Epistemic Explanation</div>
              <div>${esc(q.expl)}</div>
            </div>
          </div>
        `).join('')}
      </div>
    `;

    m.querySelectorAll('.sl-quiz-opt').forEach(opt => {
      opt.onclick = () => {
        const qid = opt.dataset.qid;
        const oIdx = parseInt(opt.dataset.idx, 10);
        const quiz = CONCEPT_QUIZZES.find(q => q.id === qid);
        const card = $(`quiz_${qid}`);
        const explEl = $(`expl_${qid}`);

        card.querySelectorAll('.sl-quiz-opt').forEach(el => {
          el.classList.remove('selected', 'right', 'wrong');
        });

        opt.classList.add('selected');
        if (oIdx === quiz.correct) {
          opt.classList.add('right');
          explEl.style.display = 'block';
          toast('Correct answer!');
        } else {
          opt.classList.add('wrong');
          card.querySelectorAll('.sl-quiz-opt')[quiz.correct].classList.add('right');
          explEl.style.display = 'block';
        }
      };
    });
  }

  // Render Tab 08: Guided Capstone Projects
  function renderProjects(m) {
    m.innerHTML = `
      <div class="sl-hero">
        <span class="lbl">Synthesis & Creation (Bloom L6)</span>
        <h1 class="sl-title">Guided Hands-On Capstone Projects</h1>
        <p class="sl-sub">
          Build full, verified Symblic programs with real-world scenarios.
          ${HOST_API ? 'Test your code directly against the live backend API (<code>/api/automation/symblic/check</code>).'
            : 'Checking and capsule preview need the host API (<code>/api/automation/symblic/check</code> and <code>/preview</code>), which this static copy does not have; the buttons say how to check a program with <code>tools/symblic</code> instead.'}
        </p>
      </div>

      <div class="unit">
        ${PROJECTS.map(p => `
          <div class="sl-project-card" id="proj_${p.id}">
            <div class="sl-project-title">${esc(p.title)}</div>
            <div class="sl-badge krn" style="margin-bottom:8px;">${esc(p.difficulty)}</div>
            <div class="sl-project-desc">${esc(p.desc)}</div>

            <div class="sl-callout why" style="margin-bottom:12px;">
              <div class="sl-callout-title">Project Requirements</div>
              <ul style="padding-left:18px; margin:0;">
                ${p.spec.map(s => `<li>${esc(s)}</li>`).join('')}
              </ul>
            </div>

            <textarea class="sl-project-editor" id="code_${p.id}" aria-label="${att(p.title + ': program')}" spellcheck="false">${esc(p.starter)}</textarea>

            <div class="sl-project-actions">
              <button class="btn" id="btn_check_${p.id}">Check with Live Kernel${HOST_LABEL}</button>
              <button class="btn alt" id="btn_preview_${p.id}">Preview Capsule${HOST_LABEL}</button>
              <button class="btn alt" id="btn_reset_${p.id}">Reset Starter Code</button>
              <span class="hint" id="status_${p.id}"></span>
            </div>

            <div class="sl-project-result" id="res_${p.id}"></div>
          </div>
        `).join('')}
      </div>
    `;

    PROJECTS.forEach(p => {
      const checkBtn = $(`btn_check_${p.id}`);
      const previewBtn = $(`btn_preview_${p.id}`);
      const resetBtn = $(`btn_reset_${p.id}`);
      const editorEl = $(`code_${p.id}`);
      const resEl = $(`res_${p.id}`);
      const statusEl = $(`status_${p.id}`);

      if (checkBtn) {
        checkBtn.onclick = async () => {
          if (!HOST_API) { needsHost(resEl, statusEl); return; }
          statusEl.textContent = 'Checking against Kernel...';
          resEl.style.display = 'block';
          try {
            const data = await api(API + 'check', { source: editorEl.value });
            if (data.ok) {
              resEl.textContent = `✓ STATIC CHECK PASSED\nProgram Name: ${data.name || 'Untitled'}\nStatements: ${(data.plan || []).length}\nProfile: ${JSON.stringify(data.profile || {})}\n${staticSpecificationScore(data.predictability)}`;
              resEl.style.border = '1px solid var(--ok)';
              statusEl.textContent = '✓ Static checks passed';
              toast('Static syntax and type checks passed.');
            } else {
              const errs = (data.errors || []).map(e => `[Line ${e.line || '?'}] ${e.message}`).join('\n');
              resEl.textContent = `✗ STATIC CHECK FAILED:\n${errs}`;
              resEl.style.border = '1px solid var(--err)';
              statusEl.textContent = 'Errors detected';
            }
          } catch (err) {
            resEl.textContent = `API error: ${err.message || err}`;
            resEl.style.border = '1px solid var(--err)';
            statusEl.textContent = 'API call failed';
          }
        };
      }

      if (previewBtn) {
        previewBtn.onclick = async () => {
          if (!HOST_API) { needsHost(resEl, statusEl); return; }
          statusEl.textContent = 'Previewing first ask...';
          resEl.style.display = 'block';
          try {
            const data = await api(API + 'preview', { source: editorEl.value, inputs: {}, by: 'claude:haiku' });
            if (data.status === 'paused' && data.next) {
              resEl.textContent = `✓ CAPSULE INSPECTION:\nApplicator: ${data.next.app}\nPrompt Sent to Model:\n${data.next.prompt}\n\nCompiled JSON Schema:\n${JSON.stringify(data.next.schema, null, 2)}`;
              resEl.style.border = '1px solid var(--acc)';
              statusEl.textContent = 'Capsule previewed';
              toast('Capsule extracted from Kernel!');
            } else if (data.status === 'done') {
              resEl.textContent = `Preview completed without pausing for a model ask. This preview does not execute external effects.\nOutputs:\n${JSON.stringify(data.outputs, null, 2)}`;
              resEl.style.border = '1px solid var(--ok)';
              statusEl.textContent = 'Pure Kernel run';
            } else {
              resEl.textContent = `Preview error: ${data.error || 'Unknown error'}`;
              resEl.style.border = '1px solid var(--err)';
            }
          } catch (err) {
            resEl.textContent = `Preview failed: ${err.message || err}`;
            resEl.style.border = '1px solid var(--err)';
          }
        };
      }

      if (resetBtn) {
        resetBtn.onclick = () => {
          editorEl.value = p.starter;
          resEl.style.display = 'none';
          statusEl.textContent = 'Starter restored';
        };
      }
    });
  }

  // Render Tab 09: Interactive Playground & Capsule Inspector
  function renderPlayground(m) {
    m.innerHTML = `
      <div class="sl-hero">
        <span class="lbl">Interactive IDE</span>
        <h1 class="sl-title">Live Symblic Workbench & Capsule Inspector</h1>
        <p class="sl-sub">
          Compose any Symblic program, run static checks, preview the isolated model capsule,
          and inspect compiled JSON schemas in real time.${HOST_API ? '' : ' Checking and preview need the host API, which this static copy does not have; the buttons say how to check a program with <code>tools/symblic</code> instead.'}
        </p>
      </div>

      <div class="unit">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <span class="lbl">Symblic Editor</span>
          <div>
            <select class="field sm" id="slPlayTemplate" style="width:200px;" aria-label="Template">
              <option value="spider">Template: Spider Study</option>
              <option value="rational">Template: Exact Rational Proof</option>
              <option value="datalog">Template: Datalog Family Tree</option>
              <option value="geometry">Template: 3D Polyhedron Solid</option>
            </select>
          </div>
        </div>

        <textarea class="sl-project-editor" id="slPlayCode" style="height:320px;" aria-label="Symblic program" spellcheck="false">program SpiderStudy.
note The kernel decides what is formal; the model is asked only what is not.

let pairs = 4.
let total_expected = pairs * 2.

ask legs: Int in 0..20 "How many legs does a spider have?" with effort=low
ensure legs = total_expected else retry because "a spider has eight legs".

show [total_expected, legs] as "Verified Legs".
</textarea>

        <div class="sl-project-actions">
          <button class="btn" id="slPlayCheckBtn">Check Program${HOST_LABEL}</button>
          <button class="btn alt" id="slPlayPreviewBtn">Preview Capsule${HOST_LABEL}</button>
          <button class="btn alt" id="slPlayClearBtn">Clear</button>
          <a class="btn alt" href="../studio/symblic.html" target="_blank" rel="noopener">Open the Symblic studio page (needs a host) ↗</a>
          <span class="hint" id="slPlayStatus"></span>
        </div>

        <div class="sl-project-result" id="slPlayOutput"></div>
      </div>
    `;

    const templates = {
      spider: `program SpiderStudy.
note The kernel decides what is formal; the model is asked only what is not.

let pairs = 4.
let total_expected = pairs * 2.

ask legs: Int in 0..20 "How many legs does a spider have?" with effort=low
ensure legs = total_expected else retry because "a spider has eight legs".

show [total_expected, legs] as "Verified Legs".
`,
      rational: `program RationalArithmetic.
note Exact rational mathematics in field Q.

let a = 0.1 + 0.2.
assert a = 0.3.

let third = 1 / 3.
assert third * 3 = 1.

let frac_sum = 1/2 + 1/3 + 1/6.
assert frac_sum = 1.

show [a, third, frac_sum] as "Exact Fractions".
`,
      datalog: `program FamilyTree.
note Pure Datalog Horn clauses evaluated in microseconds.

fact parent("Ada", "Ben").
fact parent("Ben", "Cleo").
fact parent("Cleo", "Dan").

rule ancestor(X, Y) if parent(X, Y).
rule ancestor(X, Z) if parent(X, Y) and ancestor(Y, Z).

let dan_ancestors = query ancestor(Who, "Dan").
assert {"Who": "Ada"} in dan_ancestors.

show dan_ancestors as "Dan's Ancestry".
`,
      geometry: `program CubeGeometry.
note Exact polyhedral validation with Euler characteristic V - E + F = 2.

let cube = shape_cube(1).
let chk = solid_check(cube).
assert chk.valid_solid = true.

show chk as "Cube Solid Check".
`
    };

    const sel = $('slPlayTemplate');
    const codeEl = $('slPlayCode');
    const outEl = $('slPlayOutput');
    const statusEl = $('slPlayStatus');

    if (sel) {
      sel.onchange = () => {
        if (templates[sel.value]) {
          codeEl.value = templates[sel.value];
          outEl.style.display = 'none';
        }
      };
    }

    $('slPlayClearBtn').onclick = () => {
      codeEl.value = 'program NewProgram.\n\n';
      outEl.style.display = 'none';
    };

    $('slPlayCheckBtn').onclick = async () => {
      if (!HOST_API) { needsHost(outEl, statusEl); return; }
      statusEl.textContent = 'Checking...';
      outEl.style.display = 'block';
      try {
        const data = await api(API + 'check', { source: codeEl.value });
        if (data.ok) {
          outEl.textContent = `✓ STATIC CHECK OK\nProgram: ${data.name || 'Untitled'}\nStatements: ${(data.plan || []).length}\nProfile: ${JSON.stringify(data.profile || {})}\n${staticSpecificationScore(data.predictability)}\n\nPlan:\n` +
            (data.plan || []).map(p => `  L${p.line} ${p.kind.padEnd(8)} ${p.label || ''} (${p.class || 'exact'})`).join('\n');
          outEl.style.border = '1px solid var(--ok)';
          statusEl.textContent = '✓ OK';
          toast('Syntax and typing valid!');
        } else {
          outEl.textContent = `✗ ERRORS:\n` + (data.errors || []).map(e => `Line ${e.line}: ${e.message}`).join('\n');
          outEl.style.border = '1px solid var(--err)';
          statusEl.textContent = 'Errors';
        }
      } catch (err) {
        outEl.textContent = `Request failed: ${err.message || err}`;
        outEl.style.border = '1px solid var(--err)';
      }
    };

    $('slPlayPreviewBtn').onclick = async () => {
      if (!HOST_API) { needsHost(outEl, statusEl); return; }
      statusEl.textContent = 'Previewing...';
      outEl.style.display = 'block';
      try {
        const data = await api(API + 'preview', { source: codeEl.value, inputs: {}, by: 'claude:haiku' });
        if (data.status === 'paused' && data.next) {
          outEl.textContent = `✓ MODEL CAPSULE:\nApplicator: ${data.next.app}\nPrompt:\n${data.next.prompt}\n\nSchema:\n${JSON.stringify(data.next.schema, null, 2)}`;
          outEl.style.border = '1px solid var(--acc)';
          statusEl.textContent = 'Capsule ready';
        } else if (data.status === 'done') {
          outEl.textContent = `Program executed entirely in the Kernel (0 model calls!). Outputs:\n${JSON.stringify(data.outputs, null, 2)}`;
          outEl.style.border = '1px solid var(--ok)';
          statusEl.textContent = 'Complete';
        } else {
          outEl.textContent = `Preview error: ${data.error || 'Failed'}`;
          outEl.style.border = '1px solid var(--err)';
        }
      } catch (err) {
        outEl.textContent = `Preview request failed: ${err.message || err}`;
        outEl.style.border = '1px solid var(--err)';
      }
    };
  }

  // ---------------------------------------------------------------------------
  // 1. Parsons Problems (Code Reordering Puzzles)
  // ---------------------------------------------------------------------------
  const PARSONS_PUZZLES = [
    {
      id: 'parsons-01',
      title: 'Spider Study with Transactional Rollback',
      desc: 'Arrange the code blocks into the correct sequential order: Program -> Invariant Expected -> Ask Model -> Transactional Ensure -> Output.',
      blocks: [
        { id: 'b1', text: 'program SpiderStudy.' },
        { id: 'b2', text: 'let expected = 8.' },
        { id: 'b3', text: 'ask legs: Int in 0..20 "How many legs does a spider have?" with effort=low' },
        { id: 'b4', text: 'ensure legs = expected else retry because "a spider has eight legs".' },
        { id: 'b5', text: 'show [expected, legs] as "Verified Legs".' }
      ]
    },
    {
      id: 'parsons-02',
      title: 'Transitive Datalog Family Tree',
      desc: 'Order the statements: Program -> Ground Facts -> Base Horn Rule -> Recursive Horn Rule -> Query -> Assert.',
      blocks: [
        { id: 'b1', text: 'program Ancestry.' },
        { id: 'b2', text: 'fact parent("Ada", "Ben").' },
        { id: 'b3', text: 'fact parent("Ben", "Cleo").' },
        { id: 'b4', text: 'rule ancestor(X, Y) if parent(X, Y).' },
        { id: 'b5', text: 'rule ancestor(X, Z) if parent(X, Y) and ancestor(Y, Z).' },
        { id: 'b6', text: 'let cleo_anc = query ancestor(Who, "Cleo").' },
        { id: 'b7', text: 'assert {"Who": "Ada"} in cleo_anc.' }
      ]
    },
    {
      id: 'parsons-03',
      title: 'Exact Rational Currency & Tax Auditor',
      desc: 'Order the statements: Program -> Input -> Exact Tax Fraction -> Computed Total -> Invariant Proof.',
      blocks: [
        { id: 'b1', text: 'program TaxAuditor.' },
        { id: 'b2', text: 'given subtotal: Number = 100.' },
        { id: 'b3', text: 'let tax_rate = 85 / 1000.' },
        { id: 'b4', text: 'let total = subtotal + (subtotal * tax_rate).' },
        { id: 'b5', text: 'assert total = 108.5 because "exact rational currency math".' },
        { id: 'b6', text: 'show total.' }
      ]
    }
  ];

  let parsonsState = {};

  function initParsons(pId) {
    const puzzle = PARSONS_PUZZLES.find(p => p.id === pId);
    if (!puzzle) return;
    const shuffled = [...puzzle.blocks].sort(() => Math.random() - 0.5);
    parsonsState[pId] = { available: shuffled, placed: [] };
  }

  function renderParsons(m) {
    m.innerHTML = `
      <div class="sl-hero">
        <span class="lbl">Cognitive Load Optimization</span>
        <h1 class="sl-title">Parsons Code Puzzles</h1>
        <p class="sl-sub">
          Arrange pre-written code blocks into the correct logical execution flow.
          <strong>Parsons Problems</strong> (Parsons & Haden) reduce syntax frustration while training the mental model of program structure.
        </p>
      </div>

      <div class="unit">
        ${PARSONS_PUZZLES.map(p => {
          if (!parsonsState[p.id]) initParsons(p.id);
          const st = parsonsState[p.id];
          return `
            <div class="card" style="margin-bottom:24px; padding:18px; border:1px solid var(--brd); border-radius:4px; background:var(--bg1);">
              <div style="font-size:16px; font-weight:600; margin-bottom:4px;">${esc(p.title)}</div>
              <p class="hint" style="margin-bottom:12px;">${esc(p.desc)}</p>

              <div class="sl-parsons-grid">
                <div class="sl-parsons-col">
                  <div class="sl-parsons-col-hdr">
                    <span>Available Blocks (Click to Add)</span>
                    <span class="mono">${st.available.length} left</span>
                  </div>
                  <div class="sl-parsons-list" id="parsons_avail_${p.id}">
                    ${st.available.map((b, i) => `
                      <div class="sl-parsons-item" data-pid="${p.id}" data-idx="${i}" data-src="avail">
                        <span>${esc(b.text)}</span>
                        <span style="color:var(--tx3)">+</span>
                      </div>
                    `).join('') || '<div class="empty hint" style="padding:16px; text-align:center;">All blocks placed!</div>'}
                  </div>
                </div>

                <div class="sl-parsons-col">
                  <div class="sl-parsons-col-hdr">
                    <span>Your Assembled Program (Click to Remove)</span>
                    <span class="mono">${st.placed.length}/${p.blocks.length}</span>
                  </div>
                  <div class="sl-parsons-list" id="parsons_placed_${p.id}">
                    ${st.placed.map((b, i) => `
                      <div class="sl-parsons-item target" data-pid="${p.id}" data-idx="${i}" data-src="placed">
                        <span><span class="num" style="color:var(--tx3); margin-right:8px;">${i + 1}</span>${esc(b.text)}</span>
                        <span style="color:var(--err)">×</span>
                      </div>
                    `).join('') || '<div class="empty hint" style="padding:16px; text-align:center;">Click blocks on the left to add them here in order.</div>'}
                  </div>
                </div>
              </div>

              <div style="display:flex; gap:10px; align-items:center; margin-top:12px;">
                <button class="btn" id="btn_parsons_chk_${p.id}">Check Alignment</button>
                <button class="btn alt" id="btn_parsons_rst_${p.id}">Reset Blocks</button>
                <span class="hint" id="status_parsons_${p.id}"></span>
              </div>
              <div id="feedback_parsons_${p.id}" style="margin-top:10px; font-size:13px; line-height:1.6; display:none; padding:10px 14px; border-radius:4px;"></div>
            </div>
          `;
        }).join('')}
      </div>
    `;

    // Event bindings for Parsons
    PARSONS_PUZZLES.forEach(p => {
      const st = parsonsState[p.id];
      const availEl = $(`parsons_avail_${p.id}`);
      const placedEl = $(`parsons_placed_${p.id}`);
      const chkBtn = $(`btn_parsons_chk_${p.id}`);
      const rstBtn = $(`btn_parsons_rst_${p.id}`);
      const feedEl = $(`feedback_parsons_${p.id}`);

      if (availEl) {
        availEl.querySelectorAll('.sl-parsons-item').forEach(item => {
          item.onclick = () => {
            const idx = parseInt(item.dataset.idx, 10);
            const block = st.available.splice(idx, 1)[0];
            st.placed.push(block);
            renderParsons(m);
          };
        });
      }

      if (placedEl) {
        placedEl.querySelectorAll('.sl-parsons-item').forEach(item => {
          item.onclick = () => {
            const idx = parseInt(item.dataset.idx, 10);
            const block = st.placed.splice(idx, 1)[0];
            st.available.push(block);
            renderParsons(m);
          };
        });
      }

      if (rstBtn) {
        rstBtn.onclick = () => {
          initParsons(p.id);
          renderParsons(m);
        };
      }

      if (chkBtn) {
        chkBtn.onclick = () => {
          feedEl.style.display = 'block';
          if (st.placed.length !== p.blocks.length) {
            feedEl.style.background = 'var(--err-bg)';
            feedEl.style.color = 'var(--err)';
            feedEl.textContent = `Incomplete program: please place all ${p.blocks.length} blocks before checking.`;
            return;
          }
          let allCorrect = true;
          for (let i = 0; i < p.blocks.length; i++) {
            if (st.placed[i].id !== p.blocks[i].id) {
              allCorrect = false;
              break;
            }
          }
          if (allCorrect) {
            feedEl.style.background = 'var(--krn-bg)';
            feedEl.style.color = 'var(--ok)';
            feedEl.textContent = '✓ Perfect execution order! The statements satisfy all single-assignment and anchored retry requirements.';
            toast('Puzzle solved correctly!');
          } else {
            feedEl.style.background = 'var(--err-bg)';
            feedEl.style.color = 'var(--err)';
            feedEl.textContent = 'Order mismatch: Remember that bindings (`let`) must precede their use, `ask` must precede `ensure`, and `program` must come first.';
          }
        };
      }
    });
  }

  // ---------------------------------------------------------------------------
  // 2. Spot-The-Bug / Bug Hunt (Error Detection)
  // ---------------------------------------------------------------------------
  const BUG_HUNTS = [
    {
      id: 'bug-01',
      title: 'The Missing Capsule Scope (Context Rot)',
      desc: 'Find the missing input dependency: the model cannot inspect the email needed for this task.',
      lines: [
        'program ExtractOrder.',
        'given email: Text = "Order #842 from Alice".',
        'define Res as Record { order_id: Text, customer: Text }.',
        'ask extracted: Res "Extract order details."',
        'ensure starts_with(extracted.order_id, "#") else retry.',
        'show extracted.'
      ],
      bugLine: 4, // 1-indexed: line 4
      diagnosis: 'Line 4 misses `from email`! Without `from email` or an interpolation, this ask does not supply the email. The answer is unsupported; the model might guess or refuse.',
      fix: 'ask extracted: Res "Extract order details." from email'
    },
    {
      id: 'bug-02',
      title: 'The Floating-Point Contamination',
      desc: 'Find the line that violates exact rational arithmetic by expecting an IEEE float representation.',
      lines: [
        'program ExactMathProof.',
        'let a = 0.1 + 0.2.',
        'assert a = 0.30000000000000004 because "floating point check".',
        'let half = 1 / 2.',
        'assert half * 2 = 1.',
        'show a.'
      ],
      bugLine: 3,
      diagnosis: 'Line 3 expects `0.30000000000000004`! Symblic Kernel uses exact rational arithmetic in field Q (1/10 + 2/10 = 3/10 = 0.3). The assert fails.',
      fix: 'assert a = 0.3 because "exact rational arithmetic".'
    },
    {
      id: 'bug-03',
      title: 'The Unrecoverable Crash (Missing else retry)',
      desc: 'Find the line where a condition failure causes the entire system to crash instead of self-correcting.',
      lines: [
        'program TriageSystem.',
        'ask priority: one of {low, med, high} "Triage patient: severe pain"',
        'ensure priority = "high" because "severe pain requires high triage".',
        'show priority.'
      ],
      bugLine: 3,
      diagnosis: 'Line 3 has `ensure ... because ...` without `else retry`! By default, a bare ensure that fails halts the run immediately with an error rather than rolling back and retrying.',
      fix: 'ensure priority = "high" else retry because "severe pain requires high triage".'
    },
    {
      id: 'bug-04',
      title: 'Non-Ground Datalog Fact Violation',
      desc: 'Find the line that violates the Datalog relational requirement that facts must be ground.',
      lines: [
        'program SecurityGraph.',
        'fact user("Alice").',
        'fact user("Bob").',
        'fact access(Who, "Admin").',
        'rule can_enter(U) if user(U) and access(U, "Admin").',
        'let admins = query can_enter(X).'
      ],
      bugLine: 4,
      diagnosis: 'Line 4 uses an uppercase logic variable `Who` inside a `fact`! In Datalog, facts represent ground truths and cannot contain unbound variables. Variables belong only in `rule` heads and bodies.',
      fix: 'fact access("Alice", "Admin").'
    }
  ];

  let bugHuntState = {};

  function renderBugHunt(m) {
    m.innerHTML = `
      <div class="sl-hero">
        <span class="lbl">Error Detection Heuristics</span>
        <h1 class="sl-title">Spot-The-Bug: Diagnostic Challenges</h1>
        <p class="sl-sub">
          Finding the faulty line is practice in reading a program closely.
          Click on the buggy line in each program to diagnose the defect.
        </p>
      </div>

      <div class="unit">
        ${BUG_HUNTS.map(b => {
          const st = bugHuntState[b.id] || { selectedLine: null, solved: false, showFix: false };
          bugHuntState[b.id] = st;
          return `
            <div class="sl-bughunt-card" id="bughunt_${b.id}">
              <div style="font-size:16px; font-weight:600; margin-bottom:4px;">${esc(b.title)}</div>
              <p class="hint" style="margin-bottom:10px;">${esc(b.desc)}</p>

              <div class="sl-code-lines" id="lines_${b.id}" tabindex="0">
                ${b.lines.map((l, idx) => {
                  const lineNum = idx + 1;
                  const isSel = st.selectedLine === lineNum;
                  const isBug = st.solved && lineNum === b.bugLine;
                  return `
                    <div class="sl-code-line ${isSel ? 'selected' : ''} ${isBug ? 'bug-found' : ''}" data-bid="${b.id}" data-line="${lineNum}">
                      <span class="sl-line-num">${lineNum}</span>
                      <span class="sl-line-text">${esc(l)}</span>
                    </div>
                  `;
                }).join('')}
              </div>

              <div style="display:flex; gap:10px; align-items:center; margin-top:12px;">
                <button class="btn sm" id="btn_bughunt_chk_${b.id}">Confirm Buggy Line</button>
                <button class="btn sm alt" id="btn_bughunt_fix_${b.id}">Show the fix</button>
                <span class="hint" id="status_bughunt_${b.id}">
                  ${st.selectedLine ? `Line ${st.selectedLine} selected` : 'Click a line above'}
                </span>
              </div>

              <div id="diag_bughunt_${b.id}" style="margin-top:12px; font-size:13.5px; line-height:1.6; display:${st.solved ? 'block' : 'none'}; padding:12px 14px; border-radius:4px; background:var(--bg2); border-left:3px solid var(--ok);">
                <div class="lbl" style="color:var(--ok)">Diagnostic Report</div>
                <p style="margin:4px 0 8px;">${esc(b.diagnosis)}</p>
                <div style="display:${st.showFix ? 'block' : 'none'};" id="fix_wrap_${b.id}">
                  <span class="lbl" style="color:var(--acc-tx)">Fix</span>
                  <code style="font-family:var(--mono); background:var(--bg1); padding:4px 8px; border:1px solid var(--brd); border-radius:3px; display:inline-block; margin-top:4px;">${esc(b.fix)}</code>
                </div>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;

    BUG_HUNTS.forEach(b => {
      const st = bugHuntState[b.id];
      const wrap = $(`lines_${b.id}`);
      const chkBtn = $(`btn_bughunt_chk_${b.id}`);
      const fixBtn = $(`btn_bughunt_fix_${b.id}`);
      const diagEl = $(`diag_bughunt_${b.id}`);
      const fixWrap = $(`fix_wrap_${b.id}`);
      const statusEl = $(`status_bughunt_${b.id}`);

      if (wrap) {
        wrap.querySelectorAll('.sl-code-line').forEach(line => {
          line.onclick = () => {
            const lineNum = parseInt(line.dataset.line, 10);
            st.selectedLine = lineNum;
            wrap.querySelectorAll('.sl-code-line').forEach(l => l.classList.remove('selected'));
            line.classList.add('selected');
            statusEl.textContent = `Line ${lineNum} selected`;
          };
        });
      }

      if (chkBtn) {
        chkBtn.onclick = () => {
          if (!st.selectedLine) {
            toast('Please click a line first!');
            return;
          }
          if (st.selectedLine === b.bugLine) {
            st.solved = true;
            diagEl.style.display = 'block';
            statusEl.textContent = '✓ Bug accurately identified!';
            statusEl.style.color = 'var(--ok)';
            toast('Bug found!');
            renderBugHunt(m);
          } else {
            statusEl.textContent = `✗ Line ${st.selectedLine} is syntactically sound. Look elsewhere!`;
            statusEl.style.color = 'var(--err)';
          }
        };
      }

      if (fixBtn) {
        fixBtn.onclick = () => {
          st.showFix = !st.showFix;
          if (fixWrap) fixWrap.style.display = st.showFix ? 'block' : 'none';
        };
      }
    });
  }

  // ---------------------------------------------------------------------------
  // 3. Interactive Stepper & Rollback Simulator (Mental Model Engine)
  // ---------------------------------------------------------------------------
  const STEPPER_STAGES = [
    {
      step: 1,
      title: 'Program Parse',
      code: 'program SpiderAudit.\nlet target = 8.\nask legs: Int in 0..20 "How many legs?"\nensure legs = target else retry.\nshow legs.',
      highlight: 1,
      memory: { program: 'SpiderAudit', bindings: {}, facts: 0 },
      capsule: 'None (Kernel initialization)',
      verdict: 'AST built. Deterministic single-assignment environment initialized.'
    },
    {
      step: 2,
      title: 'Kernel Exact Computation',
      code: 'program SpiderAudit.\nlet target = 8.  <-- EXECUTING\nask legs: Int in 0..20 "How many legs?"\nensure legs = target else retry.\nshow legs.',
      highlight: 2,
      memory: { program: 'SpiderAudit', bindings: { target: 8 }, facts: 0 },
      capsule: 'None (Kernel step)',
      verdict: 'Kernel binds `target = 8` (exact Int). Zero model calls. Single-assignment lock engaged.'
    },
    {
      step: 3,
      title: 'Checkpoint & Capsule Generation',
      code: 'program SpiderAudit.\nlet target = 8.\nask legs: Int in 0..20 "How many legs?"  <-- SNAPSHOT & CAPSULE\nensure legs = target else retry.\nshow legs.',
      highlight: 3,
      memory: { program: 'SpiderAudit', bindings: { target: 8 }, checkpoint: 'Snapshot taken' },
      capsule: 'PROGRAM: SpiderAudit\nKNOWN: target = 8\nSTATEMENT: ask legs: Int in 0..20\nSCHEMA: {"answer": {"type": "integer", "min": 0, "max": 20}}',
      verdict: 'Internal state snapshot saved. Explicit inputs and schema selected. The model can still return an incorrect answer.'
    },
    {
      step: 4,
      title: 'Model Returns Faulty Answer',
      code: 'program SpiderAudit.\nlet target = 8.\nask legs: Int in 0..20 "How many legs?"  <-- RECEIVED legs = 6\nensure legs = target else retry.\nshow legs.',
      highlight: 3,
      memory: { program: 'SpiderAudit', bindings: { target: 8, legs: 6 } },
      capsule: 'Response: {"answer": 6}',
      verdict: 'Model returned 6. Coerced to Int in 0..20. Handed to Kernel for verification.'
    },
    {
      step: 5,
      title: 'Postcondition Fails',
      code: 'program SpiderAudit.\nlet target = 8.\nask legs: Int in 0..20 "How many legs?"\nensure legs = target else retry.  <-- FAILED (6 != 8)\nshow legs.',
      highlight: 4,
      memory: { program: 'SpiderAudit', bindings: { target: 8, legs: 6 }, failed_condition: 'legs = target' },
      capsule: 'Condition evaluated: 6 = 8 ==> FALSE',
      verdict: 'INVARIANT VIOLATION: `legs = target` evaluated to false. `else retry` triggers rollback!'
    },
    {
      step: 6,
      title: 'Transactional State Rollback',
      code: 'program SpiderAudit.\nlet target = 8.\nask legs: Int in 0..20 ...  <-- RESTORE SNAPSHOT & INJECT FEEDBACK\nensure legs = target else retry.\nshow legs.',
      highlight: 3,
      memory: { program: 'SpiderAudit', bindings: { target: 8 }, rollback: 'Restored snapshot', feedback: 'Rejected 6 (failed legs = target)' },
      capsule: 'FEEDBACK ADDED TO CAPSULE:\n"Your previous answer 6 failed condition: legs = target (four pairs). Try again."',
      verdict: 'TRANSACTIONAL ROLLBACK: `legs: 6` erased from memory. Error feedback injected into next prompt.'
    },
    {
      step: 7,
      title: 'Retry Model Pass & Ledger Commit',
      code: 'program SpiderAudit.\nlet target = 8.\nask legs: Int in 0..20 ...  <-- MODEL RETURNS 8\nensure legs = target else retry.  <-- PASSES (8 = 8)\nshow [target, legs] as "Verified Legs".',
      highlight: 5,
      memory: { program: 'SpiderAudit', bindings: { target: 8, legs: 8 }, outputs: ['Verified Legs: [8, 8]'] },
      capsule: 'Response: {"answer": 8} ==> Invariant Passed!',
      verdict: 'Declared equality passed. The fingerprint identifies recorded canonical values; it does not establish the premise about spiders.'
    }
  ];

  let currentStepperStep = 1;

  function renderStepper(m) {
    const cur = STEPPER_STAGES[currentStepperStep - 1];

    m.innerHTML = `
      <div class="sl-hero">
        <span class="lbl">State Machine Simulation</span>
        <h1 class="sl-title">Interactive Execution & Rollback Stepper</h1>
        <p class="sl-sub">
          Step through a live execution trace to watch how the <strong>Deterministic Kernel</strong>,
          the <strong>Explicit Context Capsule</strong>, and the <strong>Transactional Rollback Engine</strong> interact.
        </p>
      </div>

      <div class="unit">
        <div class="sl-stepper-box">
          <div class="sl-timeline" tabindex="0">
            ${STEPPER_STAGES.map(s => {
              const isPast = s.step < currentStepperStep;
              const isCur = s.step === currentStepperStep;
              const isRb = s.step === 6;
              let cls = isCur ? 'active' : (isPast ? 'passed' : '');
              if (isRb && isCur) cls += ' rollback';
              return `
                <div class="sl-step-node ${cls}" data-step="${s.step}">
                  <div class="sl-step-dot">${s.step}</div>
                  <div class="sl-step-lbl">${esc(s.title.split(' ')[0])}</div>
                </div>
              `;
            }).join('')}
          </div>

          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
            <div style="font-size:16px; font-weight:700;">Stage ${cur.step}: ${esc(cur.title)}</div>
            <div style="display:flex; gap:8px;">
              <button class="btn sm" id="btn_step_prev" ${currentStepperStep === 1 ? 'disabled' : ''}>← Previous</button>
              <button class="btn sm primary" id="btn_step_next" ${currentStepperStep === STEPPER_STAGES.length ? 'disabled' : ''}>Next Step →</button>
              <button class="btn sm alt" id="btn_step_reset">Reset</button>
            </div>
          </div>

          <div class="sl-step-view">
            <div class="sl-view-panel">
              <h4>Program Execution Flow</h4>
              <div class="sl-state-pre" style="line-height:1.7;">${esc(cur.code)}</div>
              <div style="margin-top:12px; font-size:13px; color:var(--tx2);">
                <strong>Runtime Verdict:</strong> ${esc(cur.verdict)}
              </div>
            </div>

            <div class="sl-view-panel">
              <h4>Kernel Memory Ledger & Capsule Inspector</h4>
              <div class="sl-state-pre" style="color:#60a5fa;"><strong>// CURRENT BINDINGS:</strong>\n${JSON.stringify(cur.memory, null, 2)}</div>
              <div class="sl-state-pre" style="margin-top:10px; color:#f59e0b;"><strong>// CAPSULE STATE:</strong>\n${esc(cur.capsule)}</div>
            </div>
          </div>
        </div>
      </div>
    `;

    // Event listeners
    m.querySelectorAll('.sl-step-node').forEach(node => {
      node.onclick = () => {
        currentStepperStep = parseInt(node.dataset.step, 10);
        renderStepper(m);
      };
    });

    const nextBtn = $('btn_step_next');
    const prevBtn = $('btn_step_prev');
    const rstBtn = $('btn_step_reset');

    if (nextBtn) {
      nextBtn.onclick = () => {
        if (currentStepperStep < STEPPER_STAGES.length) {
          currentStepperStep++;
          renderStepper(m);
        }
      };
    }

    if (prevBtn) {
      prevBtn.onclick = () => {
        if (currentStepperStep > 1) {
          currentStepperStep--;
          renderStepper(m);
        }
      };
    }

    if (rstBtn) {
      rstBtn.onclick = () => {
        currentStepperStep = 1;
        renderStepper(m);
      };
    }
  }

  // ---------------------------------------------------------------------------
  // 4. 60-Second Rapid-Fire Speed Drill (Fluency & Automaticity)
  // ---------------------------------------------------------------------------
  const SPEED_DRILL_ITEMS = [
    { q: 'In Symblic, 0.1 + 0.2 = 0.3 evaluates to true exactly.', ans: true, why: 'Exact rational field Q.' },
    { q: 'Can an AI model write directly to Kernel memory variables?', ans: false, why: 'Models are untrusted; only Kernel binds let.' },
    { q: 'Datalog logic variables must begin with an uppercase letter.', ans: true, why: 'Horn clauses require capital logic variables.' },
    { q: 'Is the maximum integer digit limit 4,000 digits?', ans: true, why: 'MAX_DIGITS = 4000 bounds integer representations; other work limits still matter.' },
    { q: 'Does effort=ultra run an anonymized second-round peer jury?', ans: true, why: 'ultra samples 5 votes + runs jury deliberation.' },
    { q: 'Does an assert statement trigger an automatic transactional retry loop?', ans: false, why: 'assert halts immediately. ensure triggers retries.' },
    { q: 'Are List types in Symblic 0-indexed like Python?', ans: false, why: 'Lists in Symblic are 1-indexed!' },
    { q: 'Does the Kernel evaluate transcendentals using standard C libm floats?', ans: false, why: 'Kernel uses 40-digit Decimal series expansions.' },
    { q: 'Can compatibility coercion normalize enum spelling?', ans: true, why: 'Compatibility mode can normalize spelling; strict validation has a separate contract.' },
    { q: 'Does `ensure else retry` restore the internal state at its anchor?', ans: true, why: 'Internal retry state is restored; external effects use separate recovery rules.' },
    { q: 'Does Datalog use open-world assumption in Symblic?', ans: false, why: 'Stratified closed-world negation-as-failure.' },
    { q: 'Does a schema-valid model reply itself authorize an external action?', ans: false, why: 'Host capabilities and policy authorize effects; a valid answer schema grants no authority.' },
    { q: 'May a verified pure function invoke a model routine?', ans: false, why: 'Verified functions reject transitive routines and effects, including imports. Legacy functions may bridge routines.' },
    { q: 'Does Canonical Form 3 sort dictionary keys and set members?', ans: true, why: 'Canonical ordering contributes to stable hashes under the pinned rules; a hash is not evidence of truth.' },
    { q: 'Does the Capsule send the entire historical chat scroll to the model?', ans: false, why: 'Capsules select context explicitly; required dependencies still matter.' }
  ];

  let speedState = {
    running: false,
    timeLeft: 60,
    score: 0,
    combo: 0,
    maxCombo: 0,
    index: 0,
    timerId: null,
    done: false
  };

  function renderSpeed(m) {
    if (!speedState.running && !speedState.done) {
      m.innerHTML = `
        <div class="sl-hero">
          <span class="lbl">Syntactic Fluency</span>
          <h1 class="sl-title">60-Second Rapid-Fire Speed Drill</h1>
          <p class="sl-sub">
            Train automaticity (Schneider & Shiffrin). Answer rapid True/False statements against the clock to build
            faster recall of the statements practised in this round.
          </p>
        </div>

        <div class="unit">
          <div class="sl-speed-arena">
            <div style="font-size:48px; margin-bottom:12px;">⚡</div>
            <h2 style="font-size:22px; margin-bottom:8px;">Ready for the 60-Second Challenge?</h2>
            <p class="hint" style="max-width:440px; margin:0 auto 20px;">
              You have 60 seconds to answer as many questions as possible.
              Keyboard shortcuts: <strong>J</strong> for True, <strong>K</strong> for False.
            </p>
            <button class="btn primary" id="btn_start_speed" style="padding:12px 28px; font-size:16px;">Start Challenge</button>
          </div>
        </div>
      `;

      $('btn_start_speed').onclick = () => {
        startSpeedDrill(m);
      };
      return;
    }

    if (speedState.done) {
      const accuracy = Math.round((speedState.score / (speedState.index || 1)) * 100);
      let rank = 'Symblic Apprentice';
      if (speedState.score >= 12) rank = 'Master Symblic Architect';
      else if (speedState.score >= 8) rank = 'Practised Reader';

      m.innerHTML = `
        <div class="sl-hero">
          <span class="lbl">Challenge Results</span>
          <h1 class="sl-title">Drill Completed!</h1>
        </div>

        <div class="unit">
          <div class="sl-speed-arena">
            <div style="font-size:42px; color:var(--acc); margin-bottom:8px;">🏆</div>
            <div style="font-size:26px; font-weight:700; margin-bottom:4px;">Rank: ${esc(rank)}</div>
            <p class="hint" style="margin-bottom:20px;">You answered ${speedState.score} correctly with a max streak of ${speedState.maxCombo}!</p>

            <div class="sl-stats-bar" style="max-width:480px; margin:0 auto 20px;">
              <div class="sl-stat-box"><span class="sl-stat-val" style="color:var(--ok)">${speedState.score}</span><span class="sl-stat-lbl">Correct</span></div>
              <div class="sl-stat-box"><span class="sl-stat-val" style="color:var(--acc)">${speedState.maxCombo}</span><span class="sl-stat-lbl">Max Combo</span></div>
              <div class="sl-stat-box"><span class="sl-stat-val">${accuracy}%</span><span class="sl-stat-lbl">Accuracy</span></div>
            </div>

            <button class="btn primary" id="btn_restart_speed">Try Again</button>
          </div>
        </div>
      `;

      $('btn_restart_speed').onclick = () => {
        speedState.done = false;
        speedState.running = false;
        renderSpeed(m);
      };
      return;
    }

    const cur = SPEED_DRILL_ITEMS[speedState.index % SPEED_DRILL_ITEMS.length];

    m.innerHTML = `
      <div class="sl-hero">
        <span class="lbl">Fluency Drill</span>
        <h1 class="sl-title">Speed Automaticity Trainer</h1>
      </div>

      <div class="unit">
        <div class="sl-speed-arena">
          <div class="sl-speed-timer-bar">
            <div class="sl-speed-timer-fill" id="speedTimerFill" style="width:${(speedState.timeLeft / 60) * 100}%"></div>
          </div>

          <div class="sl-speed-score-row">
            <div><span class="lbl">Time Left</span><span style="font-size:20px; font-weight:700;">${speedState.timeLeft}s</span></div>
            <div>
              <span class="sl-speed-combo">${speedState.combo > 1 ? `COMBO x${speedState.combo} 🔥` : 'Active'}</span>
            </div>
            <div><span class="lbl">Score</span><span style="font-size:20px; font-weight:700; color:var(--ok);">${speedState.score}</span></div>
          </div>

          <div class="sl-speed-prompt" id="speedPrompt">${esc(cur.q)}</div>

          <div class="sl-speed-actions">
            <button class="sl-speed-btn t" id="btn_ans_true">
              <span>TRUE [J]</span>
            </button>
            <button class="sl-speed-btn f" id="btn_ans_false">
              <span>FALSE [K]</span>
            </button>
          </div>
        </div>
      </div>
    `;

    $('btn_ans_true').onclick = () => submitSpeedAnswer(true, m);
    $('btn_ans_false').onclick = () => submitSpeedAnswer(false, m);
  }

  function startSpeedDrill(m) {
    speedState = {
      running: true,
      timeLeft: 60,
      score: 0,
      combo: 0,
      maxCombo: 0,
      index: 0,
      timerId: null,
      done: false
    };

    speedState.timerId = setInterval(() => {
      speedState.timeLeft--;
      if (speedState.timeLeft <= 0) {
        clearInterval(speedState.timerId);
        speedState.running = false;
        speedState.done = true;
        renderSpeed(m);
      } else {
        const fill = $('speedTimerFill');
        if (fill) fill.style.width = `${(speedState.timeLeft / 60) * 100}%`;
      }
    }, 1000);

    renderSpeed(m);
  }

  function submitSpeedAnswer(userAns, m) {
    if (!speedState.running) return;
    const cur = SPEED_DRILL_ITEMS[speedState.index % SPEED_DRILL_ITEMS.length];
    if (userAns === cur.ans) {
      speedState.score++;
      speedState.combo++;
      if (speedState.combo > speedState.maxCombo) speedState.maxCombo = speedState.combo;
      toast(`✓ ${cur.why}`);
    } else {
      speedState.combo = 0;
      toast(`✗ Incorrect: ${cur.why}`);
    }
    speedState.index++;
    renderSpeed(m);
  }

  // ---------------------------------------------------------------------------
  // 5. Feynman Technique Coach (Elaborative Interrogation)
  // ---------------------------------------------------------------------------
  const FEYNMAN_TOPICS = [
    {
      id: 'feynman-01',
      title: 'Exact Rational Math vs Floating Point',
      prompt: 'Explain why the Symblic Kernel strictly enforces exact rational arithmetic (Q) instead of IEEE 754 floating point numbers to a junior developer.',
      keywords: ['float', 'rounding', 'exact', 'fraction', 'p/q', '0.1', '0.3', 'associative', 'reproducib', 'deterministic'],
      required: ['rounding or precision error', 'fractions or p/q', 'determinism or cross-platform'],
      exemplar: 'Exact rational arithmetic represents supported ratios without binary rounding: 1/10 + 2/10 = 3/10. That helps check the encoded calculation. Measurement uncertainty, mistaken units and an incorrect specification remain possible. Approximate operations have separate precision contracts, and cross-platform claims require versioned conformance evidence.'
    },
    {
      id: 'feynman-02',
      title: 'The Capsule Pattern vs Chat History Scroll',
      prompt: 'Explain the benefits and limits of explicit capsules, including omitted evidence and untrusted source text.',
      keywords: ['capsule', 'context', 'schema', 'evidence', 'required', 'dependency', 'limit', 'unknown', 'input', 'from'],
      required: ['required input or required context', 'missing evidence or missing dependency', 'does not guarantee or cannot guarantee'],
      exemplar: 'A capsule makes the selected context explicit. The caller must supply required inputs, definitions and source dependencies, including exceptions. This can reduce irrelevant material, but a missing dependency can make an answer unsupported. A capsule cannot guarantee attention, source truth or resistance to every injected instruction.'
    },
    {
      id: 'feynman-03',
      title: 'Transactional State Rollbacks in ensure Loops',
      prompt: 'Explain what happens under the hood when a model\'s answer fails an `ensure ... else retry` postcondition.',
      keywords: ['snapshot', 'rollback', 'restore', 'state', 'feedback', 'anchor', 'retry', 'clean', 'binding'],
      required: ['state snapshot or checkpoint', 'rollback or restore', 'feedback injection'],
      exemplar: 'The runner keeps a checkpoint of relevant internal state at a retry anchor. A failed condition can restore that state, add rejected-answer feedback and retry within the configured budget. The check establishes its encoded predicate, not the truth of every premise. External effects are fenced and tracked separately; restoring variables cannot undo an action already performed.'
    }
  ];

  FEYNMAN_TOPICS[0].exemplar = MASTERY_LEVELS[0]?.bites?.[1]?.concept || FEYNMAN_TOPICS[0].exemplar;
  FEYNMAN_TOPICS[1].prompt = 'Explain the benefits and limits of an explicit capsule, including what happens when needed context is omitted.';
  FEYNMAN_TOPICS[1].exemplar = MASTERY_LEVELS[2]?.bites?.[2]?.concept || FEYNMAN_TOPICS[1].exemplar;

  function renderFeynman(m) {
    m.innerHTML = `
      <div class="sl-hero">
        <span class="lbl">Self-Explanation Effect</span>
        <h1 class="sl-title">Feynman Technique Self-Explanation Coach</h1>
        <p class="sl-sub">
          Explain a concept in plain language, work an example and state its limits. The keyword rubric below is a writing aid, not a test of truth or a certification of mastery; compare your reasoning with the model explanation.
        </p>
      </div>

      <div class="unit">
        ${FEYNMAN_TOPICS.map(t => `
          <div class="sl-feynman-card" id="feynman_${t.id}">
            <div style="font-size:16px; font-weight:700; margin-bottom:6px;">${esc(t.title)}</div>
            <div class="sl-feynman-prompt-box">
              <strong>Challenge:</strong> ${esc(t.prompt)}
            </div>

            <textarea class="sl-feynman-area" id="input_feynman_${t.id}" placeholder="Type your plain-English explanation here..."></textarea>

            <div style="display:flex; gap:10px; align-items:center; margin-top:10px;">
              <button class="btn" id="btn_feynman_eval_${t.id}">Check Rubric Terms</button>
              <button class="btn alt" id="btn_feynman_exemplar_${t.id}">Show Worked Explanation</button>
            </div>

            <div class="sl-feynman-rubric" id="rubric_${t.id}">
              <div class="sl-rubric-score" id="score_${t.id}">Keyword rubric: 0 / 100</div>
              <ul class="sl-rubric-items" id="items_${t.id}"></ul>
              <div style="margin-top:12px; padding:10px; background:var(--bg1); border-radius:4px; display:none;" id="exemplar_${t.id}">
                <div class="lbl" style="color:var(--ok)">Worked Explanation</div>
                <p style="font-size:13.5px; line-height:1.6; margin-top:6px;">${esc(t.exemplar)}</p>
              </div>
            </div>
          </div>
        `).join('')}
      </div>
    `;

    FEYNMAN_TOPICS.forEach(t => {
      const evalBtn = $(`btn_feynman_eval_${t.id}`);
      const exBtn = $(`btn_feynman_exemplar_${t.id}`);
      const inputEl = $(`input_feynman_${t.id}`);
      const rubricEl = $(`rubric_${t.id}`);
      const scoreEl = $(`score_${t.id}`);
      const itemsEl = $(`items_${t.id}`);
      const exemplarEl = $(`exemplar_${t.id}`);

      if (evalBtn) {
        evalBtn.onclick = () => {
          const text = inputEl.value.toLowerCase().trim();
          if (text.length < 30) {
            toast('Please write at least a couple of sentences!');
            return;
          }

          rubricEl.style.display = 'block';

          let matchedKeywords = 0;
          t.keywords.forEach(kw => {
            if (text.includes(kw)) matchedKeywords++;
          });

          let matchedReq = 0;
          const reqFeedback = t.required.map(req => {
            const parts = req.split(' or ');
            const found = parts.some(p => text.includes(p));
            if (found) matchedReq++;
            return `<li style="color:${found ? 'var(--ok)' : 'var(--err)'}">
              ${found ? '✓ Phrase matched:' : '✗ No phrase match:'} "${esc(req)}"
            </li>`;
          });

          const pct = Math.min(100, Math.round(((matchedKeywords / t.keywords.length) * 40) + ((matchedReq / t.required.length) * 60)));
          scoreEl.textContent = `Keyword rubric: ${pct} / 100`;
          scoreEl.style.color = pct >= 70 ? 'var(--ok)' : (pct >= 40 ? 'var(--warn)' : 'var(--err)');

          itemsEl.innerHTML = reqFeedback.join('') +
            `<li style="margin-top:6px; color:var(--tx2);">Substring matches: ${matchedKeywords}/${t.keywords.length} keywords and ${matchedReq}/${t.required.length} phrase groups. Score weights: 40 points for keywords, 60 for phrases. Negation and reasoning are not evaluated.</li>`;

          toast(`Keyword coverage: ${pct} / 100`);
        };
      }

      if (exBtn) {
        exBtn.onclick = () => {
          rubricEl.style.display = 'block';
          exemplarEl.style.display = exemplarEl.style.display === 'block' ? 'none' : 'block';
        };
      }
    });
  }

  // ---------------------------------------------------------------------------
  // 6. Metacognitive Mastery Dashboard & Leitner Box Curves
  // ---------------------------------------------------------------------------
  function renderMetacognition(m) {
    const boxCounts = [0, 0, 0, 0, 0];
    FLASHCARDS.forEach(c => {
      const st = getCardState(c.id);
      if (st.reps === 0) boxCounts[0]++;
      else if (st.reps === 1) boxCounts[1]++;
      else if (st.reps === 2) boxCounts[2]++;
      else if (st.reps === 3) boxCounts[3]++;
      else boxCounts[4]++;
    });

    const mastered = boxCounts[3] + boxCounts[4];
    const total = FLASHCARDS.length;
    const readiness = Math.round((mastered / total) * 100);

    m.innerHTML = `
      <div class="sl-hero">
        <span class="lbl">Study Progress</span>
        <h1 class="sl-title">Review History & Spaced Practice</h1>
        <p class="sl-sub">
          Review five groups based on Good/Easy ratings since the last Again reset. Hard ratings leave this count unchanged. The practice scheduler uses minute-scale intervals.
          The diagram is illustrative: it is not fitted to your memory, a measured retention rate or a personal forecast.
        </p>
      </div>

      <div class="unit">
        <div class="card" style="padding:20px; border:1px solid var(--brd); border-radius:4px; background:var(--bg1); margin-bottom:20px;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
            <div>
              <div class="lbl">Cards with at least 3 Good/Easy ratings since reset</div>
              <div style="font-size:28px; font-weight:700; color:var(--ok);">${readiness}% of deck</div>
            </div>
            <div>
              <a class="btn primary" href="#flashcards" style="text-decoration:none;">Review Due Cards Now</a>
            </div>
          </div>

          <h4 style="margin:16px 0 8px; font-size:13px; font-family:var(--mono); letter-spacing:0.1em; text-transform:uppercase;">Five Review Groups</h4>
          <div class="sl-leitner-grid">
            <div class="sl-leitner-box">
              <span class="sl-leitner-num" style="color:var(--tx1);">${boxCounts[0]}</span>
              <span class="sl-leitner-title">Group 1</span>
              <span class="sl-leitner-freq">0 successful ratings</span>
            </div>
            <div class="sl-leitner-box">
              <span class="sl-leitner-num" style="color:var(--tx1);">${boxCounts[1]}</span>
              <span class="sl-leitner-title">Group 2</span>
              <span class="sl-leitner-freq">1 successful rating</span>
            </div>
            <div class="sl-leitner-box">
              <span class="sl-leitner-num" style="color:var(--tx1);">${boxCounts[2]}</span>
              <span class="sl-leitner-title">Group 3</span>
              <span class="sl-leitner-freq">2 successful ratings</span>
            </div>
            <div class="sl-leitner-box">
              <span class="sl-leitner-num" style="color:var(--ok);">${boxCounts[3]}</span>
              <span class="sl-leitner-title">Group 4</span>
              <span class="sl-leitner-freq">3 successful ratings</span>
            </div>
            <div class="sl-leitner-box">
              <span class="sl-leitner-num" style="color:var(--ok);">${boxCounts[4]}</span>
              <span class="sl-leitner-title">Group 5</span>
              <span class="sl-leitner-freq">4+ successful ratings</span>
            </div>
          </div>
        </div>

        <div class="sl-diagram-card">
          <div class="lbl">Illustration: Recall Can Change with Time and Practice</div>
          <svg class="sl-diagram-svg" viewBox="0 0 700 240" role="img" aria-label="Illustrative recall curves with and without review, not measured or predicted retention">
            <!-- Axes -->
            <line x1="60" y1="200" x2="660" y2="200" stroke="var(--brd)" stroke-width="2"/>
            <line x1="60" y1="20" x2="60" y2="200" stroke="var(--brd)" stroke-width="2"/>
            <text x="50" y="30" font-family="var(--mono)" font-size="10" fill="var(--tx3)" text-anchor="end">High</text>
            <text x="50" y="110" font-family="var(--mono)" font-size="10" fill="var(--tx3)" text-anchor="end">Mid</text>
            <text x="50" y="200" font-family="var(--mono)" font-size="10" fill="var(--tx3)" text-anchor="end">Low</text>
            <text x="60" y="220" font-family="var(--mono)" font-size="10" fill="var(--tx3)">Start</text>
            <text x="210" y="220" font-family="var(--mono)" font-size="10" fill="var(--tx3)">Later</text>
            <text x="360" y="220" font-family="var(--mono)" font-size="10" fill="var(--tx3)">Later</text>
            <text x="510" y="220" font-family="var(--mono)" font-size="10" fill="var(--tx3)">Later</text>
            <text x="660" y="220" font-family="var(--mono)" font-size="10" fill="var(--tx3)">Time</text>

            <!-- Forgetting Curve 1 (Standard forgetting: red) -->
            <path d="M 60 30 Q 120 170 300 190" fill="none" stroke="var(--err)" stroke-width="2" stroke-dasharray="4"/>
            <text x="170" y="150" font-family="var(--sans)" font-size="11" fill="var(--err)">Illustration without review</text>

            <!-- Spaced repetition boosts: green curve -->
            <path d="M 60 30 Q 100 120 140 140 L 140 30 Q 200 80 260 100 L 260 30 Q 380 60 500 70 L 500 30 Q 600 40 660 45" fill="none" stroke="var(--ok)" stroke-width="2.5"/>
            <circle cx="140" cy="30" r="4" fill="var(--acc)"/>
            <circle cx="260" cy="30" r="4" fill="var(--acc)"/>
            <circle cx="500" cy="30" r="4" fill="var(--acc)"/>
            <text x="440" y="45" font-family="var(--sans)" font-size="12" font-weight="bold" fill="var(--ok)">Illustration with review</text>
          </svg>
        </div>
      </div>
    `;
  }

  // ---------------------------------------------------------------------------
  // Deep Epistemic Readings & Reading Comprehension Suite
  // ---------------------------------------------------------------------------
  let currentReadingIx = 0;
  const READING_SCORES_KEY = 'symblic_reading_scores_v1';
  let READING_SCORES = {};
  try {
    READING_SCORES = JSON.parse(localStorage.getItem(READING_SCORES_KEY) || '{}');
  } catch (_) { READING_SCORES = {}; }

  function saveReadingScores() {
    try { localStorage.setItem(READING_SCORES_KEY, JSON.stringify(READING_SCORES)); } catch (_) {}
  }

  // Reading IDs are new: old reading scores and all mastery/flashcard IDs stay intact.
  const PHILOSOPHY_READINGS = MASTERY_LEVELS.slice(7).map((level, index) => ({
    id: 'depth-v2-' + index, num: index + 1, title: level.title.split(': ').slice(1).join(': '),
    subtitle: level.desc, readTime: 'Read, work the examples, then test the distinctions',
    tags: ['Research context', 'Worked reasoning', 'Scope and evidence'],
    paras: level.bites.flatMap(b => [b.title + '. ' + b.concept, ...(b.worked?.steps || []), ...(b.worked ? [b.worked.takeaway] : [])]),
    quote: 'Study principle: distinguish a model’s assumptions, its calculation and evidence about the world.',
    formula: 'Claim + assumptions + discriminating evidence → bounded conclusion',
    questions: level.bites.map(b => ({q: b.question, opts: b.options, ans: b.ans, cit: b.worked?.takeaway || '', expl: b.explanation})),
    references: level.bites.flatMap(b => b.references || [])
  }));

  function renderResearchMap(m) {
    m.innerHTML = `<div class="sl-mastery-container"><h1>Research → understanding</h1>
      <p>Explore all ${CONTENT.sources.length} indexed documents, examples and evidence records of this repository, most of them under <code>docs/</code>, <code>examples/</code>, <code>benchmarks/</code> and <code>kits/</code>. The lesson links identify a teaching connection; they do not certify every claim in the original.</p>
      ${HOST_API ? '' : '<p>The reader loads each document as a static file from the repository: serve the repository root (for example with <code>python3 -m http.server</code>) and open this page under <code>/web/academy/</code>.</p>'}
      <label for="slResearchSearch">Find a topic, document or section</label>
      <input id="slResearchSearch" class="sl-research-search" type="search" placeholder="Empathy, quantum, ambiguity, mathematics…">
      <p id="slResearchCount" role="status"></p><div id="slResearchList" class="sl-research-list"></div></div>`;
    const selected = CONTENT.sources.find(s => s.url === new URL(location.href).searchParams.get('reading'));
    if (selected) $('slResearchSearch').value = selected.title;
    const render = () => {
      const q = $('slResearchSearch').value.toLocaleLowerCase().trim();
      const rows = CONTENT.sources.filter(s => [s.title, ...s.headings, ...s.lessons.map(l => l.title)].join(' ').toLocaleLowerCase().includes(q));
      $('slResearchCount').textContent = `${rows.length} of ${CONTENT.sources.length} sources · Curriculum updated ${CONTENT.updated}`;
      const list = $('slResearchList');
      list.replaceChildren();
      rows.forEach(s => {
        const section = document.createElement('section'); section.className = 'sl-research-record';
        const title = document.createElement('h2'), anchor = document.createElement('a');
        anchor.textContent = s.title; anchor.href = readingURL(s.url); anchor.target = '_blank'; anchor.rel = 'noopener noreferrer'; title.append(anchor);
        const status = document.createElement('p'); status.textContent = s.status;
        section.append(title, status);
        s.lessons.forEach(l => {
          const btn = document.createElement('button'); btn.className = 'sl-btn-nav'; btn.textContent = `Learn: ${l.title}`;
          btn.onclick = () => { MASTERY_STATE.lvl = l.level; MASTERY_STATE.bite = l.bite; saveMastery(); location.hash = 'mastery'; };
          section.append(btn);
        });
        if (isRepoPath(s.url) && !s.url.endsWith('.pdf')) {
          const details = document.createElement('details'), summary = document.createElement('summary'), text = document.createElement('pre');
          text.tabIndex = 0;
          text.setAttribute('role', 'region');
          text.setAttribute('aria-label', `Original source: ${s.title}`);
          text.addEventListener('keydown', e => {
            if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') e.stopPropagation();
          });
          summary.textContent = 'Read the original here'; details.append(summary, text);
          let loaded = false, busy = false;
          details.ontoggle = async () => {
            if (!details.open || loaded || busy) return;
            busy = true; text.textContent = 'Loading original source…';
            try {
              const response = await fetch(repoHref(s.url), {cache: 'no-store'})
                .catch(() => { throw new Error('Source unavailable (no response).'); });
              if (!response.ok) throw new Error(`Source unavailable (${response.status}).`);
              const bytes = await response.arrayBuffer();
              text.textContent = new TextDecoder('utf-8').decode(bytes); loaded = true;
              // The catalog's sha256 hashes the file's bytes when the index was built.
              const digest = s.sha256 ? await sha256Hex(bytes) : null;
              if (digest && digest !== s.sha256) status.textContent += ' This source has changed since the lesson index was built; review the current text below.';
            } catch (err) { text.textContent = err.message + ' Close and reopen to retry.'; }
            finally { busy = false; }
          };
          section.append(details);
          if (selected?.url === s.url) details.open = true;
        }
        list.append(section);
      });
    };
    $('slResearchSearch').oninput = render; render();
  }

  function renderPhilosophyReadings(m) {
    const r = PHILOSOPHY_READINGS[currentReadingIx] || PHILOSOPHY_READINGS[0];
    const userScores = READING_SCORES[r.id] || {};
    const totalQ = r.questions.length;
    let correctCount = 0;
    r.questions.forEach((q, i) => {
      if (userScores[i] === q.ans) correctCount++;
    });

    m.innerHTML = `
      <div style="max-width:920px;margin:0 auto;padding-bottom:50px;">
        <div style="margin-bottom:24px;">
          <h2 style="font-size:22px;font-weight:700;margin:0 0 6px 0;">Epistemic Philosophy & Reading Comprehension</h2>
          <p style="font-size:14px;color:var(--tx2);margin:0;line-height:1.5;">
            Expanded readings connect the repository research to worked examples. Each separates established results, implemented capabilities and proposals; checkpoints record practice rather than certifying mastery.
          </p>
        </div>

        <!-- Navigation Tabs for the 5 Readings -->
        <div class="sl-reading-nav" id="slReadingNav">
          ${PHILOSOPHY_READINGS.map((item, idx) => {
            const sc = READING_SCORES[item.id] || {};
            const done = Object.keys(sc).length === item.questions.length;
            return `
              <button class="sl-reading-tab-btn ${idx === currentReadingIx ? 'active' : ''}" data-rix="${idx}">
                <span>${esc(item.num)}: ${esc(item.title.split(':')[0])}</span>
                ${done ? ' <span style="font-size:10px;opacity:0.85;">✓</span>' : ''}
              </button>
            `;
          }).join('')}
        </div>

        <!-- Active Reading Article Card -->
        <div class="sl-reading-card">
          <div class="sl-reading-meta">
            <span>${esc(r.num)} · ${esc(r.readTime)}</span>
          </div>

          <div class="sl-reading-title">${esc(r.title)}</div>
          <div class="sl-reading-subtitle">${esc(r.subtitle)}</div>

          <div class="sl-reading-body">
            ${r.paras.map(p => `<p>${esc(p)}</p>`).join('')}
          </div>

          <div class="sl-reading-quote">
            ${esc(r.quote)}
          </div>

          <div class="sl-reading-formula">
            <b>Mathematical / Invariant Formalism:</b><br>
            <code>${esc(r.formula)}</code>
          </div>

          <div class="sl-reading-tags">
            ${r.tags.map(t => `<span class="sl-reading-tag">${esc(t)}</span>`).join('')}
          </div>
          <div class="sl-lesson-sources"><h3>Original sources</h3>${[...new Map(r.references.map(ref => [ref.url, ref])).values()].map(ref => `<a href="${att(readingURL(ref.url))}" target="_blank" rel="noopener noreferrer">${esc(ref.title)}</a>`).join('')}</div>

          <!-- Reading Comprehension Test Section -->
          <div class="sl-comprehension-suite">
            <div class="sl-rc-header">
              <div>
                <h3 style="margin:0 0 4px 0;font-size:17px;font-weight:700;">Reading Comprehension Test</h3>
                <span style="font-size:12.5px;color:var(--tx2);">Answer the questions using the reasoning above, then test yourself on a new case.</span>
              </div>
              <div class="sl-rc-score-badge" id="slRcScoreBadge">
                Score: ${correctCount}/${totalQ} (${totalQ ? Math.round((correctCount / totalQ) * 100) : 0}%)
              </div>
            </div>

            <div class="sl-rc-list">
              ${r.questions.map((qItem, qIdx) => {
                const answered = userScores[qIdx] !== undefined;
                const chosen = userScores[qIdx];
                return `
                  <div class="sl-rc-item" data-qidx="${qIdx}">
                    <div class="sl-rc-q-num">Question ${qIdx + 1} of ${totalQ}</div>
                    <div class="sl-rc-question">${esc(qItem.q)}</div>
                    <div class="sl-rc-opts">
                      ${qItem.opts.map((opt, oIdx) => {
                        let cls = 'sl-rc-opt';
                        if (answered) {
                          cls += ' locked';
                          if (oIdx === qItem.ans) cls += ' correct';
                          else if (oIdx === chosen) cls += ' incorrect';
                        }
                        return `
                          <button class="${cls}" data-oidx="${oIdx}">
                            <span style="font-family:var(--mono);font-size:11px;font-weight:700;opacity:0.65;">
                              ${String.fromCharCode(65 + oIdx)}
                            </span>
                            <span>${esc(opt)}</span>
                          </button>
                        `;
                      }).join('')}
                    </div>
                    <div class="sl-rc-citation" style="display:${answered ? 'block' : 'none'};">
                      <b>Reasoning and scope:</b>
                      <div style="font-style:italic;margin-bottom:6px;color:var(--tx1);">${esc(qItem.cit)}</div>
                      <div style="color:var(--tx2);font-size:12.5px;">${esc(qItem.expl)}</div>
                    </div>
                  </div>
                `;
              }).join('')}
            </div>
          </div>

        </div>
      </div>
    `;

    // Wire reading tab switcher
    m.querySelectorAll('.sl-reading-tab-btn').forEach(btn => {
      btn.onclick = () => {
        currentReadingIx = parseInt(btn.dataset.rix, 10);
        renderPhilosophyReadings(m);
      };
    });

    // Wire question answering
    m.querySelectorAll('.sl-rc-item').forEach(itemEl => {
      const qIdx = parseInt(itemEl.dataset.qidx, 10);
      const qItem = r.questions[qIdx];
      const optBtns = itemEl.querySelectorAll('.sl-rc-opt');
      const citationEl = itemEl.querySelector('.sl-rc-citation');

      optBtns.forEach(btn => {
        btn.onclick = () => {
          if (READING_SCORES[r.id] && READING_SCORES[r.id][qIdx] !== undefined) return;
          const chosen = parseInt(btn.dataset.oidx, 10);
          if (!READING_SCORES[r.id]) READING_SCORES[r.id] = {};
          READING_SCORES[r.id][qIdx] = chosen;
          saveReadingScores();

          optBtns.forEach((b, i) => {
            b.classList.add('locked');
            if (i === qItem.ans) b.classList.add('correct');
            else if (i === chosen) b.classList.add('incorrect');
          });

          if (citationEl) citationEl.style.display = 'block';

          // Update score badge
          let c = 0;
          r.questions.forEach((q, i) => {
            if (READING_SCORES[r.id][i] === q.ans) c++;
          });
          const badge = $('slRcScoreBadge');
          if (badge) {
            badge.textContent = `Score: ${c}/${totalQ} (${Math.round((c / totalQ) * 100)}%)`;
          }

          if (chosen === qItem.ans) {
            toast('Correct! Review the textual citation below.');
            if (navigator.vibrate) navigator.vibrate(20);
          } else {
            toast('Incorrect. Note the citation from the text.');
            if (navigator.vibrate) navigator.vibrate(50);
          }
        };
      });
    });
  }

  // ---------------------------------------------------------------------------
  // Global Keyboard Shortcuts
  // ---------------------------------------------------------------------------
  window.addEventListener('keydown', (e) => {
    if (Studio.page === 'flashcards') {
      if (e.code === 'Space') {
        const activeTag = (document.activeElement && document.activeElement.tagName) || '';
        if (activeTag === 'INPUT' || activeTag === 'TEXTAREA') return;
        e.preventDefault();
        const scene = $('slFcScene');
        if (scene) scene.click();
      } else if (['1', '2', '3', '4'].includes(e.key)) {
        const activeTag = (document.activeElement && document.activeElement.tagName) || '';
        if (activeTag === 'INPUT' || activeTag === 'TEXTAREA') return;
        const btn = document.querySelector(`.sl-rate-btn[data-rate="${e.key}"]`);
        if (btn) btn.click();
      }
    } else if (Studio.page === 'mastery') {
      const activeTag = (document.activeElement && document.activeElement.tagName) || '';
      if (activeTag === 'INPUT' || activeTag === 'TEXTAREA') return;
      if (['1', '2', '3', '4'].includes(e.key)) {
        const idx = parseInt(e.key, 10) - 1;
        const btn = document.querySelector(`.sl-checkpoint-opt[data-opt="${idx}"]`);
        if (btn && !btn.classList.contains('locked')) btn.click();
      } else if (e.code === 'Space' || e.key === 'Enter') {
        const nextBtn = $('slBtnNext');
        if (nextBtn && !nextBtn.hasAttribute('disabled')) {
          e.preventDefault();
          nextBtn.click();
        }
      }
    } else if (Studio.page === 'speed' && speedState.running) {
      if (e.key === 'j' || e.key === 'J') {
        const btn = $('btn_ans_true');
        if (btn) btn.click();
      } else if (e.key === 'k' || e.key === 'K') {
        const btn = $('btn_ans_false');
        if (btn) btn.click();
      }
    }
  });

  // ---------------------------------------------------------------------------
  // Studio.boot: Academy Top-Level Shell with All Advanced Tools
  // ---------------------------------------------------------------------------
  Studio.boot({
    title: 'Symblic Academy',
    wide: true,
    pages: [
      { id: 'mastery', ix: '01', name: 'Zero to Mastery', sub: 'concentrated micro-units & immediate checkpoints', grp: 'Course', render: renderMasteryPathway },
      { id: 'overview', ix: '02', name: 'Architecture Map', sub: 'construction, checking & evidence', grp: 'Theory', render: renderOverview },
      { id: 'foundations', ix: '03', name: 'Foundations', sub: 'kernel vs model in & out', grp: 'Theory', render: renderFoundations },
      { id: 'readings', ix: '04', name: 'Deep Readings', sub: `${PHILOSOPHY_READINGS.length} research chapters & understanding checks`, grp: 'Theory', render: renderPhilosophyReadings },
      { id: 'research', ix: '18', name: 'Research Map', sub: 'original sources → linked lessons', grp: 'Theory', render: renderResearchMap },
      { id: 'language', ix: '05', name: 'Reference', sub: 'statements, types & builtins', grp: 'Syntax', render: renderLanguage },
      { id: 'flashcards', ix: '06', name: 'Flashcards', sub: 'SM-2 spaced repetition deck', grp: 'Practice', render: renderFlashcards },
      { id: 'cloze', ix: '07', name: 'Cloze Blanks', sub: 'fill-in cognitive chunking', grp: 'Practice', render: renderCloze },
      { id: 'drills', ix: '08', name: 'Syntax Drills', sub: 'single-line rapid tests', grp: 'Practice', render: renderDrills },
      { id: 'parsons', ix: '09', name: 'Parsons Puzzles', sub: 'code reordering challenges', grp: 'Practice', render: renderParsons },
      { id: 'bughunt', ix: '10', name: 'Bug Hunt', sub: 'spot-the-bug diagnostics', grp: 'Practice', render: renderBugHunt },
      { id: 'stepper', ix: '11', name: 'State Stepper', sub: 'rollback execution visualizer', grp: 'Tools', render: renderStepper },
      { id: 'speed', ix: '12', name: 'Speed Drill', sub: '60s automaticity challenge', grp: 'Tools', render: renderSpeed },
      { id: 'feynman', ix: '13', name: 'Feynman Coach', sub: 'self-explanation rubric', grp: 'Tools', render: renderFeynman },
      { id: 'quizzes', ix: '14', name: 'Concept Quizzes', sub: 'elaborative interrogation', grp: 'Practice', render: renderQuizzes },
      { id: 'projects', ix: '15', name: 'Projects', sub: `${PROJECTS.length} guided capstone labs`, grp: 'Build', render: renderProjects },
      { id: 'playground', ix: '16', name: 'Playground', sub: 'live code & capsule inspector', grp: 'Build', render: renderPlayground },
      { id: 'retention', ix: '17', name: 'Metacognition', sub: 'review groups & illustrative recall curves', grp: 'Analytics', render: renderMetacognition }
    ],
    menuSub(id) {
      if (id === 'mastery') {
        const done = Object.keys(MASTERY_STATE.completed || {}).length;
        let total = 0;
        MASTERY_LEVELS.forEach(l => { total += l.bites.length; });
        return `${done}/${total} checkpoints complete`;
      }
      if (id === 'readings') return PHILOSOPHY_READINGS.length + ' research readings';
      if (id === 'flashcards') {
        const m = FLASHCARDS.filter(c => getCardState(c.id).reps >= 3).length;
        return `${m}/${FLASHCARDS.length} reviewed ≥ 3 times`;
      }
      if (id === 'parsons') return `${PARSONS_PUZZLES.length} puzzles`;
      if (id === 'bughunt') return `${BUG_HUNTS.length} challenges`;
      if (id === 'projects') return `${PROJECTS.length} guided labs`;
      return null;
    },
    menuNow(el) {
      el.innerHTML = '<span class="lbl">Symblic</span><a class="hint" href="../studio/symblic.html">← Symblic studio page (needs a host)</a>';
    },
    // The host also linked its terminal and Forge pages here; they are not part of this repository.
    footLinks: '<a class="btn sm ghost" href="../hub/index.html">Symblic</a><a class="btn sm ghost" href="../studio/symblic-guides/index.html">Guides</a>',
    compactNav: true
  });

})();
