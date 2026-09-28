---
marp: true
theme: default
paginate: true
style: |
  @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap');

  :root {
    --orange: #ff6b1a;
    --orange-hover: #ff8c4a;
    --dark: #000000;
    --card: #0a0a0a;
    --border: #1a1a1a;
    --muted: #888;
    --light: #ffffff;
  }

  section {
    background: var(--dark);
    color: var(--light);
    font-family: 'Outfit', sans-serif;
    font-weight: 300;
    padding: 60px 80px;
    line-height: 1.6;
  }

  h1 {
    font-family: 'Outfit', sans-serif;
    font-weight: 900;
    font-size: 3.6em;
    color: var(--orange);
    letter-spacing: -0.02em;
    line-height: 1.1;
    margin-bottom: 0.2em;
  }

  h2 {
    font-family: 'Outfit', sans-serif;
    font-weight: 700;
    font-size: 2em;
    color: var(--light);
    margin-bottom: 0.4em;
  }

  h3 {
    font-family: 'Outfit', sans-serif;
    font-weight: 500;
    font-size: 0.85em;
    color: var(--orange);
    text-transform: uppercase;
    letter-spacing: 0.15em;
    margin-bottom: 0.1em;
  }

  strong { color: var(--orange); font-weight: 600; }

  blockquote {
    border-left: 3px solid var(--orange);
    padding: 16px 24px;
    background: var(--card);
    border-radius: 0 12px 12px 0;
    color: var(--muted);
    font-style: italic;
  }

  table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0 6px;
    font-size: 0.85em;
  }

  table th {
    background: var(--orange);
    color: var(--dark);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.8em;
    padding: 10px 20px;
    border: none;
  }

  table th:first-child { border-radius: 8px 0 0 8px; }
  table th:last-child { border-radius: 0 8px 8px 0; }

  table td {
    background: var(--card);
    padding: 12px 20px;
    border: none;
  }

  table td:first-child { border-radius: 8px 0 0 8px; }
  table td:last-child { border-radius: 0 8px 8px 0; }

  section.lead {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    text-align: center;
    background: radial-gradient(ellipse at 50% 80%, #1a0e05 0%, var(--dark) 70%);
  }

  section.lead h1 { font-size: 4.2em; }
  section.lead p { color: var(--muted); font-size: 1.05em; }

  .card-row {
    display: flex;
    gap: 24px;
    margin-top: 20px;
  }

  .card {
    flex: 1;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 28px 24px;
    text-align: center;
  }

  .card h4 {
    font-family: 'Outfit', sans-serif;
    font-weight: 700;
    font-size: 1.15em;
    color: var(--light);
    margin: 12px 0 6px;
  }

  .card p {
    color: var(--muted);
    font-size: 0.78em;
    line-height: 1.5;
    margin: 0;
  }

  .pill-row {
    display: flex;
    gap: 8px;
    justify-content: center;
    margin-top: 20px;
  }

  .pill {
    display: inline-block;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 5px 16px;
    font-size: 0.65em;
    color: var(--muted);
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  .divider {
    width: 60px;
    height: 3px;
    background: var(--orange);
    border-radius: 2px;
    margin: 16px auto 20px;
  }

  /* Animations */
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }
  @keyframes float {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-8px); }
  }
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
  @keyframes glow {
    0%, 100% { box-shadow: 0 0 8px #ff6b1a33; }
    50% { box-shadow: 0 0 24px #ff6b1a66; }
  }
  @keyframes slideIn {
    from { opacity: 0; transform: translateX(-20px); }
    to { opacity: 1; transform: translateX(0); }
  }
  @keyframes typing {
    from { width: 0; }
    to { width: 100%; }
  }
  @keyframes blink {
    0%, 100% { border-color: #ff6b1a; }
    50% { border-color: transparent; }
  }

  /* Glass card */
  .glass {
    background: rgba(255, 107, 26, 0.05);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 107, 26, 0.15);
    border-radius: 16px;
    padding: 24px;
  }

  /* Terminal */
  .terminal {
    background: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 12px;
    overflow: hidden;
    font-family: 'Courier New', monospace;
    font-size: 0.75em;
  }
  .terminal-bar {
    background: #111;
    padding: 8px 14px;
    display: flex;
    gap: 6px;
    align-items: center;
  }
  .terminal-dot {
    width: 10px; height: 10px; border-radius: 50%;
  }
  .terminal-body {
    padding: 16px 20px;
    line-height: 1.8;
  }
  .terminal-body .prompt { color: #ff6b1a; }
  .terminal-body .output { color: #888; }
  .terminal-body .success { color: #22c55e; }

  /* Browser mockup */
  .browser {
    background: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 12px;
    overflow: hidden;
  }
  .browser-bar {
    background: #111;
    padding: 10px 14px;
    display: flex;
    gap: 6px;
    align-items: center;
  }
  .browser-url {
    background: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 6px;
    padding: 4px 12px;
    color: #555;
    font-size: 0.75em;
    flex: 1;
    margin-left: 8px;
  }

  /* Chat bubble */
  .chat-bubble {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 16px 16px 16px 4px;
    padding: 14px 18px;
    margin: 6px 0;
    font-size: 0.85em;
    max-width: 75%;
  }
  .chat-bubble.agent {
    background: rgba(255, 107, 26, 0.08);
    border-color: rgba(255, 107, 26, 0.2);
    border-radius: 16px 16px 4px 16px;
    margin-left: auto;
  }
  .chat-meta {
    font-size: 0.65em;
    color: #555;
    margin-bottom: 4px;
  }
  .chat-bubble.agent .chat-meta { color: #ff6b1a88; text-align: right; }

  footer {
    font-family: 'Outfit', sans-serif;
    font-size: 0.6em;
    color: #333;
    letter-spacing: 0.12em;
  }

  section::after {
    font-family: 'Outfit', sans-serif;
    font-size: 0.7em;
    color: #333;
  }
footer: 'ANTIGRAVITY'
---

<!-- _class: lead -->

# The Agent Stack

<div class="divider"></div>

How to build AI agents that actually do work

<div class="pill-row">
  <span class="pill">AI Agents</span>
  <span class="pill">Automation</span>
  <span class="pill">2026</span>
</div>

---

### Chatbot vs Agent

## The difference isn't intelligence — it's **autonomy**

| | Chatbot | Agent |
|---|---|---|
| **Input** | You type everything | You give a goal |
| **Tools** | <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#555" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="8" y1="12" x2="16" y2="12"/></svg> None | <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ff6b35" stroke-width="2" stroke-linecap="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg> Files, APIs, browser, code |
| **Memory** | <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#555" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="8" y1="12" x2="16" y2="12"/></svg> Forgets next session | <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ff6b35" stroke-width="2" stroke-linecap="round"><path d="M12 2a7 7 0 0 1 7 7c0 2.38-1.19 4.47-3 5.74V17a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 0 1 7-7z"/><line x1="9" y1="21" x2="15" y2="21"/></svg> Remembers context |
| **Output** | Text reply | **Real work done** |

---

### The Framework

## Three layers. That's the whole stack.

<div class="card-row">
  <div class="card">
    <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="#ff6b35" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="10"/>
      <path d="M12 8v4l3 3"/>
      <circle cx="12" cy="12" r="3" fill="#ff6b35" opacity="0.2"/>
    </svg>
    <h4>Brain</h4>
    <p>The LLM that reasons. Picks the right tool, decides the next step.</p>
  </div>
  <div class="card">
    <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="#ff6b35" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
    </svg>
    <h4>Tools</h4>
    <p>What the agent can touch. Files, APIs, databases, browser. No tools = no action.</p>
  </div>
  <div class="card">
    <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="#ff6b35" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
      <line x1="8" y1="7" x2="16" y2="7"/>
      <line x1="8" y1="11" x2="13" y2="11"/>
    </svg>
    <h4>Memory</h4>
    <p>What survives between sessions. Context, preferences, past decisions.</p>
  </div>
</div>

> Get these three right and your agent goes from *toy* to **teammate**.

---

### Progress Bars

## How far along is your agent?

<div style="margin-top: 20px;">
  <div style="display: flex; justify-content: space-between; font-size: 0.75em; margin-bottom: 4px;">
    <span>Brain <span style="color: #ff6b1a;">— Claude 4 Opus</span></span>
    <span style="color: #888;">95%</span>
  </div>
  <div style="background: #0a0a0a; border-radius: 8px; height: 14px; border: 1px solid #1a1a1a; overflow: hidden;">
    <div style="background: linear-gradient(90deg, #ff6b1a, #ff8c4a); width: 95%; height: 100%; border-radius: 8px;"></div>
  </div>
</div>

<div style="margin-top: 16px;">
  <div style="display: flex; justify-content: space-between; font-size: 0.75em; margin-bottom: 4px;">
    <span>Tools <span style="color: #ff6b1a;">— 12 connected</span></span>
    <span style="color: #888;">70%</span>
  </div>
  <div style="background: #0a0a0a; border-radius: 8px; height: 14px; border: 1px solid #1a1a1a; overflow: hidden;">
    <div style="background: linear-gradient(90deg, #ff6b1a, #ff8c4a); width: 70%; height: 100%; border-radius: 8px;"></div>
  </div>
</div>

<div style="margin-top: 16px;">
  <div style="display: flex; justify-content: space-between; font-size: 0.75em; margin-bottom: 4px;">
    <span>Memory <span style="color: #ff6b1a;">— persistent store</span></span>
    <span style="color: #888;">40%</span>
  </div>
  <div style="background: #0a0a0a; border-radius: 8px; height: 14px; border: 1px solid #1a1a1a; overflow: hidden;">
    <div style="background: linear-gradient(90deg, #ff6b1a, #ff8c4a); width: 40%; height: 100%; border-radius: 8px;"></div>
  </div>
</div>

<div style="margin-top: 16px;">
  <div style="display: flex; justify-content: space-between; font-size: 0.75em; margin-bottom: 4px;">
    <span>Autonomy <span style="color: #ff6b1a;">— runs overnight</span></span>
    <span style="color: #888;">20%</span>
  </div>
  <div style="background: #0a0a0a; border-radius: 8px; height: 14px; border: 1px solid #1a1a1a; overflow: hidden;">
    <div style="background: linear-gradient(90deg, #ff6b1a, #ff8c4a); width: 20%; height: 100%; border-radius: 8px;"></div>
  </div>
</div>

---

### Highlights & Keyboard

## Make text pop with <mark style="background: #ff6b1a33; color: #ff8c4a; padding: 2px 8px; border-radius: 4px;">highlights</mark>

Use <mark style="background: #ff6b1a33; color: #ff8c4a; padding: 2px 8px; border-radius: 4px;">mark</mark> to draw attention to key concepts inline.

Keyboard shortcuts render as styled keys:

<div style="margin-top: 24px; font-size: 0.9em;">

<kbd style="background: #0a0a0a; border: 1px solid #333; border-radius: 6px; padding: 6px 14px; font-family: 'Outfit', sans-serif; font-size: 0.85em; color: #fff; box-shadow: 0 2px 0 #222;">Ctrl</kbd> + <kbd style="background: #0a0a0a; border: 1px solid #333; border-radius: 6px; padding: 6px 14px; font-family: 'Outfit', sans-serif; font-size: 0.85em; color: #fff; box-shadow: 0 2px 0 #222;">Shift</kbd> + <kbd style="background: #0a0a0a; border: 1px solid #ff6b1a; border-radius: 6px; padding: 6px 14px; font-family: 'Outfit', sans-serif; font-size: 0.85em; color: #ff6b1a; box-shadow: 0 2px 0 #ff6b1a55;">P</kbd> → Open command palette

<kbd style="background: #0a0a0a; border: 1px solid #333; border-radius: 6px; padding: 6px 14px; font-family: 'Outfit', sans-serif; font-size: 0.85em; color: #fff; box-shadow: 0 2px 0 #222; margin-top: 12px; display: inline-block;">Ctrl</kbd> + <kbd style="background: #0a0a0a; border: 1px solid #ff6b1a; border-radius: 6px; padding: 6px 14px; font-family: 'Outfit', sans-serif; font-size: 0.85em; color: #ff6b1a; box-shadow: 0 2px 0 #ff6b1a55;">L</kbd> → Ask Claude

</div>

---

### Collapsibles

## Expandable sections with `<details>`

<details style="background: #0a0a0a; border: 1px solid #1a1a1a; border-radius: 12px; padding: 16px 20px; margin-top: 12px;">
<summary style="color: #ff6b1a; font-weight: 600; cursor: pointer; font-size: 0.95em;">
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ff6b1a" stroke-width="2" style="vertical-align: middle; margin-right: 6px;"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
  What model should I use?
</summary>
<p style="color: #888; margin-top: 10px; font-size: 0.85em; line-height: 1.6;">Claude Opus 4 for complex reasoning. Sonnet 4 for speed. Haiku for bulk operations where cost matters more than depth.</p>
</details>

<details style="background: #0a0a0a; border: 1px solid #1a1a1a; border-radius: 12px; padding: 16px 20px; margin-top: 10px;">
<summary style="color: #ff6b1a; font-weight: 600; cursor: pointer; font-size: 0.95em;">
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ff6b1a" stroke-width="2" style="vertical-align: middle; margin-right: 6px;"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
  How much does it cost?
</summary>
<p style="color: #888; margin-top: 10px; font-size: 0.85em; line-height: 1.6;">Claude Code Max plan: $200/mo unlimited. Or API usage at ~$15/M input tokens for Opus.</p>
</details>

<details style="background: #0a0a0a; border: 1px solid #1a1a1a; border-radius: 12px; padding: 16px 20px; margin-top: 10px;">
<summary style="color: #ff6b1a; font-weight: 600; cursor: pointer; font-size: 0.95em;">
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ff6b1a" stroke-width="2" style="vertical-align: middle; margin-right: 6px;"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
  Can it run overnight?
</summary>
<p style="color: #888; margin-top: 10px; font-size: 0.85em; line-height: 1.6;">Yes. With cron triggers and session recovery, agents can run 24/7 with no human in the loop.</p>
</details>

---

### Stats Grid

## The numbers that matter

<div style="display: flex; gap: 20px; margin-top: 24px;">
  <div style="flex: 1; background: #0a0a0a; border: 1px solid #1a1a1a; border-radius: 16px; padding: 28px 20px; text-align: center;">
    <div style="font-size: 2.8em; font-weight: 800; color: #ff6b1a; line-height: 1;">25+</div>
    <div style="color: #888; font-size: 0.75em; margin-top: 8px; text-transform: uppercase; letter-spacing: 0.1em;">Integrations</div>
  </div>
  <div style="flex: 1; background: #0a0a0a; border: 1px solid #1a1a1a; border-radius: 16px; padding: 28px 20px; text-align: center;">
    <div style="font-size: 2.8em; font-weight: 800; color: #ff6b1a; line-height: 1;">1M</div>
    <div style="color: #888; font-size: 0.75em; margin-top: 8px; text-transform: uppercase; letter-spacing: 0.1em;">Context Window</div>
  </div>
  <div style="flex: 1; background: #0a0a0a; border: 1px solid #1a1a1a; border-radius: 16px; padding: 28px 20px; text-align: center;">
    <div style="font-size: 2.8em; font-weight: 800; color: #ff6b1a; line-height: 1;">24/7</div>
    <div style="color: #888; font-size: 0.75em; margin-top: 8px; text-transform: uppercase; letter-spacing: 0.1em;">Uptime</div>
  </div>
  <div style="flex: 1; background: #0a0a0a; border: 1px solid #1a1a1a; border-radius: 16px; padding: 28px 20px; text-align: center;">
    <div style="font-size: 2.8em; font-weight: 800; color: #ff6b1a; line-height: 1;">6</div>
    <div style="color: #888; font-size: 0.75em; margin-top: 8px; text-transform: uppercase; letter-spacing: 0.1em;">Agent Team</div>
  </div>
</div>

---

### Timeline

## How we got here

<div style="margin-top: 20px; position: relative; padding-left: 28px; border-left: 2px solid #1a1a1a;">
  <div style="margin-bottom: 24px; position: relative;">
    <div style="position: absolute; left: -35px; top: 2px; width: 12px; height: 12px; background: #ff6b1a; border-radius: 50%; border: 2px solid #000;"></div>
    <div style="font-weight: 600; color: #ff6b1a; font-size: 0.8em; letter-spacing: 0.08em;">2024</div>
    <div style="color: #fff; font-size: 0.95em; margin-top: 2px;">ChatGPT wrappers everywhere. Copy-paste workflows.</div>
  </div>
  <div style="margin-bottom: 24px; position: relative;">
    <div style="position: absolute; left: -35px; top: 2px; width: 12px; height: 12px; background: #ff6b1a; border-radius: 50%; border: 2px solid #000;"></div>
    <div style="font-weight: 600; color: #ff6b1a; font-size: 0.8em; letter-spacing: 0.08em;">2025</div>
    <div style="color: #fff; font-size: 0.95em; margin-top: 2px;">Claude Code ships. Agents get tools, memory, autonomy.</div>
  </div>
  <div style="margin-bottom: 24px; position: relative;">
    <div style="position: absolute; left: -35px; top: 2px; width: 12px; height: 12px; background: #ff6b1a; border-radius: 50%; border: 2px solid #000;"></div>
    <div style="font-weight: 600; color: #ff6b1a; font-size: 0.8em; letter-spacing: 0.08em;">2026</div>
    <div style="color: #fff; font-size: 0.95em; margin-top: 2px;">Multi-agent teams running 24/7. The agent <em>is</em> the product.</div>
  </div>
  <div style="position: relative;">
    <div style="position: absolute; left: -35px; top: 2px; width: 12px; height: 12px; background: #ff8c4a; border-radius: 50%; border: 2px solid #ff6b1a; box-shadow: 0 0 8px #ff6b1a55;"></div>
    <div style="font-weight: 600; color: #ff8c4a; font-size: 0.8em; letter-spacing: 0.08em;">NOW</div>
    <div style="color: #fff; font-size: 0.95em; margin-top: 2px;"><strong>You're here.</strong> The best time to start building.</div>
  </div>
</div>

---

### Definition List

## Key terms you'll need

<dl style="margin-top: 16px;">
  <dt style="color: #ff6b1a; font-weight: 600; font-size: 1em; margin-top: 16px;">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ff6b1a" stroke-width="2" style="vertical-align: middle; margin-right: 6px;"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
    MCP (Model Context Protocol)
  </dt>
  <dd style="color: #888; font-size: 0.85em; margin-left: 24px; margin-top: 4px; border-left: 2px solid #1a1a1a; padding-left: 12px;">A standard for connecting AI models to external tools and data sources. Think USB for AI.</dd>

  <dt style="color: #ff6b1a; font-weight: 600; font-size: 1em; margin-top: 16px;">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ff6b1a" stroke-width="2" style="vertical-align: middle; margin-right: 6px;"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
    Claude Code
  </dt>
  <dd style="color: #888; font-size: 0.85em; margin-left: 24px; margin-top: 4px; border-left: 2px solid #1a1a1a; padding-left: 12px;">Anthropic's CLI agent. Reads files, writes code, runs commands, manages projects. Your AI teammate in the terminal.</dd>

  <dt style="color: #ff6b1a; font-weight: 600; font-size: 1em; margin-top: 16px;">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ff6b1a" stroke-width="2" style="vertical-align: middle; margin-right: 6px;"><circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/></svg>
    Cron Trigger
  </dt>
  <dd style="color: #888; font-size: 0.85em; margin-left: 24px; margin-top: 4px; border-left: 2px solid #1a1a1a; padding-left: 12px;">A scheduled task that runs your agent at set intervals — daily briefings, weekly reports, overnight builds. No human needed.</dd>
</dl>

---

### Terminal Mockup

## What it actually looks like

<div class="terminal">
  <div class="terminal-bar">
    <div class="terminal-dot" style="background: #ff5f57;"></div>
    <div class="terminal-dot" style="background: #febc2e;"></div>
    <div class="terminal-dot" style="background: #28c840;"></div>
    <span style="color: #555; font-size: 0.8em; margin-left: 8px;">~/projects/my-agent</span>
  </div>
  <div class="terminal-body">
    <span class="prompt">$</span> claude "deploy the new landing page"<br>
    <span class="output">● Reading project structure...</span><br>
    <span class="output">● Building with Vite...</span><br>
    <span class="output">● Running tests — 14/14 passed</span><br>
    <span class="output">● Pushing to main...</span><br>
    <span class="output">● Deploying to Vercel...</span><br>
    <span class="success">✓ Live at https://mysite.vercel.app</span><br>
    <span class="prompt">$</span> <span style="border-right: 2px solid #ff6b1a; animation: blink 1s infinite; padding-right: 2px;">_</span>
  </div>
</div>

---

### Chat Interface

## Agents talk back

<div style="max-width: 520px; margin: 16px auto 0;">
  <div class="chat-bubble">
    <div class="chat-meta">You · 9:41 AM</div>
    Can you check if the API is still rate limiting us?
  </div>
  <div class="chat-bubble agent">
    <div class="chat-meta">Agent · 9:41 AM</div>
    Checked the last 500 requests. We're hitting 429s on the <span style="color: #ff6b1a;">/v2/generate</span> endpoint — 12% failure rate since 8am. The retry logic backs off but the queue is growing. Want me to switch to the fallback provider?
  </div>
  <div class="chat-bubble">
    <div class="chat-meta">You · 9:42 AM</div>
    Yeah do it. And log the switch.
  </div>
  <div class="chat-bubble agent">
    <div class="chat-meta">Agent · 9:42 AM</div>
    <span style="color: #22c55e;">✓</span> Switched to fallback. Logged to <span style="color: #ff6b1a;">ops/provider-switches.md</span>. Queue clearing now — ETA 3 min.
  </div>
</div>

---

### Browser Mockup

## Your agent has a dashboard

<div class="browser">
  <div class="browser-bar">
    <div class="terminal-dot" style="background: #ff5f57;"></div>
    <div class="terminal-dot" style="background: #febc2e;"></div>
    <div class="terminal-dot" style="background: #28c840;"></div>
    <div class="browser-url">localhost:5000/dashboard</div>
  </div>
  <div style="padding: 24px; display: flex; gap: 16px;">
    <div style="flex: 1; background: #111; border-radius: 10px; padding: 16px; border: 1px solid #1a1a1a;">
      <div style="font-size: 0.65em; color: #888; text-transform: uppercase; letter-spacing: 0.1em;">Tasks Today</div>
      <div style="font-size: 2em; font-weight: 800; color: #22c55e; margin-top: 4px;">12</div>
      <div style="font-size: 0.7em; color: #555; margin-top: 4px;">↑ 3 from yesterday</div>
    </div>
    <div style="flex: 1; background: #111; border-radius: 10px; padding: 16px; border: 1px solid #1a1a1a;">
      <div style="font-size: 0.65em; color: #888; text-transform: uppercase; letter-spacing: 0.1em;">Agents Online</div>
      <div style="font-size: 2em; font-weight: 800; color: #ff6b1a; margin-top: 4px;">6/6</div>
      <div style="font-size: 0.7em; color: #22c55e; margin-top: 4px;">● All healthy</div>
    </div>
    <div style="flex: 1; background: #111; border-radius: 10px; padding: 16px; border: 1px solid #1a1a1a;">
      <div style="font-size: 0.65em; color: #888; text-transform: uppercase; letter-spacing: 0.1em;">MRR</div>
      <div style="font-size: 2em; font-weight: 800; color: #ff6b1a; margin-top: 4px;">$47K</div>
      <div style="font-size: 0.7em; color: #22c55e; margin-top: 4px;">↑ 8% this week</div>
    </div>
  </div>
</div>

---

### Circular Progress

## Agent readiness score

<div style="display: flex; gap: 40px; justify-content: center; margin-top: 24px;">
  <div style="text-align: center;">
    <svg width="120" height="120" viewBox="0 0 120 120">
      <circle cx="60" cy="60" r="50" fill="none" stroke="#1a1a1a" stroke-width="8"/>
      <circle cx="60" cy="60" r="50" fill="none" stroke="#ff6b1a" stroke-width="8" stroke-dasharray="283" stroke-dashoffset="28" stroke-linecap="round" transform="rotate(-90 60 60)"/>
      <text x="60" y="58" text-anchor="middle" fill="#fff" font-family="Outfit" font-size="28" font-weight="700">90</text>
      <text x="60" y="74" text-anchor="middle" fill="#888" font-family="Outfit" font-size="11">BRAIN</text>
    </svg>
  </div>
  <div style="text-align: center;">
    <svg width="120" height="120" viewBox="0 0 120 120">
      <circle cx="60" cy="60" r="50" fill="none" stroke="#1a1a1a" stroke-width="8"/>
      <circle cx="60" cy="60" r="50" fill="none" stroke="#ff6b1a" stroke-width="8" stroke-dasharray="283" stroke-dashoffset="85" stroke-linecap="round" transform="rotate(-90 60 60)"/>
      <text x="60" y="58" text-anchor="middle" fill="#fff" font-family="Outfit" font-size="28" font-weight="700">70</text>
      <text x="60" y="74" text-anchor="middle" fill="#888" font-family="Outfit" font-size="11">TOOLS</text>
    </svg>
  </div>
  <div style="text-align: center;">
    <svg width="120" height="120" viewBox="0 0 120 120">
      <circle cx="60" cy="60" r="50" fill="none" stroke="#1a1a1a" stroke-width="8"/>
      <circle cx="60" cy="60" r="50" fill="none" stroke="#ff6b1a" stroke-width="8" stroke-dasharray="283" stroke-dashoffset="170" stroke-linecap="round" transform="rotate(-90 60 60)"/>
      <text x="60" y="58" text-anchor="middle" fill="#fff" font-family="Outfit" font-size="28" font-weight="700">40</text>
      <text x="60" y="74" text-anchor="middle" fill="#888" font-family="Outfit" font-size="11">MEMORY</text>
    </svg>
  </div>
  <div style="text-align: center;">
    <svg width="120" height="120" viewBox="0 0 120 120">
      <circle cx="60" cy="60" r="50" fill="none" stroke="#1a1a1a" stroke-width="8"/>
      <circle cx="60" cy="60" r="50" fill="none" stroke="#22c55e" stroke-width="8" stroke-dasharray="283" stroke-dashoffset="57" stroke-linecap="round" transform="rotate(-90 60 60)"/>
      <text x="60" y="58" text-anchor="middle" fill="#fff" font-family="Outfit" font-size="28" font-weight="700">80</text>
      <text x="60" y="74" text-anchor="middle" fill="#888" font-family="Outfit" font-size="11">OVERALL</text>
    </svg>
  </div>
</div>

---

### Glassmorphism

## The new aesthetic

<div style="display: flex; gap: 20px; margin-top: 20px;">
  <div class="glass" style="flex: 1; animation: float 4s ease-in-out infinite;">
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#ff6b1a" stroke-width="1.5"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
    <h4 style="margin: 10px 0 4px; font-weight: 600;">Fast</h4>
    <p style="color: #888; font-size: 0.78em; margin: 0;">Opus-level reasoning at sub-second response times for most tasks.</p>
  </div>
  <div class="glass" style="flex: 1; animation: float 4s ease-in-out 0.5s infinite;">
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#ff6b1a" stroke-width="1.5"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
    <h4 style="margin: 10px 0 4px; font-weight: 600;">Secure</h4>
    <p style="color: #888; font-size: 0.78em; margin: 0;">Local-first. Your data stays on your machine. No cloud required.</p>
  </div>
  <div class="glass" style="flex: 1; animation: float 4s ease-in-out 1s infinite;">
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#ff6b1a" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
    <h4 style="margin: 10px 0 4px; font-weight: 600;">Connected</h4>
    <p style="color: #888; font-size: 0.78em; margin: 0;">25+ integrations. Telegram, Slack, GitHub, Gmail, Calendar — all native.</p>
  </div>
</div>

> Glass cards float with CSS animation — no JavaScript needed.

---

### Photo Backgrounds

## Unsplash images work natively

![bg right:45% brightness:0.4](https://images.unsplash.com/photo-1550751827-4bd374c3f58b?w=800)

MARP supports remote images as backgrounds.

- `![bg](url)` — full bleed
- `![bg right:45%](url)` — split layout
- `![bg left:40%](url)` — image on left
- `brightness`, `blur`, `opacity` filters
- Multiple `![bg]` for side-by-side

> This photo is pulled live from Unsplash.

---

### Split Image Layout

![bg left:50% blur:2px brightness:0.3](https://images.unsplash.com/photo-1677442136019-21780ecad995?w=800)

## AI is eating the world

And the people who know how to **direct it** will eat with it.

<div style="margin-top: 20px;">
  <div style="display: flex; align-items: center; gap: 12px; margin: 10px 0;">
    <div style="width: 8px; height: 8px; background: #ff6b1a; border-radius: 50;"></div>
    <span style="font-size: 0.85em;">Creators who use agents ship 10x faster</span>
  </div>
  <div style="display: flex; align-items: center; gap: 12px; margin: 10px 0;">
    <div style="width: 8px; height: 8px; background: #ff6b1a; border-radius: 50;"></div>
    <span style="font-size: 0.85em;">Solo founders are building what teams couldn't</span>
  </div>
  <div style="display: flex; align-items: center; gap: 12px; margin: 10px 0;">
    <div style="width: 8px; height: 8px; background: #ff6b1a; border-radius: 50;"></div>
    <span style="font-size: 0.85em;">The leverage gap is widening every month</span>
  </div>
</div>

---

### Animated Glow Cards

## Choose your path

<div style="display: flex; gap: 20px; margin-top: 20px;">
  <div style="flex: 1; background: #0a0a0a; border: 1px solid #ff6b1a33; border-radius: 16px; padding: 24px; animation: glow 3s ease-in-out infinite; text-align: center;">
    <div style="font-size: 2.4em; margin-bottom: 8px;">🔰</div>
    <h4 style="font-weight: 700; margin: 0 0 6px; color: #fff;">Beginner</h4>
    <p style="color: #888; font-size: 0.75em; margin: 0 0 12px;">One agent, one task.<br>Get your first win.</p>
    <div style="background: #ff6b1a; color: #000; font-weight: 600; padding: 8px 20px; border-radius: 8px; font-size: 0.8em; display: inline-block;">Start here</div>
  </div>
  <div style="flex: 1; background: #0a0a0a; border: 1px solid #ff6b1a55; border-radius: 16px; padding: 24px; animation: glow 3s ease-in-out 1s infinite; text-align: center;">
    <div style="font-size: 2.4em; margin-bottom: 8px;">⚡</div>
    <h4 style="font-weight: 700; margin: 0 0 6px; color: #fff;">Builder</h4>
    <p style="color: #888; font-size: 0.75em; margin: 0 0 12px;">Multi-tool agents.<br>Memory + crons.</p>
    <div style="background: #ff6b1a22; color: #ff6b1a; font-weight: 600; padding: 8px 20px; border-radius: 8px; font-size: 0.8em; display: inline-block; border: 1px solid #ff6b1a55;">Level up</div>
  </div>
  <div style="flex: 1; background: #0a0a0a; border: 1px solid #ff6b1a77; border-radius: 16px; padding: 24px; animation: glow 3s ease-in-out 2s infinite; text-align: center;">
    <div style="font-size: 2.4em; margin-bottom: 8px;">🏗️</div>
    <h4 style="font-weight: 700; margin: 0 0 6px; color: #fff;">Architect</h4>
    <p style="color: #888; font-size: 0.75em; margin: 0 0 12px;">Agent teams. 24/7 ops.<br>The whole stack.</p>
    <div style="background: #ff6b1a22; color: #ff6b1a; font-weight: 600; padding: 8px 20px; border-radius: 8px; font-size: 0.8em; display: inline-block; border: 1px solid #ff6b1a55;">Go deep</div>
  </div>
</div>

---

### Code Showcase

## Syntax highlighting is built in

```javascript
// Your first agent — 4 lines of code
import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic();
const response = await client.messages.create({
  model: "claude-opus-4-6-20250414",
  max_tokens: 1024,
  tools: [readFile, writeFile, runCommand],
  messages: [{ role: "user", content: "Deploy the app" }],
});
```

> MARP uses **highlight.js** under the hood — supports 190+ languages.

---

### Flowchart

## How agents think

<div style="display: flex; align-items: center; justify-content: center; gap: 0; margin-top: 30px;">
  <div style="background: #0a0a0a; border: 2px solid #ff6b1a; border-radius: 12px; padding: 14px 20px; text-align: center; min-width: 100px;">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#ff6b1a" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
    <div style="font-size: 0.75em; font-weight: 600; margin-top: 4px;">PROMPT</div>
  </div>
  <svg width="40" height="20" viewBox="0 0 40 20"><line x1="0" y1="10" x2="30" y2="10" stroke="#333" stroke-width="2"/><polygon points="30,5 40,10 30,15" fill="#ff6b1a"/></svg>
  <div style="background: #0a0a0a; border: 2px solid #ff6b1a44; border-radius: 12px; padding: 14px 20px; text-align: center; min-width: 100px;">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#ff6b1a" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 8v4l3 3"/></svg>
    <div style="font-size: 0.75em; font-weight: 600; margin-top: 4px;">REASON</div>
  </div>
  <svg width="40" height="20" viewBox="0 0 40 20"><line x1="0" y1="10" x2="30" y2="10" stroke="#333" stroke-width="2"/><polygon points="30,5 40,10 30,15" fill="#ff6b1a"/></svg>
  <div style="background: #0a0a0a; border: 2px solid #ff6b1a44; border-radius: 12px; padding: 14px 20px; text-align: center; min-width: 100px;">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#ff6b1a" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
    <div style="font-size: 0.75em; font-weight: 600; margin-top: 4px;">ACT</div>
  </div>
  <svg width="40" height="20" viewBox="0 0 40 20"><line x1="0" y1="10" x2="30" y2="10" stroke="#333" stroke-width="2"/><polygon points="30,5 40,10 30,15" fill="#ff6b1a"/></svg>
  <div style="background: #0a0a0a; border: 2px solid #ff6b1a44; border-radius: 12px; padding: 14px 20px; text-align: center; min-width: 100px;">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#ff6b1a" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
    <div style="font-size: 0.75em; font-weight: 600; margin-top: 4px;">OBSERVE</div>
  </div>
  <svg width="40" height="20" viewBox="0 0 40 20"><line x1="0" y1="10" x2="30" y2="10" stroke="#333" stroke-width="2"/><polygon points="30,5 40,10 30,15" fill="#22c55e"/></svg>
  <div style="background: #0a0a0a; border: 2px solid #22c55e; border-radius: 12px; padding: 14px 20px; text-align: center; min-width: 100px;">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
    <div style="font-size: 0.75em; font-weight: 600; color: #22c55e; margin-top: 4px;">DONE</div>
  </div>
</div>

<div style="text-align: center; margin-top: 20px; color: #555; font-size: 0.8em;">Prompt → Reason → Act → Observe → repeat until done</div>

---

### Before & After

## The same task, two realities

<div style="display: flex; gap: 2px; margin-top: 20px;">
  <div style="flex: 1; background: #0a0a0a; border-radius: 12px 0 0 12px; padding: 24px; border: 1px solid #1a1a1a;">
    <div style="color: #e00000; font-weight: 600; font-size: 0.8em; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 12px;">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#e00000" stroke-width="2" style="vertical-align: middle; margin-right: 4px;"><circle cx="12" cy="12" r="10"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
      Without agents
    </div>
    <div style="font-size: 0.82em; color: #888; line-height: 1.8;">
      ⬜ Research the topic (45 min)<br>
      ⬜ Draft the script (2 hrs)<br>
      ⬜ Create thumbnail (1 hr)<br>
      ⬜ Edit the video (3 hrs)<br>
      ⬜ Write the description (20 min)<br>
      ⬜ Schedule the post (10 min)<br>
      <div style="margin-top: 12px; color: #e00000; font-weight: 600;">Total: ~7 hours</div>
    </div>
  </div>
  <div style="flex: 1; background: #0a0a0a; border-radius: 0 12px 12px 0; padding: 24px; border: 1px solid #ff6b1a33;">
    <div style="color: #22c55e; font-weight: 600; font-size: 0.8em; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 12px;">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2" style="vertical-align: middle; margin-right: 4px;"><circle cx="12" cy="12" r="10"/><polyline points="8 12 11 15 16 9"/></svg>
      With agents
    </div>
    <div style="font-size: 0.82em; color: #888; line-height: 1.8;">
      ✅ Research + draft (agent, 10 min)<br>
      ✅ Thumbnail generated (agent, 2 min)<br>
      ✅ Auto-cut + XML (agent, 5 min)<br>
      ⬜ You review + record (1 hr)<br>
      ✅ Description + schedule (agent, 1 min)<br>
      <br>
      <div style="margin-top: 12px; color: #22c55e; font-weight: 600;">Total: ~1.5 hours (you: 1 hr)</div>
    </div>
  </div>
</div>

---

<!-- _class: lead -->

# Start building.

<div class="divider"></div>

Pick one task. Give your agent tools. Watch it run.

<div class="pill-row">
  <span class="pill">antigravity.so</span>
  <span class="pill">@robonuggets</span>
</div>
