/* AFIS Examination Workspace */

function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function openWorkspace() {
  const btn = document.getElementById('examineBtn');
  const scanNum = btn ? btn.dataset.scan : '';
  document.getElementById('afisWorkspace').style.display = 'flex';
  document.querySelector('.detail-header').style.display = 'none';
  document.getElementById('detailLayout').style.display = 'none';
  loadCandidates(scanNum);
}

function closeWorkspace() {
  document.getElementById('afisWorkspace').style.display = 'none';
  document.querySelector('.detail-header').style.display = '';
  document.getElementById('detailLayout').style.display = '';
}

async function loadCandidates(scanNum) {
  document.getElementById('afisCandidateList').innerHTML =
    '<div class="afis-loading"><div class="afis-spinner"></div>ANALYZING…</div>';
  document.getElementById('afisFeaturesList').innerHTML =
    '<div class="afis-feature"><span class="afis-fk">STATUS:</span>'
    + ' <span class="afis-fv" style="color:#4a5568">RUNNING OCR…</span></div>';

  try {
    const resp = await fetch('/card/' + scanNum + '/find-matches', { method: 'POST' });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ error: 'Server error' }));
      throw new Error(err.error || 'Request failed');
    }
    renderWorkspace(await resp.json(), scanNum);
  } catch (e) {
    document.getElementById('afisCandidateList').innerHTML =
      '<div class="afis-error">ANALYSIS FAILED: ' + escHtml(e.message) + '</div>';
    document.getElementById('afisFeaturesList').innerHTML =
      '<div class="afis-feature"><span class="afis-fk">STATUS:</span>'
      + ' <span class="afis-fv" style="color:#fc8181">ERROR</span></div>';
  }
}

function featureRow(key, val) {
  return '<div class="afis-feature"><span class="afis-fk">' + key
    + ':</span> <span class="afis-fv">' + val + '</span></div>';
}

function rhSectionHTML(rh, scanNum) {
  if (!rh) return '';
  const isRH = rh.is_reverse_holo;
  const conf = (rh.confidence || 'low').toUpperCase();
  const valHtml = isRH
    ? '<span style="color:#d69e2e">&#x2726; YES</span>&nbsp;<span style="color:#d69e2e">(' + conf + ' confidence)</span>'
    : '<span style="color:#718096">&#x2717; NO</span>&nbsp;<span style="color:#718096">(' + conf + ' confidence)</span>';
  return '<div class="afis-rh-section">'
    + '<div class="afis-feature"><span class="afis-fk">REVERSE HOLO:</span> <span class="afis-fv">' + valHtml + '</span></div>'
    + (rh.reasoning ? '<div class="afis-rh-reasoning">' + escHtml(rh.reasoning) + '</div>' : '')
    + '<div class="afis-rh-btns">'
    + '<button class="btn-rh-confirm" data-scan="' + escHtml(scanNum) + '" data-is-rh="1">&#x2726; CONFIRM REVERSE HOLO</button>'
    + '<button class="btn-rh-normal" data-scan="' + escHtml(scanNum) + '" data-is-rh="0">&#x2717; CONFIRM NORMAL</button>'
    + '</div>'
    + '</div>';
}

function renderWorkspace(data, scanNum) {
  const ocr = data.ocr || {};
  const confLvl = (ocr.confidence || 'low').toLowerCase();

  document.getElementById('afisFeaturesList').innerHTML = [
    featureRow('CARD NAME', escHtml(ocr.card_name || '—')),
    featureRow('CARD NUMBER', escHtml(ocr.card_number || '—')),
    featureRow('SET CODE', escHtml(ocr.set_code || '—')),
    '<div class="afis-feature"><span class="afis-fk">CONFIDENCE:</span> '
      + '<span class="afis-conf-badge conf-' + confLvl + '">'
      + confLvl.toUpperCase() + '</span></div>',
    rhSectionHTML(data.reverse_holo, scanNum),
  ].join('');

  const candidates = data.candidates || [];
  document.getElementById('afisCandidateLabel').textContent =
    candidates.length + ' CANDIDATE HITS — Ranked by Confidence';

  const list = document.getElementById('afisCandidateList');
  if (!candidates.length) {
    list.innerHTML = '<div class="afis-no-hits">NO CANDIDATES FOUND</div>';
    return;
  }

  list.innerHTML = candidates.map((c, i) => hitCardHTML(c, i + 1, scanNum)).join('');

  // Double rAF so the browser has painted width:0 before we animate to the target
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      document.querySelectorAll('.afis-bar-fill').forEach(el => {
        el.style.width = el.dataset.target;
      });
    });
  });
}

