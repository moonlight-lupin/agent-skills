---
marp: true
theme: default
paginate: true
style: |
  @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Work+Sans:wght@300;400;500;600;700&display=swap');

  :root {
    --accent: #c4956a;
    --accent-hover: #d4a87d;
    --dark: #1a1210;
    --card: #241c17;
    --border: #3a2e25;
    --muted: #8a7a6a;
    --light: #f5e6d3;
    --cream: #e8d5bf;
    --espresso: #4a3628;
  }

  section {
    background: var(--dark);
    color: var(--light);
    font-family: 'Work Sans', sans-serif;
    font-weight: 400;
    padding: 60px 80px;
    line-height: 1.6;
  }

  h1 {
    font-family: 'Space Mono', monospace;
    font-weight: 700;
    font-size: 3.2em;
    color: var(--accent);
    letter-spacing: -0.02em;
    line-height: 1.1;
    margin-bottom: 0.2em;
  }

  h2 {
    font-family: 'Space Mono', monospace;
    font-weight: 700;
    font-size: 1.7em;
    color: var(--light);
    margin-bottom: 0.4em;
  }

  h3 {
    font-family: 'Space Mono', monospace;
    font-weight: 400;
    font-size: 0.75em;
    color: var(--accent);
    text-transform: uppercase;
    letter-spacing: 0.2em;
    margin-bottom: 0.1em;
  }

  strong { color: var(--accent); font-weight: 600; }

  section.lead {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    text-align: center;
    background: radial-gradient(ellipse at 50% 80%, #2a1e15 0%, var(--dark) 70%);
  }
  section.lead h1 { font-size: 3.6em; }
  section.lead p { color: var(--muted); font-size: 1em; }

  .method-card {
    flex: 1;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 20px 16px;
    text-align: center;
  }
  .method-card h4 {
    font-family: 'Space Mono', monospace;
    font-weight: 700;
    font-size: 0.9em;
    color: var(--light);
    margin: 10px 0 12px;
  }

  .meter-label {
    font-size: 0.6em;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 4px;
  }

  .step-circle {
    width: 52px;
    height: 52px;
    border-radius: 50%;
    background: var(--card);
    border: 2px solid var(--accent);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  .step-num {
    font-family: 'Space Mono', monospace;
    font-weight: 700;
    font-size: 1.1em;
    color: var(--accent);
    line-height: 1;
  }

  @keyframes steam {
    0%, 100% { transform: translateY(0); opacity: 0.6; }
    50% { transform: translateY(-6px); opacity: 1; }
  }

  @keyframes float {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-5px); }
  }

  .divider {
    width: 50px;
    height: 3px;
    background: var(--accent);
    border-radius: 2px;
    margin: 12px auto 16px;
  }

footer: ''
---

<!-- _class: lead -->

<svg width="140" height="140" viewBox="0 0 140 140" style="margin-bottom: 4px;">
  <!-- Coffee cup -->
  <path d="M30 55 L35 120 C35 128 105 128 105 120 L110 55" fill="none" stroke="#c4956a" stroke-width="3" stroke-linejoin="round"/>
  <!-- Cup handle -->
  <path d="M110 65 C126 65 130 90 110 95" fill="none" stroke="#c4956a" stroke-width="3"/>
  <!-- Saucer -->
  <ellipse cx="70" cy="125" rx="55" ry="8" fill="none" stroke="#c4956a" stroke-width="2.5"/>
  <!-- Coffee surface -->
  <ellipse cx="70" cy="58" rx="40" ry="6" fill="#4a3628" stroke="#c4956a" stroke-width="1.5"/>
  <!-- Steam lines -->
  <g style="animation: steam 3s ease-in-out infinite;">
    <path d="M50 42 C50 34 58 34 58 26" fill="none" stroke="#c4956a" stroke-width="2" stroke-linecap="round" opacity="0.6"/>
  </g>
  <g style="animation: steam 3s ease-in-out 0.8s infinite;">
    <path d="M70 38 C70 28 78 28 78 18" fill="none" stroke="#c4956a" stroke-width="2" stroke-linecap="round" opacity="0.5"/>
  </g>
  <g style="animation: steam 3s ease-in-out 1.6s infinite;">
    <path d="M88 42 C88 34 80 30 80 22" fill="none" stroke="#c4956a" stroke-width="2" stroke-linecap="round" opacity="0.4"/>
  </g>
