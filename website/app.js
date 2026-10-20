/**
 * DUME Studio — Deterministic Unit-Record Memory Engine
 * Client-side interactive engine: Live Simulator, Odometer Calculator, Gallery Lightbox
 */

(function () {
  'use strict';

  // --- TOAST NOTIFICATIONS ---
  const toast = document.getElementById('toast-notice');
  let toastTimer = null;

  function showToast(message) {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast.classList.remove('show');
    }, 2400);
  }

  // --- CLIPBOARD COPYING ---
  function setupClipboard() {
    // Hero Install button
    const copyInstallBtn = document.getElementById('btn-copy-install');
    if (copyInstallBtn) {
      copyInstallBtn.addEventListener('click', () => {
        const text = copyInstallBtn.getAttribute('data-copy') || 'pip install dumedb';
        navigator.clipboard.writeText(text).then(() => {
          showToast('✓ Copied to clipboard: ' + text);
        });
      });
    }

    // Code Tab Copy buttons
    document.querySelectorAll('.copy-code-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const targetId = btn.getAttribute('data-target');
        const targetEl = document.getElementById(targetId);
        if (targetEl) {
          const text = targetEl.innerText.trim();
          navigator.clipboard.writeText(text).then(() => {
            showToast('✓ Code snippet copied to clipboard!');
          });
        }
      });
    });
  }

  // --- INTERACTIVE TERMINAL SIMULATOR ---
  const termOutput = document.getElementById('term-output');
  const termForm = document.getElementById('terminal-form');
  const termInput = document.getElementById('terminal-input');
  const termShell = document.getElementById('studio-terminal');
  const btnClear = document.getElementById('btn-clear-term');
  const btnScanlines = document.getElementById('btn-scanlines-toggle');

  function appendTermLine(content, className = '') {
    if (!termOutput) return;
    const line = document.createElement('div');
    line.className = 'term-line ' + className;
    line.innerHTML = content;
    termOutput.appendChild(line);
    termOutput.scrollTop = termOutput.scrollHeight;
  }

  function handleCommand(rawCmd) {
    const cmd = rawCmd.trim();
    if (!cmd) return;

    appendTermLine('<span class="term-prompt">SENTINEL@DUMEDB:~$</span> ' + escapeHtml(cmd), 'cmd');

    const lower = cmd.toLowerCase().replace(/['"]/g, '').trim();

    if (lower === 'box is the game' || lower === 'wake' || lower === 'cabinet_wake') {
      setTimeout(() => {
        appendTermLine('[*] EXECUTING CABINET_WAKE HANDSHAKE PROTOCOL...', 'resp-wake');
        appendTermLine('[*] Codeword Validated: <span class="highlight">"box is the game"</span>', 'resp-wake');
        appendTermLine('----------------------------------------------------', 'sys');
        appendTermLine('🗄️ <strong>THE CABINET ORIENTATION (ZERO-TURN ORIENT)</strong>', 'resp-header');
        appendTermLine('• Operator: <strong>MadBrad</strong>', 'resp-wake');
        appendTermLine('• AI Collaborator: <strong>AG / Sentinel Harness</strong>', 'resp-wake');
        appendTermLine('• Mode: <strong>Sentinel Active</strong>', 'resp-wake');
        appendTermLine('• Next Move: Clean database on 8095 to fresh empty generic version whenever ready.', 'resp-wake');
        appendTermLine('----------------------------------------------------', 'sys');
        appendTermLine('⚡ <strong>DUMEDB HARDWARE STATUS</strong>', 'resp-header');
        appendTermLine('• Active Registers: <strong>112 Immutable Entries</strong>', 'resp-wake');
        appendTermLine('• KV-Cache Overhead: <strong>~220 tokens (0.2%)</strong>', 'resp-wake');
        appendTermLine('• Clean Runway: <strong>99.8% (~119,780 tok)</strong>', 'resp-wake');
        appendTermLine('• Execution Latency: <strong>0.18s (Zero filesystem traversal)</strong>', 'resp-wake');
        appendTermLine('[✓] System aligned. Status block cached.', 'resp-wake');
      }, 150);
    } else if (lower === 'dume.odometer' || lower === 'odometer') {
      setTimeout(() => {
        appendTermLine('--- REAL MATHEMATICAL CONTEXT ODOMETER ---', 'sys');
        appendTermLine('Transcript Audit: transcript.jsonl (Direct post-compaction measurement)', 'sys');
        appendTermLine('Epoch: 2 | Active Steps: 4', 'sys');
        appendTermLine('Active Context Footprint: <strong>767 / ~120,000 tokens (0.6%)</strong>', 'resp-wake');
        appendTermLine('Clean Runway Remaining: <strong>~119,233 tokens</strong>', 'resp-wake');
        appendTermLine('Last Turn Delta: +1,864 tokens (📥 1,481 in | 📤 383 out)', 'sys');
        appendTermLine('Zone: 🟢 Nominal (Safe buffer &gt; 75% limit)', 'resp-wake');
        appendTermLine('📊 <strong>Context Odometer (Real Math)</strong>: [░░░░░░░░░░] 0.6% (767 / ~120,000 tok) | Runway: ~119k tok', 'odometer-box');
      }, 120);
    } else if (lower === 'dume.status' || lower === 'status') {
      setTimeout(() => {
        appendTermLine('[STORAGE ENGINE] LMDB MMap Storage Active: <code>./data/dumedb.mdb</code>', 'sys');
        appendTermLine('[WORKSPACE] Active Workspace: <code>MadBrad-AG-01</code> (Tag: <code>v1.0-working-freeze</code>)', 'sys');
        appendTermLine('[PORT 8095] HTTP API & Inspector WebSocket: LISTENING', 'resp-wake');
        appendTermLine('[SCHEMAS] Loaded: <code>incident_rca</code>, <code>adr_record</code>, <code>error_fingerprint</code>, <code>unit_record</code>', 'sys');
      }, 100);
    } else if (lower === 'dume.registers' || lower === 'registers' || lower === 'list registers') {
      setTimeout(() => {
        appendTermLine('[REGISTERS] Sample of 112 Active Immutable Keys:', 'resp-header');
        const sampleRegisters = [
          { key: "operator_alias", val: "AG", type: "string" },
          { key: "session_handshake", val: "RP_FINALIZED", type: "enum" },
          { key: "repo_tag", val: "v1.0-working-freeze", type: "git_ref" },
          { key: "adr_003", val: "Zero-Token Vector Cache Bypass", type: "adr" },
          { key: "inc_4091", val: "LMDB Lock Contention Resolution", type: "rca" }
        ];
        appendTermLine(JSON.stringify(sampleRegisters, null, 2), 'json');
      }, 120);
    } else if (lower === 'dume.compare' || lower === 'compare') {
      setTimeout(() => {
        appendTermLine('=== BENCHMARK: REPLAY BLOAT vs DUMEDB REGISTER MEMORY ===', 'resp-header');
        appendTermLine('Traditional Chat History Replay: 85,000+ tokens (~71% context eaten, $1.40/wake)', 'term-line danger');
        appendTermLine('DUMEdb Unit-Record Wake: 220 tokens (~0.2% context eaten, $0.0003/wake)', 'term-line resp-wake');
        appendTermLine('Efficiency Gain: <strong>99.7% reduction in prompt bloat. Zero amnesia.</strong>', 'odometer-box');
      }, 150);
    } else if (lower === 'clear') {
      if (termOutput) termOutput.innerHTML = '';
    } else if (lower === 'help') {
      appendTermLine('AVAILABLE COMMANDS:', 'resp-header');
      appendTermLine('• <code>box is the game</code> — Execute zero-turn wake handshake', 'sys');
      appendTermLine('• <code>dume.odometer</code> — Real mathematical context audit on disk', 'sys');
      appendTermLine('• <code>dume.status</code> — Hardware & storage engine telemetry', 'sys');
      appendTermLine('• <code>dume.registers</code> — List active unit-record registers', 'sys');
      appendTermLine('• <code>dume.compare</code> — Benchmark against vector chat replay', 'sys');
      appendTermLine('• <code>clear</code> — Clear console buffer', 'sys');
    } else {
      appendTermLine(`Command not recognized: "${escapeHtml(cmd)}". Try typing <span class="highlight">"box is the game"</span> or <span class="highlight">"help"</span>.`, 'prompt-help');
    }
  }

  function escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function setupTerminal() {
    if (termForm && termInput) {
      termForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const cmd = termInput.value;
        termInput.value = '';
        handleCommand(cmd);
      });
    }

    // Preset pills
    document.querySelectorAll('.term-pill-btn').forEach(pill => {
      pill.addEventListener('click', () => {
        const cmd = pill.getAttribute('data-cmd');
        if (cmd) {
          handleCommand(cmd);
        }
      });
    });

    // Clear Button
    if (btnClear && termOutput) {
      btnClear.addEventListener('click', () => {
        termOutput.innerHTML = '<div class="term-line sys">[CLEARED] Console ready. Type "box is the game" to wake.</div>';
      });
    }

    // Scanlines Toggle
    if (btnScanlines && termShell) {
      btnScanlines.addEventListener('click', () => {
        termShell.classList.toggle('crt');
      });
    }
  }

  // --- CONTEXT RUNWAY CALCULATOR (REAL MATH) ---
  function setupOdometerCalculator() {
    const sliderTurns = document.getElementById('slider-turns');
    const sliderCeiling = document.getElementById('slider-ceiling');
    const valTurns = document.getElementById('val-turns');
    const valCeiling = document.getElementById('val-ceiling');

    const barTrad = document.getElementById('gauge-bar-trad');
    const valTradTok = document.getElementById('val-trad-tok');
    const valTradPct = document.getElementById('val-trad-pct');
    const valTradStatus = document.getElementById('val-trad-status');

    const barDume = document.getElementById('gauge-bar-dume');
    const valDumeTok = document.getElementById('val-dume-tok');
    const valDumePct = document.getElementById('val-dume-pct');
    const valDumeRunway = document.getElementById('val-dume-runway');
    const sampleString = document.getElementById('sample-odometer-string');
    const zoneBadge = document.getElementById('calc-zone-badge');
    const zoneText = document.getElementById('calc-zone-text');

    function updateCalculations() {
      if (!sliderTurns || !sliderCeiling) return;

      const turns = parseInt(sliderTurns.value, 10);
      const ceiling = parseInt(sliderCeiling.value, 10);

      valTurns.textContent = `${turns} Turns`;
      valCeiling.textContent = `${ceiling.toLocaleString()} tok`;

      // Traditional Replay: ~7,800 tokens accumulated per turn of chat/history
      const tradTokens = Math.min(ceiling, turns * 7800);
      const tradPct = Math.min(100, (tradTokens / ceiling) * 100).toFixed(1);

      // DUMEdb: 220 baseline wake + only ~200 tokens delta per turn (unit records only)
      const dumeTokens = Math.min(ceiling, 220 + (turns * 210));
      const dumePct = ((dumeTokens / ceiling) * 100).toFixed(1);
      const runwayTokens = Math.max(0, ceiling - dumeTokens);

      if (barTrad) barTrad.style.width = `${tradPct}%`;
      if (valTradTok) valTradTok.textContent = tradTokens.toLocaleString();
      if (valTradPct) valTradPct.textContent = `${tradPct}%`;

      if (tradPct >= 75) {
        if (valTradStatus) {
          valTradStatus.textContent = 'CRITICAL CHOKE (Compaction Imminent)';
          valTradStatus.className = 'danger';
        }
      } else if (tradPct >= 50) {
        if (valTradStatus) {
          valTradStatus.textContent = 'HIGH BLOAT (Latency Spikes)';
          valTradStatus.className = 'warning';
        }
      } else {
        if (valTradStatus) {
          valTradStatus.textContent = 'GROWING ACCUMULATION';
          valTradStatus.className = '';
        }
      }

      if (barDume) barDume.style.width = `${Math.max(1.5, dumePct)}%`;
      if (valDumeTok) valDumeTok.textContent = dumeTokens.toLocaleString();
      if (valDumePct) valDumePct.textContent = `${dumePct}%`;
      if (valDumeRunway) valDumeRunway.textContent = `~${runwayTokens.toLocaleString()} tokens`;

      // Generate visual meter bar
      const filledBlocks = Math.min(10, Math.floor((dumeTokens / ceiling) * 10));
      const meterBar = '█'.repeat(filledBlocks) + '░'.repeat(10 - filledBlocks);

      if (sampleString) {
        sampleString.textContent = `---
📊 **Context Odometer (Real Math)**: [${meterBar}] ${dumePct}% (${dumeTokens} / ~${ceiling.toLocaleString()} tok) | Epoch ${Math.floor(turns/5)+1} (Turn +${turns}) | Runway: ~${runwayTokens.toLocaleString()} tok | Last Turn: +210 tok (📥 120 in | 📤 90 out) | Zone: 🟢 Nominal`;
      }
    }

    if (sliderTurns && sliderCeiling) {
      sliderTurns.addEventListener('input', updateCalculations);
      sliderCeiling.addEventListener('input', updateCalculations);
      updateCalculations();
    }
  }

  // --- INTEGRATION TABS ---
  function setupTabs() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabPanels = document.querySelectorAll('.tab-panel');

    tabBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        tabBtns.forEach(b => b.classList.remove('active'));
        tabPanels.forEach(p => p.classList.remove('active'));

        btn.classList.add('active');
        const targetId = btn.getAttribute('data-tab');
        const targetPanel = document.getElementById(targetId);
        if (targetPanel) {
          targetPanel.classList.add('active');
        }
      });
    });
  }

  // --- LIGHTBOX GALLERY ---
  function setupLightbox() {
    const modal = document.getElementById('lightbox-modal');
    const modalImg = document.getElementById('lightbox-img');
    const modalCaption = document.getElementById('lightbox-caption');
    const closeBtn = document.getElementById('lightbox-close');
    const backdrop = document.getElementById('lightbox-backdrop');

    if (!modal || !modalImg) return;

    document.querySelectorAll('.gallery-card').forEach(card => {
      card.addEventListener('click', () => {
        const fullSrc = card.getAttribute('data-full');
        const captionTitle = card.querySelector('h4')?.textContent || '';
        const captionDesc = card.querySelector('p')?.textContent || '';

        modalImg.src = fullSrc;
        modalCaption.innerHTML = `<strong>${captionTitle}</strong> — ${captionDesc}`;
        modal.classList.add('active');
        modal.setAttribute('aria-hidden', 'false');
      });
    });

    function closeModal() {
      modal.classList.remove('active');
      modal.setAttribute('aria-hidden', 'true');
      modalImg.src = '';
    }

    if (closeBtn) closeBtn.addEventListener('click', closeModal);
    if (backdrop) backdrop.addEventListener('click', closeModal);
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && modal.classList.contains('active')) {
        closeModal();
      }
    });
  }

  // --- SMOOTH SCROLL ACTIVE HIGHLIGHT ---
  function setupNavHighlight() {
    const sections = document.querySelectorAll('section[id]');
    const navItems = document.querySelectorAll('.nav-item');

    window.addEventListener('scroll', () => {
      let current = '';
      const scrollY = window.pageYOffset;

      sections.forEach(section => {
        const sectionTop = section.offsetTop - 120;
        const sectionHeight = section.offsetHeight;
        if (scrollY >= sectionTop && scrollY < sectionTop + sectionHeight) {
          current = section.getAttribute('id');
        }
      });

      navItems.forEach(item => {
        item.classList.remove('active');
        if (item.getAttribute('href') === '#' + current) {
          item.classList.add('active');
        }
      });
    });
  }

  // --- INITIALIZATION ---
  document.addEventListener('DOMContentLoaded', () => {
    setupClipboard();
    setupTerminal();
    setupOdometerCalculator();
    setupTabs();
    setupLightbox();
    setupNavHighlight();
  });

})();