function hitCardHTML(c, rank, scanNum) {
  const MAX = 8;
  const pct = Math.round((c.score / MAX) * 100);
  const barCls = c.score >= 5 ? 'bar-green' : c.score >= 3 ? 'bar-yellow' : 'bar-red';

  const tags = (c.match_reasons || []).length
    ? c.match_reasons.map(r => '<span class="afis-match-tag">' + escHtml(r) + '</span>').join('')
    : '<span class="afis-match-tag tag-none">NO MATCHES</span>';

  const price = c.market_price != null ? '$' + Number(c.market_price).toFixed(2) : 'N/A';

  const img = c.tcg_image_url
    ? '<img src="' + escHtml(c.tcg_image_url) + '" class="afis-tcg-img" loading="lazy" />'
    : '<div class="afis-no-tcg-img">NO IMAGE</div>';

  const examineLink = c.tcg_image_url
    ? '<a href="' + escHtml(c.tcg_image_url) + '" target="_blank" rel="noopener"'
      + ' class="afis-examine-link">EXAMINE ↗</a>'
    : '';

  const setLine = [escHtml(c.set_name || ''), c.card_number ? '&#x2022; #' + escHtml(c.card_number) : '']
    .filter(Boolean).join(' ');

  // Confirm button uses data attributes — no inline JS, no quote escaping hazard
  const confirmBtn = '<button class="btn-confirm"'
    + ' data-scan="' + escHtml(scanNum) + '"'
    + ' data-tcg-id="' + escHtml(c.tcg_card_id || '') + '">'
    + 'CONFIRM IDENTIFICATION</button>';

  return '<div class="afis-hit-card">'
    + '<div class="afis-hit-header">'
    +   '<span class="afis-hit-rank">HIT #' + rank + '</span>'
    +   '<div class="afis-score-bar">'
    +     '<div class="afis-bar-fill ' + barCls + '" data-target="' + pct + '%" style="width:0%"></div>'
    +   '</div>'
    +   '<span class="afis-score-num">' + c.score + '/' + MAX + '</span>'
    + '</div>'
    + '<div class="afis-match-tags">' + tags + '</div>'
    + '<div class="afis-hit-body">'
    +   '<div class="afis-tcg-wrap">' + img + examineLink + '</div>'
    +   '<div class="afis-hit-meta">'
    +     '<div class="afis-hit-name">' + escHtml(c.card_name || '—') + '</div>'
    +     '<div class="afis-hit-set">' + (setLine || '—') + '</div>'
    +     (c.release_date ? '<div class="afis-hit-date">Released: ' + escHtml(c.release_date) + '</div>' : '')
    +     '<div class="afis-hit-price">' + escHtml(price) + '</div>'
    +     '<div class="afis-hit-id"><code>' + escHtml(c.tcg_card_id || '') + '</code></div>'
    +     confirmBtn
    +   '</div>'
    + '</div>'
    + '</div>';
}

async function setReverseHolo(scanNum, isRH, btn) {
  btn.disabled = true;
  const origText = btn.textContent;
  btn.textContent = 'SAVING…';
  try {
    const resp = await fetch('/card/' + scanNum + '/set-reverse-holo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_reverse_holo: isRH }),
    });
    if (!resp.ok) throw new Error('Server error');
    btn.textContent = '✓ SAVED';
    const wrap = btn.closest('.afis-rh-btns');
    if (wrap) wrap.querySelectorAll('button').forEach(b => { b.disabled = true; });
  } catch (e) {
    btn.disabled = false;
    btn.textContent = origText;
  }
}

async function confirmMatch(scanNum, tcgCardId, btn) {
  btn.disabled = true;
  btn.textContent = 'CONFIRMING…';
  try {
    const resp = await fetch('/card/' + scanNum + '/confirm-match', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tcg_card_id: tcgCardId }),
    });
    if (!resp.ok) throw new Error('Server error');
    btn.textContent = '✓ IDENTIFICATION CONFIRMED';
    btn.classList.add('btn-confirm-success');
    setTimeout(() => location.reload(), 1400);
  } catch (e) {
    btn.disabled = false;
    btn.textContent = 'ERROR — RETRY';
    setTimeout(() => { btn.textContent = 'CONFIRM IDENTIFICATION'; }, 2000);
  }
}

document.addEventListener('DOMContentLoaded', function () {
  const examineBtn = document.getElementById('examineBtn');
  if (examineBtn) examineBtn.addEventListener('click', openWorkspace);

  const closeBtn = document.getElementById('afisCloseBtn');
  if (closeBtn) closeBtn.addEventListener('click', closeWorkspace);

  // Event delegation for confirm buttons — they're created dynamically
  const candidateList = document.getElementById('afisCandidateList');
  if (candidateList) {
    candidateList.addEventListener('click', function (e) {
      const btn = e.target.closest('.btn-confirm');
      if (btn && !btn.disabled) {
        confirmMatch(btn.dataset.scan, btn.dataset.tcgId, btn);
      }
    });
  }

  // Event delegation for reverse holo confirm buttons
  const featuresList = document.getElementById('afisFeaturesList');
  if (featuresList) {
    featuresList.addEventListener('click', function (e) {
      const btn = e.target.closest('.btn-rh-confirm, .btn-rh-normal');
      if (btn && !btn.disabled) {
        setReverseHolo(btn.dataset.scan, btn.dataset.isRh === '1', btn);
      }
    });
  }
});