</svg>

# The Complete Brewing Guide

<div class="divider"></div>

Three methods, one perfect cup

<div style="display: flex; gap: 12px; justify-content: center; margin-top: 20px;">
  <div style="display: inline-flex; align-items: center; gap: 6px; background: var(--card); border: 1px solid var(--border); border-radius: 20px; padding: 5px 16px; font-size: 0.68em; color: var(--muted);">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#c4956a" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
    3 METHODS
  </div>
  <div style="display: inline-flex; align-items: center; gap: 6px; background: var(--card); border: 1px solid var(--border); border-radius: 20px; padding: 5px 16px; font-size: 0.68em; color: var(--muted);">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#c4956a" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
    2 - 5 MIN BREW
  </div>
  <div style="display: inline-flex; align-items: center; gap: 6px; background: var(--card); border: 1px solid var(--border); border-radius: 20px; padding: 5px 16px; font-size: 0.68em; color: var(--muted);">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#c4956a" stroke-width="2"><path d="M18 8h1a4 4 0 0 1 0 8h-1"/><path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z"/></svg>
    BEGINNER FRIENDLY
  </div>
</div>

---

### Method Comparison

## Choose Your Brew

<div style="display: flex; gap: 18px; margin-top: 16px;">

  <!-- Pour Over -->
  <div class="method-card">
    <svg width="50" height="50" viewBox="0 0 50 50">
      <!-- V60 dripper shape -->
      <path d="M10 10 L20 44 L30 44 L40 10" fill="none" stroke="#c4956a" stroke-width="2.5" stroke-linejoin="round"/>
      <line x1="10" y1="10" x2="40" y2="10" stroke="#c4956a" stroke-width="2"/>
      <!-- Filter lines -->
      <line x1="18" y1="22" x2="32" y2="22" stroke="#c4956a" stroke-width="0.8" opacity="0.4"/>
      <line x1="19" y1="28" x2="31" y2="28" stroke="#c4956a" stroke-width="0.8" opacity="0.4"/>
      <line x1="20" y1="34" x2="30" y2="34" stroke="#c4956a" stroke-width="0.8" opacity="0.4"/>
      <!-- Drip -->
      <circle cx="25" cy="48" r="1.5" fill="#c4956a" opacity="0.6"/>
    </svg>
    <h4>Pour Over</h4>

    <!-- Grind Size Bar -->
    <div class="meter-label">Grind: Medium-Fine</div>
    <div style="display: flex; gap: 2px; justify-content: center; margin-bottom: 10px;">
      <div style="width: 16px; height: 8px; border-radius: 2px; background: #c4956a;"></div>
      <div style="width: 16px; height: 8px; border-radius: 2px; background: #c4956a;"></div>
      <div style="width: 16px; height: 8px; border-radius: 2px; background: #c4956a;"></div>
      <div style="width: 16px; height: 8px; border-radius: 2px; background: rgba(196,149,106,0.2);"></div>
      <div style="width: 16px; height: 8px; border-radius: 2px; background: rgba(196,149,106,0.2);"></div>
    </div>

    <!-- Brew Time Donut -->
    <div class="meter-label">Brew Time</div>
    <svg width="70" height="70" viewBox="0 0 70 70" style="display: block; margin: 0 auto 8px;">
      <circle cx="35" cy="35" r="28" fill="none" stroke="#3a2e25" stroke-width="5"/>
      <circle cx="35" cy="35" r="28" fill="none" stroke="#c4956a" stroke-width="5"
              stroke-dasharray="176" stroke-dashoffset="70"
              stroke-linecap="round" transform="rotate(-90 35 35)"/>
      <text x="35" y="33" text-anchor="middle" fill="#f5e6d3" font-family="Space Mono" font-size="14" font-weight="700">3:30</text>
      <text x="35" y="44" text-anchor="middle" fill="#8a7a6a" font-family="Work Sans" font-size="8">MIN</text>
    </svg>

    <!-- Strength Meter -->
    <div class="meter-label">Strength: Light-Medium</div>
    <div style="display: flex; gap: 3px; justify-content: center;">
      <svg width="12" height="12" viewBox="0 0 12 12"><circle cx="6" cy="6" r="5" fill="#c4956a"/></svg>
      <svg width="12" height="12" viewBox="0 0 12 12"><circle cx="6" cy="6" r="5" fill="#c4956a"/></svg>
      <svg width="12" height="12" viewBox="0 0 12 12"><circle cx="6" cy="6" r="5" fill="#c4956a" opacity="0.3"/></svg>
      <svg width="12" height="12" viewBox="0 0 12 12"><circle cx="6" cy="6" r="5" fill="#c4956a" opacity="0.3"/></svg>
    </div>

    <!-- Temp Badge -->
    <div style="margin-top: 10px; display: inline-block; background: var(--espresso); border: 1px solid var(--border); border-radius: 6px; padding: 3px 10px; font-size: 0.65em; color: var(--accent);">
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#c4956a" stroke-width="2" style="vertical-align: middle;"><path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z"/></svg>
      96 C / 205 F
    </div>
  </div>

  <!-- French Press -->
  <div class="method-card">
    <svg width="50" height="50" viewBox="0 0 50 50">
      <!-- Press body -->
      <rect x="12" y="10" width="26" height="34" rx="3" fill="none" stroke="#c4956a" stroke-width="2.5"/>
      <!-- Plunger handle -->
      <line x1="25" y1="4" x2="25" y2="14" stroke="#c4956a" stroke-width="2.5" stroke-linecap="round"/>
      <line x1="19" y1="4" x2="31" y2="4" stroke="#c4956a" stroke-width="2.5" stroke-linecap="round"/>
      <!-- Filter mesh -->
      <line x1="14" y1="20" x2="36" y2="20" stroke="#c4956a" stroke-width="1.5"/>
      <line x1="14" y1="22" x2="36" y2="22" stroke="#c4956a" stroke-width="0.8" opacity="0.5"/>
      <!-- Spout -->
      <path d="M38 16 C42 16 42 24 38 24" fill="none" stroke="#c4956a" stroke-width="2"/>
      <!-- Coffee level -->
      <rect x="14" y="24" width="22" height="18" rx="1" fill="#c4956a" opacity="0.15"/>
    </svg>
    <h4>French Press</h4>

    <!-- Grind Size Bar -->
    <div class="meter-label">Grind: Coarse</div>
    <div style="display: flex; gap: 2px; justify-content: center; margin-bottom: 10px;">
      <div style="width: 16px; height: 8px; border-radius: 2px; background: #c4956a;"></div>
      <div style="width: 16px; height: 8px; border-radius: 2px; background: #c4956a;"></div>
      <div style="width: 16px; height: 8px; border-radius: 2px; background: #c4956a;"></div>
      <div style="width: 16px; height: 8px; border-radius: 2px; background: #c4956a;"></div>
      <div style="width: 16px; height: 8px; border-radius: 2px; background: #c4956a;"></div>
    </div>

    <!-- Brew Time Donut -->
    <div class="meter-label">Brew Time</div>
    <svg width="70" height="70" viewBox="0 0 70 70" style="display: block; margin: 0 auto 8px;">
      <circle cx="35" cy="35" r="28" fill="none" stroke="#3a2e25" stroke-width="5"/>
      <circle cx="35" cy="35" r="28" fill="none" stroke="#c4956a" stroke-width="5"
              stroke-dasharray="176" stroke-dashoffset="35"
              stroke-linecap="round" transform="rotate(-90 35 35)"/>
      <text x="35" y="33" text-anchor="middle" fill="#f5e6d3" font-family="Space Mono" font-size="14" font-weight="700">4:00</text>
      <text x="35" y="44" text-anchor="middle" fill="#8a7a6a" font-family="Work Sans" font-size="8">MIN</text>
    </svg>

    <!-- Strength Meter -->
    <div class="meter-label">Strength: Full-Bodied</div>
    <div style="display: flex; gap: 3px; justify-content: center;">
      <svg width="12" height="12" viewBox="0 0 12 12"><circle cx="6" cy="6" r="5" fill="#c4956a"/></svg>
      <svg width="12" height="12" viewBox="0 0 12 12"><circle cx="6" cy="6" r="5" fill="#c4956a"/></svg>
      <svg width="12" height="12" viewBox="0 0 12 12"><circle cx="6" cy="6" r="5" fill="#c4956a"/></svg>
      <svg width="12" height="12" viewBox="0 0 12 12"><circle cx="6" cy="6" r="5" fill="#c4956a" opacity="0.3"/></svg>
    </div>

    <!-- Temp Badge -->
    <div style="margin-top: 10px; display: inline-block; background: var(--espresso); border: 1px solid var(--border); border-radius: 6px; padding: 3px 10px; font-size: 0.65em; color: var(--accent);">
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#c4956a" stroke-width="2" style="vertical-align: middle;"><path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z"/></svg>
      93 C / 200 F
    </div>
  </div>

  <!-- AeroPress -->
  <div class="method-card">
    <svg width="50" height="50" viewBox="0 0 50 50">
      <!-- Outer cylinder -->
      <rect x="15" y="14" width="20" height="30" rx="2" fill="none" stroke="#c4956a" stroke-width="2.5"/>
      <!-- Inner plunger -->
      <rect x="17" y="6" width="16" height="12" rx="2" fill="none" stroke="#c4956a" stroke-width="2"/>
      <!-- Plunger rod -->
      <line x1="25" y1="2" x2="25" y2="8" stroke="#c4956a" stroke-width="2.5" stroke-linecap="round"/>
      <line x1="20" y1="2" x2="30" y2="2" stroke="#c4956a" stroke-width="2.5" stroke-linecap="round"/>
      <!-- Filter cap -->
      <rect x="13" y="44" width="24" height="4" rx="2" fill="none" stroke="#c4956a" stroke-width="1.5"/>
      <!-- Drip -->
      <circle cx="25" cy="50" r="1" fill="#c4956a" opacity="0.5"/>
      <!-- Pressure arrows -->
      <polygon points="25,22 22,26 28,26" fill="#c4956a" opacity="0.4"/>
      <polygon points="25,28 22,32 28,32" fill="#c4956a" opacity="0.3"/>
    </svg>
    <h4>AeroPress</h4>

    <!-- Grind Size Bar -->
    <div class="meter-label">Grind: Fine-Medium</div>
    <div style="display: flex; gap: 2px; justify-content: center; margin-bottom: 10px;">
      <div style="width: 16px; height: 8px; border-radius: 2px; background: #c4956a;"></div>
      <div style="width: 16px; height: 8px; border-radius: 2px; background: #c4956a;"></div>
      <div style="width: 16px; height: 8px; border-radius: 2px; background: rgba(196,149,106,0.2);"></div>
      <div style="width: 16px; height: 8px; border-radius: 2px; background: rgba(196,149,106,0.2);"></div>
      <div style="width: 16px; height: 8px; border-radius: 2px; background: rgba(196,149,106,0.2);"></div>
    </div>

    <!-- Brew Time Donut -->
    <div class="meter-label">Brew Time</div>
    <svg width="70" height="70" viewBox="0 0 70 70" style="display: block; margin: 0 auto 8px;">
      <circle cx="35" cy="35" r="28" fill="none" stroke="#3a2e25" stroke-width="5"/>
      <circle cx="35" cy="35" r="28" fill="none" stroke="#c4956a" stroke-width="5"
              stroke-dasharray="176" stroke-dashoffset="106"
              stroke-linecap="round" transform="rotate(-90 35 35)"/>
      <text x="35" y="33" text-anchor="middle" fill="#f5e6d3" font-family="Space Mono" font-size="14" font-weight="700">2:00</text>
      <text x="35" y="44" text-anchor="middle" fill="#8a7a6a" font-family="Work Sans" font-size="8">MIN</text>
    </svg>

    <!-- Strength Meter -->
    <div class="meter-label">Strength: Concentrated</div>
    <div style="display: flex; gap: 3px; justify-content: center;">
      <svg width="12" height="12" viewBox="0 0 12 12"><circle cx="6" cy="6" r="5" fill="#c4956a"/></svg>
      <svg width="12" height="12" viewBox="0 0 12 12"><circle cx="6" cy="6" r="5" fill="#c4956a"/></svg>
      <svg width="12" height="12" viewBox="0 0 12 12"><circle cx="6" cy="6" r="5" fill="#c4956a"/></svg>
      <svg width="12" height="12" viewBox="0 0 12 12"><circle cx="6" cy="6" r="5" fill="#c4956a"/></svg>
    </div>

    <!-- Temp Badge -->
    <div style="margin-top: 10px; display: inline-block; background: var(--espresso); border: 1px solid var(--border); border-radius: 6px; padding: 3px 10px; font-size: 0.65em; color: var(--accent);">
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#c4956a" stroke-width="2" style="vertical-align: middle;"><path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z"/></svg>
      85 C / 185 F
    </div>
  </div>

