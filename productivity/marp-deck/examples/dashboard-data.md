---
marp: true
theme: default
paginate: true
style: |
  @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;800&family=Raleway:wght@100;200;300&display=swap');

  :root {
    --a: #ff6b1a;
    --a2: #ff8c4a;
    --bg: #000;
    --s: #080808;
    --b: #111;
    --m: #555;
    --t: #fff;
    --g: #22c55e;
    --r: #ef4444;
    --y: #f5a623;
    --body: #999;
    --label: #666;
  }

  section {
    background: var(--bg);
    color: var(--t);
    font-family: 'Raleway', sans-serif;
    font-weight: 200;
    padding: 56px 72px;
    line-height: 1.5;
  }

  h1 { font-family: 'Outfit'; font-weight: 800; font-size: 3em; color: var(--t); letter-spacing: -0.03em; line-height: 1; margin: 0 0 4px; }
  h2 { font-family: 'Raleway'; font-weight: 100; font-size: 1.3em; color: #888; margin: 0 0 20px; }
  h3 { font-family: 'Outfit'; font-weight: 600; font-size: 0.6em; color: var(--m); text-transform: uppercase; letter-spacing: 0.2em; margin: 0 0 4px; }
  strong { color: var(--a); font-weight: 300; }

  section.lead { display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; }
  section.lead h1 { font-size: 3.8em; color: var(--t); }

  section::after { font-family: 'Outfit'; font-size: 0.6em; color: #151515; }

  header { text-align: right; padding: 0; margin: 0; }
  header img { margin: 0; }

  .tag { font-family: 'Outfit'; font-weight: 600; font-size: 0.55em; letter-spacing: 0.12em; text-transform: uppercase; padding: 3px 10px; border-radius: 4px; display: inline-block; }

  details { background: var(--s); border: 1px solid var(--b); border-radius: 10px; padding: 14px 18px; margin-top: 8px; }
  details summary { color: var(--a); font-family: 'Outfit'; font-weight: 600; font-size: 0.8em; cursor: pointer; letter-spacing: 0.03em; }
  details p { color: var(--body); font-size: 0.78em; margin-top: 8px; line-height: 1.6; }

  .row:hover { background: #0c0c0c; }
  .row { transition: background 0.2s; border-radius: 6px; padding: 0 8px; }

  abbr { text-decoration: none; border-bottom: 1px dotted #333; cursor: help; }
header: ''
footer: ''
---

<!-- _class: lead -->
<!-- _header: '' -->
<!-- _paginate: false -->

![bg brightness:0.15](https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=1400)

# Facebook Ads

<div style="font-family: 'Raleway'; font-weight: 100; font-size: 1em; color: #ffffff55; margin-top: 8px;">April 2026 · Monthly Performance Report</div>

<div style="display: flex; gap: 8px; margin-top: 20px;">
  <span style="background: #ff6b1a15; border: 1px solid #ff6b1a33; border-radius: 20px; padding: 4px 14px; font-family: 'Outfit'; font-size: 0.55em; color: #ff6b1aaa; font-weight: 400;">8 Campaigns</span>
  <span style="background: #ff6b1a15; border: 1px solid #ff6b1a33; border-radius: 20px; padding: 4px 14px; font-family: 'Outfit'; font-size: 0.55em; color: #ff6b1aaa; font-weight: 400;">$10.9K Spend</span>
  <span style="background: #ff6b1a15; border: 1px solid #ff6b1a33; border-radius: 20px; padding: 4px 14px; font-family: 'Outfit'; font-size: 0.55em; color: #ff6b1aaa; font-weight: 400;">3.8x ROAS</span>
</div>

---

### Summary

<div style="display: flex; gap: 14px; margin-top: 16px;">
  <div style="flex: 1; background: var(--s); border: 1px solid var(--b); border-radius: 10px; padding: 18px; position: relative; overflow: hidden;">
    <div style="position: absolute; top: 0; left: 0; width: 100%; height: 2px; background: linear-gradient(90deg, var(--a), transparent);"></div>
    <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 10px;">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--m)" stroke-width="1.5"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 1 0 0 7h5a3.5 3.5 0 1 1 0 7H6"/></svg>
      <span style="font-family: 'Outfit'; font-weight: 600; font-size: 0.5em; color: var(--m); letter-spacing: 0.1em;">SPEND</span>
    </div>
    <div style="font-family: 'Outfit'; font-size: 2em; font-weight: 800; color: var(--t); line-height: 1;">$10,939</div>
    <div style="font-size: 0.65em; color: var(--g); margin-top: 6px;">
      <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2" style="vertical-align: middle;"><polyline points="18 15 12 9 6 15"/></svg> +32.7%
    </div>
  </div>
  <div style="flex: 1; background: var(--s); border: 1px solid var(--b); border-radius: 10px; padding: 18px; position: relative; overflow: hidden;">
    <div style="position: absolute; top: 0; left: 0; width: 100%; height: 2px; background: linear-gradient(90deg, var(--g), transparent);"></div>
    <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 10px;">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--m)" stroke-width="1.5"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
      <span style="font-family: 'Outfit'; font-weight: 600; font-size: 0.5em; color: var(--m); letter-spacing: 0.1em;">REVENUE</span>
    </div>
    <div style="font-family: 'Outfit'; font-size: 2em; font-weight: 800; color: var(--g); line-height: 1;">$41,946</div>
    <div style="font-size: 0.65em; color: var(--g); margin-top: 6px;">
      <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2" style="vertical-align: middle;"><polyline points="18 15 12 9 6 15"/></svg> +49.3%
    </div>
  </div>
  <div style="flex: 1; background: var(--s); border: 1px solid var(--b); border-radius: 10px; padding: 18px; position: relative; overflow: hidden;">
    <div style="position: absolute; top: 0; left: 0; width: 100%; height: 2px; background: linear-gradient(90deg, var(--a), transparent);"></div>
    <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 10px;">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--m)" stroke-width="1.5"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>
      <span style="font-family: 'Outfit'; font-weight: 600; font-size: 0.5em; color: var(--m); letter-spacing: 0.1em;">ROAS</span>
    </div>
    <div style="font-family: 'Outfit'; font-size: 2em; font-weight: 800; color: var(--t); line-height: 1;">3.8x</div>
    <div style="font-size: 0.65em; color: var(--g); margin-top: 6px;">
      <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2" style="vertical-align: middle;"><polyline points="18 15 12 9 6 15"/></svg> +11.8%
    </div>
  </div>
  <div style="flex: 1; background: var(--s); border: 1px solid var(--b); border-radius: 10px; padding: 18px; position: relative; overflow: hidden;">
    <div style="position: absolute; top: 0; left: 0; width: 100%; height: 2px; background: linear-gradient(90deg, var(--a), transparent);"></div>
    <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 10px;">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--m)" stroke-width="1.5"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
      <span style="font-family: 'Outfit'; font-weight: 600; font-size: 0.5em; color: var(--m); letter-spacing: 0.1em;">CONVERSIONS</span>
    </div>
    <div style="font-family: 'Outfit'; font-size: 2em; font-weight: 800; color: var(--t); line-height: 1;">648</div>
    <div style="font-size: 0.65em; color: var(--g); margin-top: 6px;">
      <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2" style="vertical-align: middle;"><polyline points="18 15 12 9 6 15"/></svg> +22.1%
    </div>
  </div>
</div>

---

### Funnel

![bg right:35% brightness:0.2 blur:3px](https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=800)

<div style="margin-top: 20px;">
  <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 28px;">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--label)" stroke-width="1.5"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
    <div>
      <div style="font-family: 'Outfit'; font-size: 1.6em; font-weight: 800; color: var(--t); line-height: 1;">1.31M</div>
      <div style="font-weight: 100; font-size: 0.6em; color: var(--label); letter-spacing: 0.1em;">IMPRESSIONS</div>
    </div>
  </div>
  <div style="width: 40px; border-left: 1px solid #222; height: 12px; margin-left: 10px;"></div>
  <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 28px;">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--label)" stroke-width="1.5"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
    <div>
      <div style="font-family: 'Outfit'; font-size: 1.6em; font-weight: 800; color: var(--t); line-height: 1;">1.01M</div>
      <div style="font-weight: 100; font-size: 0.6em; color: var(--label); letter-spacing: 0.1em;">REACH</div>
    </div>
    <div style="font-family: 'Outfit'; font-size: 0.6em; color: var(--label); margin-left: auto;">77%</div>
  </div>
  <div style="width: 40px; border-left: 1px solid #222; height: 12px; margin-left: 10px;"></div>
  <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 28px;">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--a)" stroke-width="1.5"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>
    <div>
      <div style="font-family: 'Outfit'; font-size: 1.6em; font-weight: 800; color: var(--a); line-height: 1;">17.6K</div>
      <div style="font-weight: 100; font-size: 0.6em; color: var(--label); letter-spacing: 0.1em;">CLICKS</div>
    </div>
    <div style="font-family: 'Outfit'; font-size: 0.6em; color: var(--label); margin-left: auto;">1.34% CTR</div>
  </div>
  <div style="width: 40px; border-left: 1px solid #222; height: 12px; margin-left: 10px;"></div>
  <div style="display: flex; align-items: center; gap: 12px;">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--g)" stroke-width="1.5"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
    <div>
      <div style="font-family: 'Outfit'; font-size: 1.6em; font-weight: 800; color: var(--g); line-height: 1;">648</div>
      <div style="font-weight: 100; font-size: 0.6em; color: var(--label); letter-spacing: 0.1em;">CONVERSIONS</div>
    </div>
    <div style="font-family: 'Outfit'; font-size: 0.6em; color: var(--label); margin-left: auto;">3.68%</div>
  </div>
</div>

---

### Spend Allocation

## Where the budget went

<div style="display: flex; gap: 24px; margin-top: 12px;">
  <div style="flex: 2;">
    <div style="display: flex; height: 20px; border-radius: 6px; overflow: hidden; margin-bottom: 14px;">
      <div style="background: var(--a); width: 26%;"></div>
      <div style="background: #cc5515; width: 20%;"></div>
      <div style="background: #444; width: 15%;"></div>
      <div style="background: var(--g); width: 13%;"></div>
      <div style="background: var(--r); width: 11%; opacity: 0.6;"></div>
      <div style="background: var(--g); width: 7%; opacity: 0.7;"></div>
      <div style="background: var(--g); width: 5%; opacity: 0.5;"></div>
      <div style="background: var(--y); width: 3%; opacity: 0.5;"></div>
    </div>
    <div style="display: flex; flex-wrap: wrap; gap: 10px;">
      <div style="display: flex; align-items: center; gap: 4px;"><div style="width: 8px; height: 8px; border-radius: 2px; background: var(--a);"></div><span style="font-size: 0.58em; color: var(--body);">New Customer $2.9K</span></div>
      <div style="display: flex; align-items: center; gap: 4px;"><div style="width: 8px; height: 8px; border-radius: 2px; background: #cc5515;"></div><span style="font-size: 0.58em; color: var(--body);">Spring $2.2K</span></div>
      <div style="display: flex; align-items: center; gap: 4px;"><div style="width: 8px; height: 8px; border-radius: 2px; background: #444;"></div><span style="font-size: 0.58em; color: var(--body);">Brand $1.6K</span></div>
      <div style="display: flex; align-items: center; gap: 4px;"><div style="width: 8px; height: 8px; border-radius: 2px; background: var(--g);"></div><span style="font-size: 0.58em; color: var(--body);">Dynamic $1.4K</span></div>
      <div style="display: flex; align-items: center; gap: 4px;"><div style="width: 8px; height: 8px; border-radius: 2px; background: var(--r); opacity: 0.6;"></div><span style="font-size: 0.58em; color: var(--body);">Competitor $1.2K</span></div>
      <div style="display: flex; align-items: center; gap: 4px;"><div style="width: 8px; height: 8px; border-radius: 2px; background: var(--g); opacity: 0.7;"></div><span style="font-size: 0.58em; color: var(--body);">Retarget $743</span></div>
    </div>
  </div>
  <div style="width: 1px; background: var(--b);"></div>
  <div style="width: 300px; display: flex; align-items: center; justify-content: center;">
    <svg width="280" height="280" viewBox="0 0 280 280" style="display: block;">
      <circle cx="140" cy="140" r="110" fill="none" stroke="#111" stroke-width="36"/>
      <circle cx="140" cy="140" r="110" fill="none" stroke="#ff6b1a" stroke-width="36" stroke-dasharray="180 511" stroke-dashoffset="0" transform="rotate(-90 140 140)"/>
      <circle cx="140" cy="140" r="110" fill="none" stroke="#cc5515" stroke-width="36" stroke-dasharray="138 553" stroke-dashoffset="-180" transform="rotate(-90 140 140)"/>
      <circle cx="140" cy="140" r="110" fill="none" stroke="#444" stroke-width="36" stroke-dasharray="104 587" stroke-dashoffset="-318" transform="rotate(-90 140 140)"/>
      <circle cx="140" cy="140" r="110" fill="none" stroke="#22c55e" stroke-width="36" stroke-dasharray="90 601" stroke-dashoffset="-422" transform="rotate(-90 140 140)"/>
      <circle cx="140" cy="140" r="110" fill="none" stroke="#ef4444" stroke-width="36" stroke-dasharray="76 615" stroke-dashoffset="-512" opacity="0.6" transform="rotate(-90 140 140)"/>
      <circle cx="140" cy="140" r="110" fill="none" stroke="#22c55e" stroke-width="36" stroke-dasharray="83 608" stroke-dashoffset="-588" opacity="0.5" transform="rotate(-90 140 140)"/>
      <text x="140" y="134" text-anchor="middle" fill="#fff" font-family="Outfit" font-size="28" font-weight="800">$10.9K</text>
      <text x="140" y="158" text-anchor="middle" fill="#555" font-family="Outfit" font-size="12" font-weight="600" letter-spacing="1.5">TOTAL SPEND</text>
    </svg>
  </div>
</div>

---

### ROAS Trend

## Monthly return on ad spend

<div style="margin-top: 16px;">
  <svg width="100%" height="240" viewBox="0 0 900 240" preserveAspectRatio="none">
    <line x1="0" y1="0" x2="900" y2="0" stroke="#111" stroke-width="1"/>
    <line x1="0" y1="60" x2="900" y2="60" stroke="#111" stroke-width="1"/>
    <line x1="0" y1="120" x2="900" y2="120" stroke="#111" stroke-width="1"/>
    <line x1="0" y1="180" x2="900" y2="180" stroke="#111" stroke-width="1"/>
    <!-- Y labels -->
    <text x="-5" y="8" fill="#333" font-family="Outfit" font-size="10" text-anchor="end">8x</text>
    <text x="-5" y="65" fill="#333" font-family="Outfit" font-size="10" text-anchor="end">6x</text>
    <text x="-5" y="125" fill="#333" font-family="Outfit" font-size="10" text-anchor="end">4x</text>
    <text x="-5" y="185" fill="#333" font-family="Outfit" font-size="10" text-anchor="end">2x</text>
    <!-- Target line -->
    <line x1="0" y1="150" x2="900" y2="150" stroke="#ff6b1a" stroke-width="1" stroke-dasharray="6,4" opacity="0.3"/>
    <text x="908" y="154" fill="#ff6b1a" font-family="Outfit" font-size="9" opacity="0.5">3x</text>
    <!-- Area fill -->
    <polygon points="0,195 150,186 300,177 450,165 600,156 750,141 900,132 900,240 0,240" fill="url(#areaGrad)" opacity="0.2"/>
    <defs><linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#ff6b1a"/><stop offset="100%" stop-color="transparent"/></linearGradient></defs>
    <!-- Line -->
    <polyline points="0,195 150,186 300,177 450,165 600,156 750,141 900,132" fill="none" stroke="#ff6b1a" stroke-width="2.5" stroke-linejoin="round"/>
    <!-- Points -->
    <circle cx="0" cy="195" r="3" fill="#ff6b1a"/>
    <circle cx="150" cy="186" r="3" fill="#ff6b1a"/>
    <circle cx="300" cy="177" r="3" fill="#ff6b1a"/>
    <circle cx="450" cy="165" r="3" fill="#ff6b1a"/>
    <circle cx="600" cy="156" r="3" fill="#ff6b1a"/>
    <circle cx="750" cy="141" r="3" fill="#ff6b1a"/>
    <circle cx="900" cy="132" r="5" fill="#ff6b1a" stroke="#000" stroke-width="2"/>
    <text x="900" y="122" text-anchor="middle" fill="#ff6b1a" font-family="Outfit" font-size="13" font-weight="700">3.8x</text>
    <!-- X labels -->
    <text x="0" y="235" fill="#333" font-family="Outfit" font-size="10">Oct</text>
    <text x="150" y="235" fill="#333" font-family="Outfit" font-size="10">Nov</text>
    <text x="300" y="235" fill="#333" font-family="Outfit" font-size="10">Dec</text>
    <text x="450" y="235" fill="#333" font-family="Outfit" font-size="10">Jan</text>
    <text x="600" y="235" fill="#333" font-family="Outfit" font-size="10">Feb</text>
    <text x="750" y="235" fill="#333" font-family="Outfit" font-size="10">Mar</text>
    <text x="880" y="235" fill="#ff6b1a" font-family="Outfit" font-size="10" font-weight="600">Apr</text>
  </svg>
</div>

---

### Campaign Performance

<div style="margin-top: 8px; font-size: 0.65em;">
  <div class="row" style="display: flex; align-items: center; gap: 10px; padding: 8px 8px; border-bottom: 1px solid #0e0e0e;">
    <svg width="6" height="6" viewBox="0 0 6 6"><circle cx="3" cy="3" r="3" fill="#22c55e"/></svg>
    <div style="width: 130px; font-weight: 300; color: #ccc;">Retargeting</div>
    <div style="flex: 1; height: 3px; background: #0a0a0a; border-radius: 2px; overflow: hidden;"><div style="background: var(--g); width: 100%; height: 100%;"></div></div>
    <div style="font-family: 'Outfit'; font-weight: 700; color: var(--g); width: 30px; text-align: right;">8.7x</div>
    <div style="color: var(--body); width: 44px; text-align: right;">$743</div>
    <!-- sparkline -->
    <svg width="50" height="16" viewBox="0 0 50 16"><polyline points="0,14 8,12 16,10 24,8 32,6 40,4 50,2" fill="none" stroke="#22c55e" stroke-width="1.2"/></svg>
  </div>
  <div class="row" style="display: flex; align-items: center; gap: 10px; padding: 8px 8px; border-bottom: 1px solid #0e0e0e;">
    <svg width="6" height="6" viewBox="0 0 6 6"><circle cx="3" cy="3" r="3" fill="#22c55e"/></svg>
    <div style="width: 130px; font-weight: 300; color: #ccc;">Dynamic Ads</div>
    <div style="flex: 1; height: 3px; background: #0a0a0a; border-radius: 2px; overflow: hidden;"><div style="background: var(--g); width: 71%; height: 100%;"></div></div>
    <div style="font-family: 'Outfit'; font-weight: 700; color: var(--g); width: 30px; text-align: right;">6.2x</div>
    <div style="color: var(--body); width: 44px; text-align: right;">$1,380</div>
    <svg width="50" height="16" viewBox="0 0 50 16"><polyline points="0,12 8,11 16,10 24,8 32,6 40,5 50,3" fill="none" stroke="#22c55e" stroke-width="1.2"/></svg>
  </div>
  <div class="row" style="display: flex; align-items: center; gap: 10px; padding: 8px 8px; border-bottom: 1px solid #0e0e0e;">
    <svg width="6" height="6" viewBox="0 0 6 6"><circle cx="3" cy="3" r="3" fill="#22c55e"/></svg>
    <div style="width: 130px; font-weight: 300; color: #ccc;">Spring Sale</div>
    <div style="flex: 1; height: 3px; background: #0a0a0a; border-radius: 2px; overflow: hidden;"><div style="background: var(--a); width: 48%; height: 100%;"></div></div>
    <div style="font-family: 'Outfit'; font-weight: 700; color: var(--a); width: 30px; text-align: right;">4.2x</div>
    <div style="color: var(--body); width: 44px; text-align: right;">$2,187</div>
    <svg width="50" height="16" viewBox="0 0 50 16"><polyline points="0,10 8,9 16,8 24,7 32,7 40,5 50,4" fill="none" stroke="#ff6b1a" stroke-width="1.2"/></svg>
  </div>
  <div class="row" style="display: flex; align-items: center; gap: 10px; padding: 8px 8px; border-bottom: 1px solid #0e0e0e;">
    <svg width="6" height="6" viewBox="0 0 6 6"><circle cx="3" cy="3" r="3" fill="#22c55e"/></svg>
    <div style="width: 130px; font-weight: 300; color: #ccc;">New Customer</div>
    <div style="flex: 1; height: 3px; background: #0a0a0a; border-radius: 2px; overflow: hidden;"><div style="background: var(--a); width: 44%; height: 100%;"></div></div>
    <div style="font-family: 'Outfit'; font-weight: 700; color: var(--a); width: 30px; text-align: right;">3.8x</div>
    <div style="color: var(--body); width: 44px; text-align: right;">$2,891</div>
    <svg width="50" height="16" viewBox="0 0 50 16"><polyline points="0,10 8,9 16,9 24,8 32,7 40,6 50,5" fill="none" stroke="#ff6b1a" stroke-width="1.2"/></svg>
  </div>
  <div class="row" style="display: flex; align-items: center; gap: 10px; padding: 8px 8px; border-bottom: 1px solid #0e0e0e;">
    <svg width="6" height="6" viewBox="0 0 6 6"><circle cx="3" cy="3" r="3" fill="#f5a623"/></svg>
    <div style="width: 130px; font-weight: 300; color: #ccc;">Brand Video</div>
    <div style="flex: 1; height: 3px; background: #0a0a0a; border-radius: 2px; overflow: hidden;"><div style="background: var(--y); width: 24%; height: 100%;"></div></div>
    <div style="font-family: 'Outfit'; font-weight: 700; color: var(--y); width: 30px; text-align: right;">2.1x</div>
    <div style="color: var(--body); width: 44px; text-align: right;">$1,623</div>
    <svg width="50" height="16" viewBox="0 0 50 16"><polyline points="0,8 8,8 16,9 24,10 32,10 40,11 50,12" fill="none" stroke="#f5a623" stroke-width="1.2"/></svg>
  </div>
  <div class="row" style="display: flex; align-items: center; gap: 10px; padding: 8px 8px;">
    <svg width="6" height="6" viewBox="0 0 6 6"><circle cx="3" cy="3" r="3" fill="#ef4444"/></svg>
    <div style="width: 130px; font-weight: 300; color: #ccc;">Competitor</div>
    <div style="flex: 1; height: 3px; background: #0a0a0a; border-radius: 2px; overflow: hidden;"><div style="background: var(--r); width: 22%; height: 100%;"></div></div>
    <div style="font-family: 'Outfit'; font-weight: 700; color: var(--r); width: 30px; text-align: right;">1.9x</div>
    <div style="color: var(--body); width: 44px; text-align: right;">$1,156</div>
    <svg width="50" height="16" viewBox="0 0 50 16"><polyline points="0,6 8,7 16,8 24,9 32,10 40,12 50,14" fill="none" stroke="#ef4444" stroke-width="1.2"/></svg>
  </div>
</div>

---

### Efficiency

<div style="display: flex; gap: 30px; justify-content: center; margin-top: 20px;">
  <div style="text-align: center;">
    <svg width="180" height="180" viewBox="0 0 180 180">
      <circle cx="90" cy="90" r="74" fill="none" stroke="#111" stroke-width="8"/>
      <circle cx="90" cy="90" r="74" fill="none" stroke="var(--g)" stroke-width="8" stroke-dasharray="465" stroke-dashoffset="51" stroke-linecap="round" transform="rotate(-90 90 90)"/>
      <text x="90" y="84" text-anchor="middle" fill="#fff" font-family="Outfit" font-size="36" font-weight="800">89%</text>
      <text x="90" y="106" text-anchor="middle" fill="#666" font-family="Outfit" font-size="11" font-weight="600" letter-spacing="1.5">BUDGET USED</text>
    </svg>
  </div>
  <div style="text-align: center;">
    <svg width="180" height="180" viewBox="0 0 180 180">
      <circle cx="90" cy="90" r="74" fill="none" stroke="#111" stroke-width="8"/>
      <circle cx="90" cy="90" r="74" fill="none" stroke="var(--a)" stroke-width="8" stroke-dasharray="465" stroke-dashoffset="140" stroke-linecap="round" transform="rotate(-90 90 90)"/>
      <text x="90" y="84" text-anchor="middle" fill="#fff" font-family="Outfit" font-size="36" font-weight="800">70%</text>
      <text x="90" y="106" text-anchor="middle" fill="#666" font-family="Outfit" font-size="11" font-weight="600" letter-spacing="1.5">ABOVE 3X</text>
    </svg>
  </div>
  <div style="text-align: center;">
    <svg width="180" height="180" viewBox="0 0 180 180">
      <circle cx="90" cy="90" r="74" fill="none" stroke="#111" stroke-width="8"/>
      <circle cx="90" cy="90" r="74" fill="none" stroke="var(--g)" stroke-width="8" stroke-dasharray="465" stroke-dashoffset="70" stroke-linecap="round" transform="rotate(-90 90 90)"/>
      <text x="90" y="84" text-anchor="middle" fill="#fff" font-family="Outfit" font-size="36" font-weight="800">85%</text>
      <text x="90" y="106" text-anchor="middle" fill="#666" font-family="Outfit" font-size="11" font-weight="600" letter-spacing="1.5">CONV EFF.</text>
    </svg>
  </div>
</div>

---

### Spend vs Revenue

<div style="display: flex; gap: 8px; margin-top: 20px; align-items: flex-end; height: 260px; padding-bottom: 20px; border-bottom: 1px solid #0a0a0a;">
  <div style="flex: 1; display: flex; gap: 3px; align-items: flex-end; justify-content: center;">
    <div style="width: 18px; background: linear-gradient(180deg, #222, #111); border-radius: 3px 3px 0 0; height: 56px;"></div>
    <div style="width: 18px; background: linear-gradient(180deg, var(--a), #cc5515); border-radius: 3px 3px 0 0; height: 200px;"></div>
  </div>
  <div style="flex: 1; display: flex; gap: 3px; align-items: flex-end; justify-content: center;">
    <div style="width: 18px; background: linear-gradient(180deg, #222, #111); border-radius: 3px 3px 0 0; height: 166px;"></div>
    <div style="width: 18px; background: linear-gradient(180deg, var(--a), #cc5515); border-radius: 3px 3px 0 0; height: 240px;"></div>
  </div>
  <div style="flex: 1; display: flex; gap: 3px; align-items: flex-end; justify-content: center;">
    <div style="width: 18px; background: linear-gradient(180deg, #222, #111); border-radius: 3px 3px 0 0; height: 105px;"></div>
    <div style="width: 18px; background: linear-gradient(180deg, var(--g), #198754); border-radius: 3px 3px 0 0; height: 186px;"></div>
  </div>
  <div style="flex: 1; display: flex; gap: 3px; align-items: flex-end; justify-content: center;">
    <div style="width: 18px; background: linear-gradient(180deg, #222, #111); border-radius: 3px 3px 0 0; height: 57px;"></div>
    <div style="width: 18px; background: linear-gradient(180deg, var(--g), #198754); border-radius: 3px 3px 0 0; height: 141px;"></div>
  </div>
  <div style="flex: 1; display: flex; gap: 3px; align-items: flex-end; justify-content: center;">
    <div style="width: 18px; background: linear-gradient(180deg, #222, #111); border-radius: 3px 3px 0 0; height: 124px;"></div>
    <div style="width: 18px; background: linear-gradient(180deg, #333, #222); border-radius: 3px 3px 0 0; height: 74px;"></div>
  </div>
  <div style="flex: 1; display: flex; gap: 3px; align-items: flex-end; justify-content: center;">
    <div style="width: 18px; background: linear-gradient(180deg, #222, #111); border-radius: 3px 3px 0 0; height: 88px;"></div>
    <div style="width: 18px; background: linear-gradient(180deg, var(--r), #b91c1c); border-radius: 3px 3px 0 0; height: 48px; opacity: 0.7;"></div>
  </div>
</div>
<div style="display: flex; gap: 8px; font-size: 0.48em; color: var(--label); font-weight: 200; margin-top: 4px;">
  <div style="flex: 1; text-align: center;">New Cust.</div><div style="flex: 1; text-align: center;">Spring</div><div style="flex: 1; text-align: center;">Dynamic</div><div style="flex: 1; text-align: center;">Retarget</div><div style="flex: 1; text-align: center;">Brand</div><div style="flex: 1; text-align: center;">Competitor</div>
</div>
<div style="display: flex; gap: 10px; margin-top: 8px;">
  <div style="display: flex; align-items: center; gap: 4px;"><div style="width: 10px; height: 10px; background: #1a1a1a; border-radius: 2px;"></div><span style="font-size: 0.5em; color: var(--label);">Spend</span></div>
  <div style="display: flex; align-items: center; gap: 4px;"><div style="width: 10px; height: 10px; background: var(--a); border-radius: 2px;"></div><span style="font-size: 0.5em; color: var(--label);">Revenue</span></div>
</div>

---

<!-- _class: lead -->
<!-- _header: '' -->
<!-- _paginate: false -->

![bg brightness:0.1](https://images.unsplash.com/photo-1504868584819-f8e8b4b6d7e3?w=1400)

<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#ff6b1a" stroke-width="1.2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>

# Deep Dives

<div style="font-family: 'Raleway'; font-weight: 100; font-size: 0.9em; color: #ffffff44;">Click to expand each campaign</div>

---

### Campaign Details

<details>
<summary>Retargeting — Cart Abandoners · 8.7x ROAS</summary>
<p>Highest ROAS in the account. Cart abandoners already showed intent — lowest CPA at $11.09. Frequency 1.46, still healthy. Revenue: $6,461 from $743 spend. <strong>Verdict: Scale to $1,500.</strong></p>
</details>

<details>
<summary>Dynamic Product Ads · 6.2x ROAS</summary>
<p>Product feed doing the heavy lifting. Cheapest CPC at $0.48. Meta's Advantage+ matching is working — 94 conversions from algorithmic targeting. Revenue: $8,556. <strong>Verdict: Scale to $2,000.</strong></p>
</details>

<details>
<summary>Spring Sale — Lookalike · 4.2x ROAS</summary>
<p>Lookalike audience performing well above breakeven. Low frequency at 1.29 means the pool hasn't saturated. Room to push spend without fatigue. Revenue: $9,185. <strong>Verdict: Maintain, watch frequency.</strong></p>
</details>

<details>
<summary>New Customer — Interest · 3.8x ROAS</summary>
<p>Biggest spend ($2,891), biggest volume (112 conversions). 17% of all account conversions. The workhorse campaign. <strong>Verdict: Maintain at $3,000.</strong></p>
</details>

<details>
<summary>Email Subscriber — Lead Gen · $2.51/lead</summary>
<p>No direct revenue — this is list building. 218 email subscribers enter the nurture sequence. Most strategic campaign for lifetime value. <strong>Verdict: Scale to $1,000.</strong></p>
</details>

---

<!-- _class: lead -->
<!-- _header: '' -->
<!-- _paginate: false -->

![bg brightness:0.08](https://images.unsplash.com/photo-1633158829585-23ba8f7c8caf?w=1400)

<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="1.2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>

# Problem Areas

<div style="font-family: 'Raleway'; font-weight: 100; font-size: 0.9em; color: #ffffff44;">Click to expand</div>

---

### Issues

<details>
<summary>Competitor Audience — 1.9x ROAS · Paused</summary>
<p>$1,156 spent for $2,196 revenue. CTR second-lowest at 1.06%. Targeting competitor audiences is expensive and intent doesn't transfer. <span style="color: #ef4444;">Kill — reallocate $1,200.</span></p>
</details>

<details>
<summary>Brand Awareness Video — 2.1x ROAS · $48 CPA</summary>
<p>298K impressions but only 34 conversions. Cheapest CPM ($5.44) — reaching people, not converting. <span style="color: #f5a623;">Cut if no lift by May 5.</span></p>
</details>

<details>
<summary>Summer Launch — 2.8x ROAS · Learning Phase</summary>
<p>Only $412 spent, 11 conversions. Still in Meta's learning phase. <span style="color: #999;">Wait until May 8, then reassess.</span></p>
</details>

---

### Gauge — Overall Health

<div style="display: flex; gap: 30px; justify-content: center; margin-top: 16px;">
  <div style="text-align: center;">
    <svg width="320" height="190" viewBox="0 0 320 190">
      <path d="M 30 170 A 130 130 0 0 1 290 170" fill="none" stroke="#111" stroke-width="18" stroke-linecap="round"/>
      <path d="M 30 170 A 130 130 0 0 1 270 82" fill="none" stroke="#ff6b1a" stroke-width="18" stroke-linecap="round"/>
      <line x1="160" y1="170" x2="256" y2="92" stroke="#fff" stroke-width="2.5" stroke-linecap="round"/>
      <circle cx="160" cy="170" r="7" fill="#fff"/>
      <text x="160" y="152" text-anchor="middle" fill="#fff" font-family="Outfit" font-size="44" font-weight="800">76</text>
      <text x="30" y="188" fill="#444" font-family="Outfit" font-size="12">0</text>
      <text x="290" y="188" fill="#444" font-family="Outfit" font-size="12">100</text>
    </svg>
    <div style="font-family: 'Outfit'; font-weight: 600; font-size: 0.7em; color: var(--label); letter-spacing: 0.12em; margin-top: 0;">ACCOUNT HEALTH</div>
  </div>
  <div style="text-align: center;">
    <svg width="320" height="190" viewBox="0 0 320 190">
      <path d="M 30 170 A 130 130 0 0 1 290 170" fill="none" stroke="#111" stroke-width="18" stroke-linecap="round"/>
      <path d="M 30 170 A 130 130 0 0 1 240 52" fill="none" stroke="#22c55e" stroke-width="18" stroke-linecap="round"/>
      <line x1="160" y1="170" x2="228" y2="62" stroke="#fff" stroke-width="2.5" stroke-linecap="round"/>
      <circle cx="160" cy="170" r="7" fill="#fff"/>
      <text x="160" y="152" text-anchor="middle" fill="#fff" font-family="Outfit" font-size="44" font-weight="800">82</text>
      <text x="30" y="188" fill="#444" font-family="Outfit" font-size="12">0</text>
      <text x="290" y="188" fill="#444" font-family="Outfit" font-size="12">100</text>
    </svg>
    <div style="font-family: 'Outfit'; font-weight: 600; font-size: 0.7em; color: var(--label); letter-spacing: 0.12em; margin-top: 0;">EFFICIENCY SCORE</div>
  </div>
  <div style="text-align: center;">
    <svg width="320" height="190" viewBox="0 0 320 190">
      <path d="M 30 170 A 130 130 0 0 1 290 170" fill="none" stroke="#111" stroke-width="18" stroke-linecap="round"/>
      <path d="M 30 170 A 130 130 0 0 1 185 42" fill="none" stroke="#f5a623" stroke-width="18" stroke-linecap="round"/>
      <line x1="160" y1="170" x2="178" y2="50" stroke="#fff" stroke-width="2.5" stroke-linecap="round"/>
      <circle cx="160" cy="170" r="7" fill="#fff"/>
      <text x="160" y="152" text-anchor="middle" fill="#fff" font-family="Outfit" font-size="44" font-weight="800">58</text>
      <text x="30" y="188" fill="#444" font-family="Outfit" font-size="12">0</text>
      <text x="290" y="188" fill="#444" font-family="Outfit" font-size="12">100</text>
    </svg>
    <div style="font-family: 'Outfit'; font-weight: 600; font-size: 0.7em; color: var(--label); letter-spacing: 0.12em; margin-top: 0;">SCALE READINESS</div>
  </div>
</div>

---

<!-- _class: lead -->
<!-- _header: '' -->
<!-- _paginate: false -->

![bg brightness:0.08](https://images.unsplash.com/photo-1554224155-6726b3ff858f?w=1400)

<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#ff6b1a" stroke-width="1.2"><path d="M12 20V10"/><path d="M18 20V4"/><path d="M6 20v-4"/></svg>

# Budget Plan

<div style="font-family: 'Raleway'; font-weight: 100; font-size: 0.9em; color: #ffffff44;">May 2026 reallocation</div>

---

### Reallocation

<div style="display: flex; gap: 24px; margin-top: 16px;">
  <div style="flex: 1;">
    <div style="font-family: 'Outfit'; font-weight: 600; font-size: 0.55em; color: var(--label); text-transform: uppercase; letter-spacing: 0.12em; margin-bottom: 14px;">Current · $11.4K</div>
    <div style="font-weight: 200; font-size: 0.78em; color: var(--label); line-height: 2.4;">
      New Customer — $3,000<br>
      Spring Sale — $2,500<br>
      Brand Video — $1,800<br>
      Dynamic Ads — $1,500<br>
      Competitor — $1,200<br>
      Retargeting — $800<br>
      Lead Gen — $600
    </div>
  </div>
  <div style="display: flex; align-items: center;">
    <svg width="40" height="16" viewBox="0 0 40 16"><line x1="0" y1="8" x2="30" y2="8" stroke="#222" stroke-width="1"/><polygon points="30,4 40,8 30,12" fill="var(--a)"/></svg>
  </div>
  <div style="flex: 1;">
    <div style="font-family: 'Outfit'; font-weight: 600; font-size: 0.55em; color: var(--a); text-transform: uppercase; letter-spacing: 0.12em; margin-bottom: 14px;">Proposed · $11.5K</div>
    <div style="font-weight: 200; font-size: 0.78em; color: #ccc; line-height: 2.4;">
      New Customer — $3,000<br>
      Spring Sale — $2,500<br>
      Dynamic Ads — <span style="color: var(--g);">$2,000</span> <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2" style="vertical-align: middle;"><polyline points="18 15 12 9 6 15"/></svg><br>
      Retargeting — <span style="color: var(--g);">$1,500</span> <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2" style="vertical-align: middle;"><polyline points="18 15 12 9 6 15"/></svg><br>
      Lead Gen — <span style="color: var(--g);">$1,000</span> <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2" style="vertical-align: middle;"><polyline points="18 15 12 9 6 15"/></svg><br>
      Brand Video — <span style="color: var(--y);">$1,000</span> <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="#f5a623" stroke-width="2" style="vertical-align: middle;"><polyline points="18 9 12 15 6 9"/></svg><br>
      Summer Launch — $500<br>
      Competitor — <span style="color: var(--r);">$0</span> <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2" style="vertical-align: middle;"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
    </div>
  </div>
</div>

---

### May Targets

<div style="display: flex; gap: 14px; margin-top: 20px;">
  <div style="flex: 1; background: var(--s); border: 1px solid var(--b); border-radius: 10px; padding: 20px; position: relative; overflow: hidden;">
    <div style="position: absolute; top: 0; left: 0; width: 100%; height: 2px; background: linear-gradient(90deg, var(--a), transparent);"></div>
    <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 12px;">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--m)" stroke-width="1.5"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 1 0 0 7h5a3.5 3.5 0 1 1 0 7H6"/></svg>
      <span style="font-family: 'Outfit'; font-weight: 600; font-size: 0.5em; color: var(--m); letter-spacing: 0.1em;">TARGET SPEND</span>
    </div>
    <div style="font-family: 'Outfit'; font-size: 2.2em; font-weight: 800; color: var(--a); line-height: 1;">$11.5K</div>
  </div>
  <div style="flex: 1; background: var(--s); border: 1px solid var(--b); border-radius: 10px; padding: 20px; position: relative; overflow: hidden;">
    <div style="position: absolute; top: 0; left: 0; width: 100%; height: 2px; background: linear-gradient(90deg, var(--g), transparent);"></div>
    <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 12px;">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--m)" stroke-width="1.5"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
      <span style="font-family: 'Outfit'; font-weight: 600; font-size: 0.5em; color: var(--m); letter-spacing: 0.1em;">TARGET REVENUE</span>
    </div>
    <div style="font-family: 'Outfit'; font-size: 2.2em; font-weight: 800; color: var(--g); line-height: 1;">$48K+</div>
  </div>
  <div style="flex: 1; background: var(--s); border: 1px solid var(--b); border-radius: 10px; padding: 20px; position: relative; overflow: hidden;">
    <div style="position: absolute; top: 0; left: 0; width: 100%; height: 2px; background: linear-gradient(90deg, var(--a), transparent);"></div>
    <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 12px;">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--m)" stroke-width="1.5"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>
      <span style="font-family: 'Outfit'; font-weight: 600; font-size: 0.5em; color: var(--m); letter-spacing: 0.1em;">TARGET ROAS</span>
    </div>
    <div style="font-family: 'Outfit'; font-size: 2.2em; font-weight: 800; color: var(--t); line-height: 1;">4.2x</div>
  </div>
  <div style="flex: 1; background: var(--s); border: 1px solid var(--b); border-radius: 10px; padding: 20px; position: relative; overflow: hidden;">
    <div style="position: absolute; top: 0; left: 0; width: 100%; height: 2px; background: linear-gradient(90deg, var(--a), transparent);"></div>
    <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 12px;">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--m)" stroke-width="1.5"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
      <span style="font-family: 'Outfit'; font-weight: 600; font-size: 0.5em; color: var(--m); letter-spacing: 0.1em;">TARGET CONV</span>
    </div>
    <div style="font-family: 'Outfit'; font-size: 2.2em; font-weight: 800; color: var(--t); line-height: 1;">750+</div>
  </div>
</div>

<div style="margin-top: 20px; font-weight: 200; font-size: 0.78em; color: var(--label); text-align: center;">
  +5% spend → +15% revenue. Efficiency from reallocation, not more money.
</div>

---

<!-- _class: lead -->
<!-- _header: '' -->
<!-- _paginate: false -->

![bg brightness:0.08](https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=1400)

<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="1.5"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>

# End of Report
