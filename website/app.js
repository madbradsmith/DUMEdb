/**
 * IBM 1401 DATA PROCESSING SYSTEM // DUME-CORE OPERATOR CONSOLE CONTROLLER
 * Architecture: Deterministic Unit-Record Memory Engine
 */

(function () {
  'use strict';

  // --- AUDIO RELAY FEEDBACK SYSTEM ---
  const sfxRelay = document.getElementById('sfx-relay');
  const sfxBlip = document.getElementById('sfx-blip');
  let audioEnabled = true;

  function playRelaySound() {
    if (!audioEnabled) return;
    try {
      if (sfxRelay) {
        sfxRelay.currentTime = 0;
        sfxRelay.play().catch(() => {});
      }
    } catch (e) {}
  }

  function playBlipSound() {
    if (!audioEnabled) return;
    try {
      if (sfxBlip) {
        sfxBlip.currentTime = 0;
        sfxBlip.play().catch(() => {});
      }
    } catch (e) {}
  }

  // --- CONSOLE TOAST NOTIFICATIONS ---
  const toast = document.getElementById('console-toast');
  let toastTimer = null;

  function showToast(message) {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast.classList.remove('show');
    }, 2200);
  }

  // --- 80-COLUMN HOLLERITH PUNCH CARD COPY ---
  const punchCard = document.getElementById('hollerith-card');
  if (punchCard) {
    punchCard.addEventListener('click', () => {
      const cmd = punchCard.getAttribute('data-copy') || 'pip install dumedb && python -m dume.mcp_server';
      navigator.clipboard.writeText(cmd).then(() => {
        playRelaySound();
        showToast('✓ 80-COL PUNCH CARD COPIED TO OPERATOR BUFFER');
        flashIndicatorLamps();
      });
    });
  }

  // --- INDICATOR LAMP PULSE ENGINE ---
  function flashIndicatorLamps() {
    const lamps = [
      document.getElementById('lamp-speed'),
      document.getElementById('lamp-wake'),
      document.getElementById('lamp-lmdb'),
      document.getElementById('lamp-reg')
    ];
    lamps.forEach(l => {
      if (l) {
        l.style.filter = 'brightness(1.8)';
        setTimeout(() => { l.style.filter = ''; }, 300);
      }
    });
  }

  // Subtle ambient pulse for the RUN lamp
  const lampRun = document.getElementById('lamp-run');
  if (lampRun) {
    setInterval(() => {
      lampRun.style.opacity = lampRun.style.opacity === '0.7' ? '1' : '0.7';
    }, 1200);
  }

  // --- MECHANICAL TOGGLE SWITCHES ---
  const toggleFastpath = document.getElementById('toggle-fastpath');
  if (toggleFastpath) {
    toggleFastpath.addEventListener('click', () => {
      toggleFastpath.classList.toggle('active');
      playBlipSound();
      const isActive = toggleFastpath.classList.contains('active');
      showToast(isActive ? 'FAST-PATH MODE: ARMED (4.2µs MMAP)' : 'STANDARD BUS MODE: ACTIVE');
    });
  }

  const toggleAudio = document.getElementById('toggle-audio');
  if (toggleAudio) {
    toggleAudio.addEventListener('click', () => {
      toggleAudio.classList.toggle('active');
      audioEnabled = toggleAudio.classList.contains('active');
      playBlipSound();
      showToast(audioEnabled ? 'MACHINE AUDIO RELAYS: ON' : 'MACHINE AUDIO RELAYS: MUTED');
    });
  }

  // --- HOPPER MODE SELECTOR (TERMINAL / VIDEO / MCP) ---
  const hopperTabs = document.querySelectorAll('.hopper-tab-btn');
  const boxTerminal = document.getElementById('mode-terminal-box');
  const boxVideo = document.getElementById('mode-video-box');
  const boxMcp = document.getElementById('mode-mcp-box');
  const hollerithCard = document.getElementById('hollerith-card');

  function switchHopperMode(mode) {
    playBlipSound();
    hopperTabs.forEach(tab => {
      tab.classList.toggle('active', tab.getAttribute('data-mode') === mode);
    });

    if (hollerithCard) {
      hollerithCard.style.display = (mode === 'terminal') ? 'block' : 'none';
    }
    if (boxTerminal) boxTerminal.style.display = (mode === 'terminal') ? 'flex' : 'none';
    if (boxVideo) {
      boxVideo.classList.toggle('active', mode === 'video');
      boxVideo.style.display = (mode === 'video') ? 'flex' : 'none';
    }
    if (boxMcp) {
      boxMcp.classList.toggle('active', mode === 'mcp');
      boxMcp.style.display = (mode === 'mcp') ? 'flex' : 'none';
    }
  }

  hopperTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      switchHopperMode(tab.getAttribute('data-mode'));
    });
  });

  // --- HD VIDEO FACADE LOGIC ---
  const videoFacade = document.getElementById('video-facade');
  const videoSlot = document.getElementById('video-iframe-slot');

  function playVideo() {
    if (!videoSlot || !videoFacade) return;
    videoFacade.style.display = 'none';
    videoSlot.style.display = 'block';
    videoSlot.innerHTML = `
      <iframe 
        class="crt-iframe"
        src="https://www.youtube.com/embed/nO5vozUhqyU?autoplay=1&rel=0&modestbranding=1" 
        title="Stop Force-Feeding Your AI 30,000 Tokens just to remind them who you are! — DUMEdb Walkthrough Video"
        frameborder="0"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" 
        referrerpolicy="strict-origin-when-cross-origin"
        allowfullscreen>
      </iframe>
    `;
    playBlipSound();
  }

  if (videoFacade) {
    videoFacade.addEventListener('click', playVideo);
    videoFacade.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        playVideo();
      }
    });
  }

  // --- INTERACTIVE 1402 CARD FEED TERMINAL ---
  const termLog = document.getElementById('term-log');
  const termForm = document.getElementById('term-cmd-form');
  const termInput = document.getElementById('term-cmd-input');

  function appendLog(text, className = 'term-line-sys') {
    if (!termLog) return;
    const line = document.createElement('div');
    line.className = className;
    line.innerHTML = text;
    termLog.appendChild(line);
    termLog.scrollTop = termLog.scrollHeight;
  }

  function handleCommand(cmdRaw) {
    const cmd = (cmdRaw || '').trim();
    if (!cmd) return;
    playRelaySound();
    flashIndicatorLamps();

    appendLog(`&gt; ${escapeHtml(cmd)}`, 'term-line-warn');

    const lower = cmd.toLowerCase();

    if (lower === 'box is the game' || lower === 'wake') {
      setTimeout(() => {
        appendLog('--- 🗄️ THE CABINET ORIENTATION ---', 'term-line-resp');
        appendLog('STATUS: ZERO-TURN WAKE HANDSHAKE CONFIRMED', 'term-line-resp');
        appendLog('OPERATOR: MadBrad // HARNESS: Sentinel Active // REGISTERS: 318', 'term-line-sys');
        appendLog('KV-CACHE OVERHEAD: 220 tokens | Clean Runway: 99.8%', 'term-line-resp');
        appendLog('NEXT MOVE: Execute unit-record state operations with zero replay amnesia.', 'term-line-sys');
      }, 120);
    } else if (lower === 'dume.odometer' || lower === 'odometer') {
      setTimeout(() => {
        appendLog('--- 📊 CONTEXT ODOMETER (REAL MATH) ---', 'term-line-resp');
        appendLog('Source: ~/.gemini/.../transcript.jsonl (Hardware Payload Math)', 'term-line-sys');
        appendLog('Consumption: [░░░░░░░░░░] 3.3% (3,970 / ~120,000 tok)', 'term-line-resp');
        appendLog('Epoch: 2 | Turn: +25 | Clean Runway: ~116,030 tok', 'term-line-sys');
        appendLog('Last Turn: +2,380 tok (📥 2,231 in | 📤 149 out) | Zone: 🟢 Nominal', 'term-line-resp');
      }, 100);
    } else if (lower === 'status') {
      setTimeout(() => {
        appendLog('--- [1401-CPU TELEMETRY] ---', 'term-line-sys');
        appendLog('STORAGE: LMDB Memory-Mapped Active (./data/dumedb.mdb)', 'term-line-resp');
        appendLog('READ LATENCY: 4.2 µs direct byte register access', 'term-line-resp');
        appendLog('PORT 8095: FastMCP HTTP & Inspector listening', 'term-line-sys');
        appendLog('SCHEMAS: adr_record, incident_rca, unit_record, error_fingerprint', 'term-line-sys');
      }, 90);
    } else if (lower === 'registers') {
      setTimeout(() => {
        appendLog('--- [DISCRETE REGISTERS: 318 ACTIVE] ---', 'term-line-sys');
        appendLog('ADDR 0001: operator_alias = "MadBrad"', 'term-line-resp');
        appendLog('ADDR 0002: session_status = "SENTINEL_ACTIVE"', 'term-line-resp');
        appendLog('ADDR 0003: wake_codeword = "box is the game"', 'term-line-resp');
        appendLog('ADDR 0004: memory_engine = "LMDB_MMAP_ZERO_REPLAY"', 'term-line-resp');
      }, 110);
    } else if (lower === 'compare') {
      setTimeout(() => {
        appendLog('=== REPLAY BLOAT vs DUMEDB UNIT-RECORD ===', 'term-line-warn');
        appendLog('Chat History Replay: 30,000+ tokens (~25% context eaten, $0.60/wake)', 'term-line-err');
        appendLog('DUMEdb Unit-Record Wake: 220 tokens (~0.2% context eaten, $0.0003/wake)', 'term-line-resp');
        appendLog('EFFICIENCY GAIN: 99.3% reduction in prompt bloat. Zero amnesia.', 'term-line-resp');
      }, 120);
    } else if (lower === 'clear') {
      if (termLog) termLog.innerHTML = '';
      appendLog('[CLEARED] Hopper buffer reset. Enter opcode command.', 'term-line-sys');
    } else {
      appendLog(`Unrecognized command: "${escapeHtml(cmd)}". Try typing: "box is the game", "dume.odometer", "status", "registers", or "compare".`, 'term-line-sys');
    }
  }

  function escapeHtml(str) {
    return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  if (termForm && termInput) {
    termForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const val = termInput.value;
      termInput.value = '';
      handleCommand(val);
    });
  }

  // Quick action pills in hopper
  document.querySelectorAll('.quick-pill[data-cmd]').forEach(pill => {
    pill.addEventListener('click', () => {
      const cmd = pill.getAttribute('data-cmd');
      handleCommand(cmd);
    });
  });

  // Stacker select button
  const btnStacker = document.getElementById('btn-stacker-dump');
  if (btnStacker) {
    btnStacker.addEventListener('click', () => {
      handleCommand('registers');
    });
  }

  // --- REGISTER MATRIX CARDS (BAY 2) INTERACTIVITY ---
  const regCards = document.querySelectorAll('.register-slot-card');
  regCards.forEach(card => {
    card.addEventListener('click', () => {
      regCards.forEach(c => c.classList.remove('active'));
      card.classList.add('active');
      playBlipSound();

      const addr = card.getAttribute('data-addr');
      const payload = card.getAttribute('data-payload');
      switchHopperMode('terminal');
      appendLog(`[READ-BRUSH] Inspected: ${addr}`, 'term-line-warn');
      if (payload) {
        appendLog(payload, 'term-line-resp');
      }
    });
  });

  // --- CONSOLE PUSH BUTTONS (BAY 4) ---
  const btnRunDemo = document.getElementById('btn-run-demo');
  if (btnRunDemo) {
    btnRunDemo.addEventListener('click', () => {
      switchHopperMode('terminal');
      handleCommand('box is the game');
    });
  }

  const btnViewMcp = document.getElementById('btn-view-mcp');
  if (btnViewMcp) {
    btnViewMcp.addEventListener('click', () => {
      switchHopperMode('mcp');
    });
  }

  // --- DIAGNOSTIC TICKER CYCLE ---
  const tickerEl = document.getElementById('diagnostic-ticker');
  const tickerMessages = [
    '02:14:48 SYS_RDY // 1401-CPU ARMED // 318 ACTIVE LMDB REGISTERS // NO CHAT REPLAY BLOAT',
    'READ_LATENCY: 4.2µs // MMAP_RAM // HARDWARE-ALIGNED BYTE REGISTERS // PARITY: OK',
    'WAKE PROTOCOL: "BOX IS THE GAME" // PAYLOAD: 220 TOKENS // ZERO-TURN CABIN HYDRATION',
    'FASTMCP SERVER LISTENING ON 127.0.0.1:8095 // 12 DISCRETE OPCODES VERIFIED',
    'GROUND-TRUTH ODOMETER // REAL DISK MATH // RUNWAY: 99.8% // AUTO-COMPACTION SHIELD ACTIVE'
  ];
  let tickerIdx = 0;
  if (tickerEl) {
    setInterval(() => {
      tickerIdx = (tickerIdx + 1) % tickerMessages.length;
      tickerEl.textContent = tickerMessages[tickerIdx];
    }, 4500);
  }

})();