</div>

<div style="text-align: center; margin-top: 14px;">
  <div style="display: flex; gap: 2px; justify-content: center; align-items: center;">
    <span style="font-size: 0.6em; color: var(--muted); text-transform: uppercase; letter-spacing: 0.1em; margin-right: 8px;">Grind Scale</span>
    <div style="width: 14px; height: 10px; border-radius: 2px; background: #4a3628;"></div>
    <div style="width: 14px; height: 10px; border-radius: 2px; background: #5a4638;"></div>
    <div style="width: 14px; height: 10px; border-radius: 2px; background: #6a5648;"></div>
    <div style="width: 14px; height: 10px; border-radius: 2px; background: #8a7668;"></div>
    <div style="width: 14px; height: 10px; border-radius: 2px; background: #a09080;"></div>
    <div style="width: 14px; height: 10px; border-radius: 2px; background: #b8a898;"></div>
    <div style="width: 14px; height: 10px; border-radius: 2px; background: #c4b4a4;"></div>
    <span style="font-size: 0.55em; color: var(--muted); margin: 0 6px;">FINE</span>
    <svg width="20" height="8" viewBox="0 0 20 8"><line x1="0" y1="4" x2="14" y2="4" stroke="#8a7a6a" stroke-width="1"/><polygon points="14,1 20,4 14,7" fill="#8a7a6a"/></svg>
    <span style="font-size: 0.55em; color: var(--muted); margin: 0 6px;">COARSE</span>
  </div>
