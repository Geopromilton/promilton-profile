// Component renderers for Dr. Promilton's site. Vanilla JS.
(function(){
  const D = window.SITE_DATA;
  const el = (tag, attrs = {}, kids = []) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === 'class') n.className = v;
      else if (k === 'style') n.style.cssText = v;
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
      else if (k === 'html') n.innerHTML = v;
      else n.setAttribute(k, v);
    }
    for (const k of [].concat(kids)) {
      if (k == null) continue;
      n.append(typeof k === 'string' ? document.createTextNode(k) : k);
    }
    return n;
  };

  // ---------- FOOTER ----------
  function renderFooter() {
    const wrap = document.getElementById('footer-grid'); if (!wrap) return;
    wrap.innerHTML = `
      <div>
        <span class="eyebrow">Field Notebook</span>
        <p style="margin:0 0 10px; max-width:420px;">A living record of research, fieldwork and consulting across the hydrogeology, geophysics and geospatial sciences of southern India.</p>
      </div>
      <div>
        <span class="eyebrow">Site</span>
        <ul>
          <li><a href="index.html">Home</a></li>
          <li><a href="research.html">Research</a></li>
          <li><a href="publications.html">Publications</a></li>
          <li><a href="contact.html">Contact</a></li>
        </ul>
      </div>
      <div>
        <span class="eyebrow">Identifiers</span>
        <ul>
          <li>ORCID ${D.contact.orcid}</li>
          <li>Scholar ${D.contact.scholar}</li>
          <li>IAH 145289</li>
        </ul>
      </div>
      <div>
        <span class="eyebrow">Direct</span>
        <ul>
          <li><a href="mailto:${D.contact.email}">${D.contact.email}</a></li>
          <li>${D.contact.phones[0]}</li>
          <li>Thoothukudi · Tamil Nadu</li>
        </ul>
      </div>
    `;
  }

  // ---------- HOME: STATS ----------
  function renderHomeStats() {
    const g = document.getElementById('stats-grid'); if (!g) return;
    g.innerHTML = D.stats.map((s, i) => `
      <div style="padding:32px 20px; ${i<D.stats.length-1 ? 'border-right:1px solid var(--rule);' : ''} text-align:center;">
        <div class="display" style="font-size:clamp(44px,5vw,72px); color:var(--ink); line-height:1;">${s.n}</div>
        <div class="mono" style="margin-top:12px; color:var(--ink-soft); letter-spacing:0.16em; text-transform:uppercase; font-size:10px;">${s.label}</div>
      </div>
    `).join('');
  }

  // ---------- HOME: BIO ----------
  function renderBio() {
    const g = document.getElementById('bio'); if (!g) return;
    g.innerHTML = D.bio.map((p, i) => `
      <div>
        <div class="mono" style="color:var(--ochre-deep); font-size:10px; letter-spacing:0.2em; text-transform:uppercase; margin-bottom:12px;">¶ ${String(i+1).padStart(2,'0')}</div>
        <p style="margin:0; text-wrap:pretty;">${p}</p>
      </div>
    `).join('');
  }

  // ---------- HOME: MAP ----------
  function renderMap() {
    const wrap = document.getElementById('map-wrap'); if (!wrap) return;
    // A schematic outline of South India + Gujarat tip. We'll render an SVG
    // with an abstract topographic grid, the coastline silhouette, and
    // pins positioned from data.
    const svg = `
    <svg viewBox="0 0 1000 620" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" style="display:block;">
      <defs>
        <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
          <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(15,43,60,0.06)" stroke-width="1"/>
        </pattern>
        <pattern id="grid2" width="200" height="200" patternUnits="userSpaceOnUse">
          <path d="M 200 0 L 0 0 0 200" fill="none" stroke="rgba(15,43,60,0.1)" stroke-width="1"/>
        </pattern>
        <filter id="rough"><feTurbulence baseFrequency="0.9" numOctaves="2" seed="3"/><feDisplacementMap in="SourceGraphic" scale="1.2"/></filter>
      </defs>
      <rect width="1000" height="620" fill="url(#grid)"/>
      <rect width="1000" height="620" fill="url(#grid2)"/>

      <!-- Topographic contours (concentric) -->
      <g fill="none" stroke="rgba(196,122,43,0.18)" stroke-width="0.9">
        <ellipse cx="320" cy="400" rx="260" ry="190"/>
        <ellipse cx="320" cy="400" rx="220" ry="160"/>
        <ellipse cx="320" cy="400" rx="180" ry="130"/>
        <ellipse cx="320" cy="400" rx="140" ry="100"/>
        <ellipse cx="320" cy="400" rx="100" ry="72"/>
        <ellipse cx="320" cy="400" rx="60" ry="42"/>
      </g>

      <!-- South India silhouette (schematic) -->
      <path d="M 180 120 Q 240 140 280 170 Q 340 180 380 220 Q 430 250 470 290 Q 500 340 490 400 Q 470 460 430 510 Q 380 560 340 580 Q 300 590 280 560 Q 240 530 220 480 Q 200 430 210 380 Q 220 320 200 260 Q 180 190 180 120 Z"
        fill="rgba(15,43,60,0.08)" stroke="rgba(15,43,60,0.45)" stroke-width="1.5"/>
      <!-- Gujarat tip (top-left) -->
      <path d="M 20 100 Q 50 80 90 110 Q 110 140 80 160 Q 50 170 30 150 Q 10 130 20 100 Z"
        fill="rgba(15,43,60,0.08)" stroke="rgba(15,43,60,0.45)" stroke-width="1.5"/>

      <!-- Compass -->
      <g transform="translate(920, 90)" fill="var(--ink)">
        <circle r="28" fill="none" stroke="var(--ink)" stroke-width="1"/>
        <path d="M 0 -24 L 6 0 L 0 24 L -6 0 Z" fill="var(--ink)"/>
        <path d="M 0 -24 L 6 0 L 0 0 Z" fill="var(--ochre)"/>
        <text y="-36" text-anchor="middle" font-family="IBM Plex Mono" font-size="10" letter-spacing="0.18em">N</text>
      </g>

      <!-- Scale bar -->
      <g transform="translate(60, 560)" font-family="IBM Plex Mono" font-size="10" fill="var(--ink-soft)">
        <line x1="0" y1="0" x2="120" y2="0" stroke="var(--ink)" stroke-width="1"/>
        <line x1="0" y1="-4" x2="0" y2="4" stroke="var(--ink)"/>
        <line x1="60" y1="-4" x2="60" y2="4" stroke="var(--ink)"/>
        <line x1="120" y1="-4" x2="120" y2="4" stroke="var(--ink)"/>
        <text y="18" letter-spacing="0.1em">0</text>
        <text x="60" y="18" text-anchor="middle" letter-spacing="0.1em">~100 km</text>
        <text x="120" y="18" text-anchor="middle" letter-spacing="0.1em">200</text>
      </g>

      <!-- Title -->
      <text x="60" y="50" font-family="Instrument Serif" font-style="italic" font-size="28" fill="var(--ink)">Atlas of Field Sites</text>
      <text x="60" y="70" font-family="IBM Plex Mono" font-size="10" letter-spacing="0.18em" fill="var(--ochre-deep)">SCHEMATIC · NOT TO SCALE</text>

      <g id="pins"></g>
    </svg>`;
    wrap.innerHTML = svg;
    const pinsG = wrap.querySelector('#pins');
    const readout = document.getElementById('map-readout');
    D.fieldSites.forEach((s, i) => {
      const cx = s.x * 1000, cy = s.y * 620;
      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.style.cursor = 'pointer';
      g.innerHTML = `
        <circle cx="${cx}" cy="${cy}" r="14" fill="rgba(196,122,43,0.12)"/>
        <circle cx="${cx}" cy="${cy}" r="5" fill="var(--ochre)" stroke="var(--ink)" stroke-width="1"/>
        <text x="${cx + 10}" y="${cy + 4}" font-family="IBM Plex Mono" font-size="10" letter-spacing="0.08em" fill="var(--ink)">${s.name}</text>
      `;
      g.addEventListener('mouseenter', () => readout && (readout.textContent = `${s.name.toUpperCase()} · ${s.role}`));
      g.addEventListener('mouseleave', () => readout && (readout.textContent = '—'));
      pinsG.appendChild(g);
    });
  }

  // ---------- HOME: TIMELINE ----------
  function renderTimeline() {
    const wrap = document.getElementById('timeline-wrap'); if (!wrap) return;
    const kindColor = { edu: 'var(--ink)', work: 'var(--ochre)', pub: 'var(--moss)', award: 'var(--rust)' };
    const kindLabel = { edu: 'Education', work: 'Work', pub: 'Publication', award: 'Honor' };
    wrap.innerHTML = `
      <div style="position:relative; padding:12px 0 4px;">
        <div style="position:absolute; left:120px; top:0; bottom:0; border-left:1px dashed var(--rule);"></div>
        ${D.timeline.map(t => `
          <div style="display:grid; grid-template-columns: 100px 40px 1fr; align-items:baseline; padding:18px 0; border-bottom:1px solid var(--rule-soft);">
            <div class="mono" style="letter-spacing:0.16em; color:var(--ink);">${t.year}</div>
            <div style="display:flex; justify-content:center;"><span style="width:10px; height:10px; background:${kindColor[t.kind]}; border:1px solid var(--ink); border-radius:50%; display:inline-block;"></span></div>
            <div>
              <div style="display:flex; gap:14px; align-items:baseline; flex-wrap:wrap;">
                <span style="font-family:var(--serif); font-size:20px;">${t.title}</span>
                <span class="mono" style="color:${kindColor[t.kind]}; font-size:10px; letter-spacing:0.18em; text-transform:uppercase;">${kindLabel[t.kind]}</span>
              </div>
              <div style="color:var(--ink-soft); margin-top:2px;">${t.note}</div>
            </div>
          </div>
        `).join('')}
      </div>
    `;
  }

  // ---------- RESEARCH PAGE ----------
  function renderResearch() {
    const wrap = document.getElementById('research-root'); if (!wrap) return;

    const interests = `
      <section class="sec" id="interests">
        <div class="sec-head">
          <div class="sec-num">§ 01 — Fields of Interest</div>
          <h2 class="sec-title">Where the <span class="accent" style="color:var(--ochre-deep)">questions</span> live.</h2>
        </div>
        <div style="display:grid; grid-template-columns: repeat(3,1fr); gap:0; border-top:1px solid var(--rule); border-left:1px solid var(--rule);">
          ${D.interests.map((i, idx) => `
            <div style="padding:24px 22px; border-right:1px solid var(--rule); border-bottom:1px solid var(--rule); min-height:110px; display:flex; flex-direction:column; justify-content:space-between;">
              <div class="mono" style="font-size:10px; color:var(--ochre-deep); letter-spacing:0.2em;">${String(idx+1).padStart(2,'0')}</div>
              <div style="font-size:18px; line-height:1.3; margin-top:12px;">${i}</div>
            </div>
          `).join('')}
        </div>
      </section>
    `;

    const skills = `
      <section class="sec" id="skills">
        <div class="sec-head">
          <div class="sec-num">§ 02 — Research Expertise &amp; Technical Skills</div>
          <h2 class="sec-title">The <span class="accent" style="color:var(--ochre-deep)">toolkit</span>.</h2>
        </div>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:36px;">
          ${D.skills.map((s, idx) => `
            <div style="border-top:1px solid var(--ink); padding-top:20px;">
              <div style="display:flex; align-items:baseline; justify-content:space-between; margin-bottom:14px;">
                <h3 style="font-size:24px;">${s.group}</h3>
                <span class="mono" style="font-size:10px; color:var(--ink-soft); letter-spacing:0.18em;">${String(idx+1).padStart(2,'0')} / ${String(D.skills.length).padStart(2,'0')}</span>
              </div>
              <ul style="list-style:none; padding:0; margin:0;">
                ${s.items.map(it => `<li style="padding:8px 0; border-bottom:1px dotted var(--rule); display:flex; gap:12px;"><span style="color:var(--ochre); flex-shrink:0;">▸</span><span>${it}</span></li>`).join('')}
              </ul>
            </div>
          `).join('')}
        </div>
      </section>
    `;

    const chapters = `
      <section class="sec" id="chapters">
        <div class="sec-head">
          <div class="sec-num">§ 03 — Book Chapters &amp; Conference Proceedings</div>
          <h2 class="sec-title">Seven chapters, <span class="accent" style="color:var(--ochre-deep)">one continuing thesis</span>.</h2>
        </div>
        <ol style="list-style:none; padding:0; margin:0; border-top:1px solid var(--rule);">
          ${D.bookChapters.map((c, i) => `
            <li style="display:grid; grid-template-columns: 60px 120px 1fr; gap:24px; padding:24px 0; border-bottom:1px solid var(--rule); align-items:baseline;">
              <span class="mono" style="color:var(--ochre-deep); letter-spacing:0.16em;">${String(i+1).padStart(2,'0')}</span>
              <span class="mono" style="color:var(--ink-soft); font-size:11px;">${c.year}${c.pages ? ' · '+c.pages : ''}</span>
              <div>
                <div style="font-size:19px; line-height:1.4;">${c.title}</div>
                <div style="color:var(--ink-soft); margin-top:6px; font-size:14px;">${c.authors}</div>
              </div>
            </li>
          `).join('')}
        </ol>
      </section>
    `;

    const confs = `
      <section class="sec" id="conferences">
        <div class="sec-head">
          <div class="sec-num">§ 04 — Paper Presentations</div>
          <h2 class="sec-title">On the <span class="accent" style="color:var(--ochre-deep)">podium</span>.</h2>
        </div>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:24px;">
          ${D.conferences.map(c => `
            <div class="card">
              <span class="eyebrow">${c.kind} · ${c.date}</span>
              <p style="margin:0 0 12px; font-size:18px; line-height:1.4;">${c.title}</p>
              <div class="mono" style="color:var(--ochre-deep); font-size:11px; letter-spacing:0.14em;">${c.venue}</div>
            </div>
          `).join('')}
        </div>
      </section>
    `;

    const reviewing = `
      <section class="sec" id="reviewing">
        <div class="sec-head">
          <div class="sec-num">§ 05 — Peer Review Service</div>
          <h2 class="sec-title">Three <span class="accent" style="color:var(--ochre-deep)">journals</span>, ongoing.</h2>
        </div>
        <div style="display:grid; grid-template-columns: repeat(3,1fr); gap:20px;">
          ${D.reviewing.map((r, i) => `
            <div style="border:1px solid var(--ink); padding:28px 24px; background:var(--paper-2);">
              <div class="mono" style="color:var(--ochre); font-size:11px; letter-spacing:0.22em;">JOURNAL ${String(i+1).padStart(2,'0')}</div>
              <div style="font-size:22px; margin-top:14px; line-height:1.25; font-family:var(--serif);">${r}</div>
            </div>
          `).join('')}
        </div>
      </section>
    `;

    const awards = `
      <section class="sec" id="awards">
        <div class="sec-head">
          <div class="sec-num">§ 06 — Recognition</div>
          <h2 class="sec-title">Awards &amp; <span class="accent" style="color:var(--ochre-deep)">memberships</span>.</h2>
        </div>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:24px;">
          ${D.awards.map(a => `
            <div style="background:var(--ink); color:var(--paper); padding:32px 28px;">
              <div class="mono" style="color:var(--ochre); font-size:11px; letter-spacing:0.2em;">${a.date}</div>
              <h3 style="color:var(--paper); font-size:26px; margin-top:14px; line-height:1.2;">${a.title}</h3>
              <p style="margin:10px 0 0; color:rgba(246,241,231,0.75); font-size:15px;">${a.issuer}</p>
            </div>
          `).join('')}
        </div>
      </section>
    `;

    wrap.innerHTML = interests + skills + chapters + confs + reviewing + awards;
  }

  // ---------- PUBLICATIONS PAGE ----------
  function renderPublications() {
    const wrap = document.getElementById('pubs-root'); if (!wrap) return;

    const years = [...new Set(D.publications.map(p => p.year))].sort().reverse();
    const tagLabels = {
      hydro: 'Hydrogeology', geophys: 'Geophysics', geochem: 'Geochemistry',
      gis: 'GIS/RS', coastal: 'Coastal', ml: 'Machine Learning',
      disaster: 'Disaster', sediment: 'Sediment', energy: 'Energy'
    };
    const allTags = [...new Set(D.publications.flatMap(p => p.tags || []))];

    wrap.innerHTML = `
      <div style="display:flex; gap:12px; flex-wrap:wrap; margin:20px 0 40px; align-items:center;">
        <span class="mono" style="color:var(--ink-soft); font-size:10px; letter-spacing:0.18em;">FILTER BY TOPIC ·</span>
        <button class="pub-tag active" data-tag="all">All · ${D.publications.length}</button>
        ${allTags.map(t => `<button class="pub-tag" data-tag="${t}">${tagLabels[t] || t}</button>`).join('')}
      </div>
      <div id="pub-list"></div>
    `;

    // tag button style
    const style = document.createElement('style');
    style.textContent = `
      .pub-tag { font-family: var(--mono); font-size: 10px; letter-spacing: 0.16em;
        text-transform: uppercase; padding: 8px 14px; background: transparent;
        border: 1px solid var(--rule); color: var(--ink-soft); cursor: pointer; transition: all .2s; }
      .pub-tag:hover { border-color: var(--ink); color: var(--ink); }
      .pub-tag.active { background: var(--ink); border-color: var(--ink); color: var(--paper); }
    `;
    document.head.appendChild(style);

    const list = document.getElementById('pub-list');
    const renderList = (filter) => {
      const items = filter === 'all' ? D.publications : D.publications.filter(p => (p.tags||[]).includes(filter));
      const byYear = {};
      items.forEach(p => { (byYear[p.year] = byYear[p.year] || []).push(p); });
      list.innerHTML = Object.keys(byYear).sort().reverse().map(y => `
        <div style="display:grid; grid-template-columns: 140px 1fr; gap:24px; margin-bottom:32px; border-top:1px solid var(--ink); padding-top:20px;">
          <div>
            <div class="display" style="font-size:44px; line-height:1;">${y}</div>
            <div class="mono" style="color:var(--ink-soft); font-size:10px; letter-spacing:0.18em; margin-top:6px;">${byYear[y].length} ${byYear[y].length===1?'PAPER':'PAPERS'}</div>
          </div>
          <ol style="list-style:none; padding:0; margin:0;">
            ${byYear[y].map(p => `
              <li style="display:grid; grid-template-columns: 40px 1fr auto; gap:20px; padding:20px 0; border-bottom:1px solid var(--rule-soft); align-items:baseline;">
                <span class="mono" style="color:var(--ochre-deep); letter-spacing:0.14em;">${String(p.n).padStart(2,'0')}</span>
                <div>
                  <div style="font-size:19px; line-height:1.35; color:var(--ink); text-wrap:pretty;">${p.title}${p.featured ? ' <span class="mono" style="display:inline-block; margin-left:6px; padding:2px 6px; background:var(--ochre); color:var(--paper); font-size:9px; letter-spacing:0.16em; vertical-align:middle;">FEATURED</span>' : ''}</div>
                  <div style="color:var(--ink-soft); margin-top:6px; font-size:14px;">${p.authors}</div>
                  <div class="mono" style="color:var(--ochre-deep); margin-top:6px; font-size:11px; letter-spacing:0.08em;">${p.venue}</div>
                </div>
                <div style="display:flex; flex-direction:column; gap:6px; align-items:flex-end;">
                  ${p.doi ? `<a class="btn ghost" style="padding:6px 10px; font-size:9px;" href="https://doi.org/${p.doi}" target="_blank" rel="noopener">DOI ↗</a>` : ''}
                  <div style="display:flex; gap:4px; flex-wrap:wrap; justify-content:flex-end;">
                    ${(p.tags||[]).map(t => `<span class="mono" style="font-size:9px; letter-spacing:0.1em; color:var(--ink-soft); border:1px solid var(--rule); padding:2px 6px;">${tagLabels[t]||t}</span>`).join('')}
                  </div>
                </div>
              </li>
            `).join('')}
          </ol>
        </div>
      `).join('');
    };
    renderList('all');

    wrap.querySelectorAll('.pub-tag').forEach(b => {
      b.addEventListener('click', () => {
        wrap.querySelectorAll('.pub-tag').forEach(x => x.classList.remove('active'));
        b.classList.add('active');
        renderList(b.dataset.tag);
      });
    });
  }

  // ---------- CONTACT PAGE ----------
  function renderContact() {
    const wrap = document.getElementById('contact-root'); if (!wrap) return;
    wrap.innerHTML = `
      <div style="display:grid; grid-template-columns: 1.1fr 1fr; gap:56px; margin-top:40px;">
        <div>
          <div class="eyebrow" style="margin-bottom:16px;">Write to the Field Notebook</div>
          <h2 style="margin-bottom:20px;">Collaboration, <span class="accent" style="color:var(--ochre-deep)">consulting</span>, or correspondence.</h2>
          <p style="color:var(--ink-2); line-height:1.6; max-width:520px;">
            Reach out about hydrogeological investigations, peer review invitations, joint research or field-site partnerships. Responses typically within two working days.
          </p>
          <form id="contact-form" style="display:grid; gap:16px; margin-top:32px;">
            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:16px;">
              <div class="field"><label>Name</label><input required name="name" placeholder="Your full name"/></div>
              <div class="field"><label>Affiliation</label><input name="org" placeholder="Institution / company"/></div>
            </div>
            <div class="field"><label>Email</label><input required type="email" name="email" placeholder="you@example.org"/></div>
            <div class="field"><label>Subject</label>
              <select name="subject">
                <option>Research collaboration</option>
                <option>Consulting enquiry (well-site, geophysics)</option>
                <option>Peer review invitation</option>
                <option>Speaking / conference</option>
                <option>Student supervision</option>
                <option>Other</option>
              </select>
            </div>
            <div class="field"><label>Message</label><textarea required name="message" placeholder="Tell me what you're working on…"></textarea></div>
            <div style="display:flex; gap:12px; align-items:center; flex-wrap:wrap;">
              <button type="submit" class="btn ochre">Send message <span class="arrow">→</span></button>
              <span id="contact-status" class="mono" style="color:var(--ink-soft); font-size:11px; letter-spacing:0.14em;"></span>
            </div>
          </form>
        </div>
        <aside>
          <div style="border:1px solid var(--ink); padding:32px 28px; background:var(--paper-2);">
            <div class="eyebrow">Direct contact</div>
            <div style="margin-top:18px;">
              <div class="mono" style="font-size:10px; color:var(--ink-soft); letter-spacing:0.18em;">EMAIL</div>
              <a href="mailto:${D.contact.email}" style="font-size:20px; text-decoration:none; color:var(--ink);">${D.contact.email}</a>
            </div>
            <div style="margin-top:20px;">
              <div class="mono" style="font-size:10px; color:var(--ink-soft); letter-spacing:0.18em;">PHONE</div>
              ${D.contact.phones.map(p => `<div style="font-size:18px;">${p}</div>`).join('')}
            </div>
            <div style="margin-top:20px;">
              <div class="mono" style="font-size:10px; color:var(--ink-soft); letter-spacing:0.18em;">ADDRESS</div>
              <div style="font-size:15px; line-height:1.5; max-width:320px;">${D.contact.address}</div>
            </div>
          </div>
          <div style="border:1px solid var(--rule); padding:24px; margin-top:20px;">
            <div class="eyebrow">Research identifiers</div>
            <div style="margin-top:14px; display:grid; gap:10px;">
              <a href="https://orcid.org/${D.contact.orcid}" target="_blank" rel="noopener" style="display:flex; justify-content:space-between; text-decoration:none; padding:10px 0; border-bottom:1px dotted var(--rule);"><span>ORCID</span><span class="mono" style="font-size:11px; color:var(--ochre-deep);">${D.contact.orcid} ↗</span></a>
              <a href="https://scholar.google.com/citations?user=${D.contact.scholar}" target="_blank" rel="noopener" style="display:flex; justify-content:space-between; text-decoration:none; padding:10px 0; border-bottom:1px dotted var(--rule);"><span>Google Scholar</span><span class="mono" style="font-size:11px; color:var(--ochre-deep);">${D.contact.scholar} ↗</span></a>
              <div style="display:flex; justify-content:space-between; padding:10px 0;"><span>IAH Member ID</span><span class="mono" style="font-size:11px; color:var(--ink-soft);">145289</span></div>
            </div>
          </div>
        </aside>
      </div>
    `;
    const form = document.getElementById('contact-form');
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const status = document.getElementById('contact-status');
      status.textContent = 'SENDING…';
      setTimeout(() => {
        status.innerHTML = '✓ MESSAGE QUEUED · WILL REPLY FROM ' + D.contact.email.toUpperCase();
        status.style.color = 'var(--moss)';
        form.reset();
      }, 650);
    });
  }

  window.Site = { renderFooter, renderHomeStats, renderBio, renderMap, renderTimeline, renderResearch, renderPublications, renderContact };
})();