</div>

---

### Step by Step

## Pour-Over Method

<div style="display: flex; align-items: flex-start; justify-content: center; gap: 0; margin-top: 30px;">

  <!-- Step 1 -->
  <div style="display: flex; flex-direction: column; align-items: center; width: 140px;">
    <div class="step-circle" style="animation: float 4s ease-in-out infinite;">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#c4956a" stroke-width="1.5">
        <path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z"/>
      </svg>
    </div>
    <div style="font-family: 'Space Mono', monospace; font-weight: 700; font-size: 0.75em; color: var(--accent); margin-top: 8px;">01</div>
    <div style="font-weight: 600; font-size: 0.78em; color: var(--light); margin-top: 2px;">Boil Water</div>
    <div style="font-size: 0.62em; color: var(--muted); text-align: center; margin-top: 4px; line-height: 1.3;">Heat to 96C. Let kettle rest 30s off boil.</div>
    <div style="display: inline-block; background: var(--espresso); border: 1px solid var(--border); border-radius: 4px; padding: 2px 8px; font-family: 'Space Mono', monospace; font-size: 0.55em; color: var(--accent); margin-top: 6px;">0:00</div>
  </div>

  <!-- Connector -->
  <div style="display: flex; align-items: center; padding-top: 22px;">
    <svg width="30" height="12" viewBox="0 0 30 12">
      <line x1="0" y1="6" x2="20" y2="6" stroke="#3a2e25" stroke-width="2" stroke-dasharray="3,3"/>
      <polygon points="20,2 30,6 20,10" fill="#c4956a" opacity="0.6"/>
    </svg>
  </div>

  <!-- Step 2 -->
  <div style="display: flex; flex-direction: column; align-items: center; width: 140px;">
    <div class="step-circle" style="animation: float 4s ease-in-out 0.4s infinite;">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#c4956a" stroke-width="1.5">
        <circle cx="12" cy="12" r="10"/>
        <path d="M8 12 C8 8 16 8 16 12 C16 16 8 16 8 12"/>
      </svg>
    </div>
    <div style="font-family: 'Space Mono', monospace; font-weight: 700; font-size: 0.75em; color: var(--accent); margin-top: 8px;">02</div>
    <div style="font-weight: 600; font-size: 0.78em; color: var(--light); margin-top: 2px;">Grind Beans</div>
    <div style="font-size: 0.62em; color: var(--muted); text-align: center; margin-top: 4px; line-height: 1.3;">18g medium-fine. Like table salt texture.</div>
    <div style="display: inline-block; background: var(--espresso); border: 1px solid var(--border); border-radius: 4px; padding: 2px 8px; font-family: 'Space Mono', monospace; font-size: 0.55em; color: var(--accent); margin-top: 6px;">0:15</div>
  </div>

  <!-- Connector -->
  <div style="display: flex; align-items: center; padding-top: 22px;">
    <svg width="30" height="12" viewBox="0 0 30 12">
      <line x1="0" y1="6" x2="20" y2="6" stroke="#3a2e25" stroke-width="2" stroke-dasharray="3,3"/>
      <polygon points="20,2 30,6 20,10" fill="#c4956a" opacity="0.6"/>
    </svg>
  </div>

  <!-- Step 3 -->
  <div style="display: flex; flex-direction: column; align-items: center; width: 140px;">
    <div class="step-circle" style="animation: float 4s ease-in-out 0.8s infinite;">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#c4956a" stroke-width="1.5">
        <path d="M12 2v6"/>
        <circle cx="12" cy="12" r="4"/>
        <path d="M8 14 C6 18 18 18 16 14"/>
      </svg>
    </div>
    <div style="font-family: 'Space Mono', monospace; font-weight: 700; font-size: 0.75em; color: var(--accent); margin-top: 8px;">03</div>
    <div style="font-weight: 600; font-size: 0.78em; color: var(--light); margin-top: 2px;">Bloom</div>
    <div style="font-size: 0.62em; color: var(--muted); text-align: center; margin-top: 4px; line-height: 1.3;">Pour 40g water in spirals. Wait 30s for CO2 release.</div>
    <div style="display: inline-block; background: var(--espresso); border: 1px solid var(--border); border-radius: 4px; padding: 2px 8px; font-family: 'Space Mono', monospace; font-size: 0.55em; color: var(--accent); margin-top: 6px;">0:30</div>
  </div>

  <!-- Connector -->
  <div style="display: flex; align-items: center; padding-top: 22px;">
    <svg width="30" height="12" viewBox="0 0 30 12">
      <line x1="0" y1="6" x2="20" y2="6" stroke="#3a2e25" stroke-width="2" stroke-dasharray="3,3"/>
      <polygon points="20,2 30,6 20,10" fill="#c4956a" opacity="0.6"/>
    </svg>
  </div>

  <!-- Step 4 -->
  <div style="display: flex; flex-direction: column; align-items: center; width: 140px;">
    <div class="step-circle" style="animation: float 4s ease-in-out 1.2s infinite;">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#c4956a" stroke-width="1.5">
        <path d="M12 2 C12 2 6 8 6 14 A6 6 0 0 0 18 14 C18 8 12 2 12 2"/>
      </svg>
    </div>
    <div style="font-family: 'Space Mono', monospace; font-weight: 700; font-size: 0.75em; color: var(--accent); margin-top: 8px;">04</div>
    <div style="font-weight: 600; font-size: 0.78em; color: var(--light); margin-top: 2px;">Pour</div>
    <div style="font-size: 0.62em; color: var(--muted); text-align: center; margin-top: 4px; line-height: 1.3;">Slow concentric pours to 300g total. Keep water level steady.</div>
    <div style="display: inline-block; background: var(--espresso); border: 1px solid var(--border); border-radius: 4px; padding: 2px 8px; font-family: 'Space Mono', monospace; font-size: 0.55em; color: var(--accent); margin-top: 6px;">1:00</div>
  </div>

  <!-- Connector -->
  <div style="display: flex; align-items: center; padding-top: 22px;">
    <svg width="30" height="12" viewBox="0 0 30 12">
      <line x1="0" y1="6" x2="20" y2="6" stroke="#3a2e25" stroke-width="2" stroke-dasharray="3,3"/>
      <polygon points="20,2 30,6 20,10" fill="#c4956a" opacity="0.6"/>
    </svg>
  </div>

  <!-- Step 5 -->
  <div style="display: flex; flex-direction: column; align-items: center; width: 140px;">
    <div class="step-circle" style="border-color: var(--accent-hover); box-shadow: 0 0 12px rgba(196,149,106,0.3); animation: float 4s ease-in-out 1.6s infinite;">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#c4956a" stroke-width="1.5">
        <path d="M18 8h1a4 4 0 0 1 0 8h-1"/><path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z"/>
      </svg>
    </div>
    <div style="font-family: 'Space Mono', monospace; font-weight: 700; font-size: 0.75em; color: var(--accent); margin-top: 8px;">05</div>
    <div style="font-weight: 600; font-size: 0.78em; color: var(--light); margin-top: 2px;">Draw Down</div>
    <div style="font-size: 0.62em; color: var(--muted); text-align: center; margin-top: 4px; line-height: 1.3;">Let it drip through completely. Flat coffee bed = good extraction.</div>
    <div style="display: inline-block; background: var(--espresso); border: 1px solid var(--border); border-radius: 4px; padding: 2px 8px; font-family: 'Space Mono', monospace; font-size: 0.55em; color: var(--accent); margin-top: 6px;">3:30</div>
  </div>

</div>

<!-- Total time bar -->
<div style="margin-top: 24px;">
  <div style="display: flex; justify-content: space-between; font-size: 0.65em; margin-bottom: 4px;">
    <span style="color: var(--muted);">Total Brew Time</span>
    <span style="font-family: 'Space Mono', monospace; color: var(--accent); font-weight: 700;">3 min 30 sec</span>
  </div>
  <div style="background: var(--card); border-radius: 8px; height: 12px; border: 1px solid var(--border); overflow: hidden;">
    <div style="background: linear-gradient(90deg, #4a3628, #c4956a, #d4a87d); width: 100%; height: 100%; border-radius: 8px;"></div>
  </div>
  <div style="display: flex; justify-content: space-between; font-size: 0.5em; color: var(--muted); margin-top: 2px; font-family: 'Space Mono', monospace;">
    <span>0:00</span>
    <span>0:30</span>
    <span>1:00</span>
    <span>2:00</span>
    <span>3:30</span>
  </div>
</div>
