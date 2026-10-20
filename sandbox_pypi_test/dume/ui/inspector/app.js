let activeEntityId = "DemoUser-01";
let schemaOpcodes = [];
let ws = null;

document.addEventListener("DOMContentLoaded", async () => {
  try { loadHealth(); } catch(e) { console.error("Health init error:", e); }
  try { await loadEntities(); } catch(e) { console.error("Entities init error:", e); }
  try { loadSchema(); } catch(e) { console.error("Schema init error:", e); }
  try { loadProxyConfig(); } catch(e) { console.error("Proxy config init error:", e); }
  try { setupWebSocket(); } catch(e) { console.error("WS init error:", e); }
  try { setupEventListeners(); } catch(e) { console.error("EventListeners init error:", e); }
});

function addSafeListener(elementOrId, event, handler) {
  const el = typeof elementOrId === "string" ? document.getElementById(elementOrId) : elementOrId;
  if (el) {
    el.addEventListener(event, handler);
  }
}

async function loadProxyConfig() {
  try {
    const res = await fetch("/api/proxy/config");
    const data = await res.json();
    const textEl = document.getElementById("proxy-status-text");
    if (textEl && data.upstream_base_url) {
      textEl.textContent = `📡 Proxy Active: Forwarding to ${data.upstream_base_url}`;
    }
  } catch (err) {
    console.error("Proxy config fetch failed:", err);
  }
}

function getStoredCustomEntities() {
  try {
    const raw = localStorage.getItem("dume_custom_entities") || "[]";
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(e => typeof e === "string");
  } catch (e) {
    return [];
  }
}

function saveCustomEntity(id) {
  if (!id || typeof id !== "string") return;
  const current = getStoredCustomEntities();
  if (!current.includes(id)) {
    current.push(id);
    try {
      localStorage.setItem("dume_custom_entities", JSON.stringify(current));
    } catch(e) {}
  }
}

async function loadEntities(selectedIdToSet = null) {
  try {
    if (localStorage.getItem("dume_custom_entities")) {
      const stored = getStoredCustomEntities().filter(e => typeof e === "string" && !e.startsWith("2e4c") && !e.startsWith("25fd"));
      if (stored.length === 0) {
        localStorage.removeItem("dume_custom_entities");
      } else {
        localStorage.setItem("dume_custom_entities", JSON.stringify(stored));
      }
    }

    const res = await fetch("/api/entities");
    const data = await res.json();
    const select = document.getElementById("select-entity");
    const hiddenInput = document.getElementById("entity_id");

    if (selectedIdToSet) {
      saveCustomEntity(selectedIdToSet);
    }

    const targetVal = selectedIdToSet || "DemoUser-01";
    const rawEntities = Array.isArray(data.entities) ? data.entities : ["DemoUser-01"];
    const customEntities = getStoredCustomEntities();

    const filteredServerEntities = rawEntities.filter(id => typeof id === "string" && !/^[0-9a-fA-F-]{32,36}$/.test(id));
    const combinedList = Array.from(new Set(["DemoUser-01", ...filteredServerEntities, ...customEntities]));

    if (select) {
      select.innerHTML = "";
      combinedList.forEach(id => {
        const opt = document.createElement("option");
        opt.value = id;
        opt.textContent = id;
        if (id === targetVal) opt.selected = true;
        select.appendChild(opt);
      });
    }

    if (hiddenInput) {
      hiddenInput.value = targetVal;
    }
    activeEntityId = targetVal;
    await inspectEntity(targetVal);
  } catch (err) {
    console.error("Failed to load entity IDs:", err);
    activeEntityId = selectedIdToSet || "DemoUser-01";
    await inspectEntity(activeEntityId);
  }
}

async function loadHealth() {
  try {
    const res = await fetch("/health");
    const data = await res.json();
    if (data.storage) {
      const activeEl = document.getElementById("metric-active-count");
      const historyEl = document.getElementById("metric-history-count");
      if (activeEl) activeEl.textContent = data.storage.active_registers_count;
      if (historyEl) historyEl.textContent = data.storage.history_records_count;
    }
    if (data.scribe_queue_size !== undefined) {
      const qEl = document.getElementById("metric-queue-size");
      if (qEl) qEl.textContent = `${data.scribe_queue_size} Turns`;
    }
  } catch (err) {
    console.error("Health check failed:", err);
  }
}

let currentFilter = "all";
let currentSearch = "";

async function loadSchema() {
  try {
    const res = await fetch("/api/schema");
    const data = await res.json();
    schemaOpcodes = data.opcodes || [];
    
    const tbody = document.querySelector("#schema-table tbody");
    if (tbody) {
      tbody.innerHTML = "";
      schemaOpcodes.forEach(op => {
        const tr = document.createElement("tr");
        const autoBadge = op.is_auto ? `<span style="background: rgba(168, 85, 247, 0.2); border: 1px solid rgba(168, 85, 247, 0.4); color: #c084fc; padding: 0.1rem 0.4rem; border-radius: 9999px; font-size: 0.7rem; font-weight: 700; margin-left: 0.35rem;">AUTO</span>` : '';
        tr.innerHTML = `
          <td style="font-family: var(--font-mono); font-weight: 600; color: var(--accent-amber);">${op.opcode}</td>
          <td style="font-weight: 600;">${op.name}${autoBadge}</td>
          <td><span style="background: rgba(255,255,255,0.06); padding: 0.15rem 0.4rem; border-radius: 4px; font-size: 0.75rem;">${op.data_type}</span></td>
          <td style="color: var(--text-muted);">${op.description}</td>
        `;
        tbody.appendChild(tr);
      });
    }

    renderSchemaManagerTable();
    loadPresetPacks();
  } catch (err) {
    console.error("Schema fetch failed:", err);
  }
}

async function loadPresetPacks() {
  try {
    const res = await fetch("/api/schema/packs");
    const data = await res.json();
    const packs = data.packs || [];
    const container = document.getElementById("preset-packs-grid");
    if (!container) return;

    container.innerHTML = "";
    packs.forEach(pack => {
      const card = document.createElement("div");
      card.className = "preset-pack-card";

      const keyPills = (pack.opcodes || []).map(op => `<span class="pack-key-pill">${op.name}</span>`).join(" ");
      const isLoaded = pack.is_loaded;
      const btnText = isLoaded ? "✓ Pack Loaded" : "📥 Load Pack";
      const btnClass = isLoaded ? "btn-load-pack loaded" : "btn-load-pack";

      card.innerHTML = `
        <div>
          <div class="pack-card-header">
            <div class="pack-card-title">📦 ${pack.title}</div>
            <span style="font-size: 0.75rem; color: var(--text-dim); font-family: var(--font-mono);">${pack.opcode_count} Opcodes</span>
          </div>
          <div class="pack-card-desc">${pack.description}</div>
          <div class="pack-pill-list">${keyPills}</div>
        </div>
        <button type="button" class="${btnClass}" ${isLoaded ? "disabled" : ""} data-pack-name="${pack.name}">
          ${btnText}
        </button>
      `;
      container.appendChild(card);
    });

    container.querySelectorAll(".btn-load-pack:not(.loaded)").forEach(btn => {
      btn.addEventListener("click", async () => {
        const packName = btn.getAttribute("data-pack-name");
        btn.textContent = "Loading...";
        try {
          const resp = await fetch("/api/schema/packs/load", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ pack_name: packName })
          });
          const result = await resp.json();
          if (resp.ok && result.success) {
            loadSchema();
            appendTerminalLine("system", `Loaded preset domain pack: '${packName}' (${result.loaded_count} opcodes)`);
          } else {
            alert("Failed to load pack: " + (result.detail || result.error));
            btn.textContent = "📥 Load Pack";
          }
        } catch (e) {
          alert("Error loading pack: " + e.message);
          btn.textContent = "📥 Load Pack";
        }
      });
    });
  } catch (err) {
    console.error("Failed to load preset packs:", err);
  }
}

function renderSchemaManagerTable() {
  const tbody = document.getElementById("schema-manager-tbody");
  if (!tbody) return;

  tbody.innerHTML = "";

  const filtered = schemaOpcodes.filter(op => {
    let matchesFilter = true;
    if (currentFilter === "preset") {
      matchesFilter = (op.opcode >= 1000 && op.opcode <= 1999);
    } else if (currentFilter === "auto") {
      matchesFilter = op.is_auto || (op.opcode >= 2000 && op.opcode <= 2999);
    } else if (currentFilter === "custom") {
      matchesFilter = !op.is_auto && (op.opcode >= 3000 && op.opcode <= 3999);
    }

    let matchesSearch = true;
    if (currentSearch) {
      const q = currentSearch.toLowerCase();
      matchesSearch = (
        (op.name && op.name.toLowerCase().includes(q)) ||
        String(op.opcode).includes(q) ||
        (op.description && op.description.toLowerCase().includes(q))
      );
    }

    return matchesFilter && matchesSearch;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No opcodes match current search filter.</td></tr>`;
    return;
  }

  filtered.forEach(op => {
    let originClass = "preset";
    let originLabel = "PRESET";

    if (op.is_auto || (op.opcode >= 2000 && op.opcode <= 2999)) {
      originClass = "auto";
      originLabel = "AUTO";
    } else if (op.opcode >= 3000 && op.opcode <= 3999) {
      originClass = "custom";
      originLabel = "CUSTOM";
    } else if (op.opcode >= 1000 && op.opcode <= 1099) {
      originClass = "preset";
      originLabel = "SYSTEM";
    }

    let enumSummary = "";
    if (op.data_type === "ENUM" && op.enum_values) {
      const pairs = Object.entries(op.enum_values).map(([k, v]) => `${k}:${v}`).join(", ");
      enumSummary = `<div style="font-size: 0.75rem; color: var(--accent-amber); font-family: var(--font-mono); margin-top: 0.2rem;">Map: {${pairs}}</div>`;
    }

    let unitBadge = op.unit ? `<span style="font-size: 0.7rem; color: var(--accent-cyan); font-family: var(--font-mono); margin-left: 0.35rem;">[${op.unit}]</span>` : '';

    let actionBtn = "";
    if (originLabel === "AUTO") {
      actionBtn = `<button type="button" class="btn-promote" data-promote-opcode="${op.opcode}" style="padding: 0.25rem 0.55rem; font-size: 0.75rem; background: rgba(168, 85, 247, 0.2); border: 1px solid rgba(168, 85, 247, 0.4); color: #c084fc; border-radius: 4px; font-weight: 600; cursor: pointer;">⚡ Promote to Registry</button>`;
    }

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><span class="origin-badge ${originClass}">${originLabel}</span></td>
      <td style="font-family: var(--font-mono); font-weight: 600; color: var(--accent-amber);">${op.opcode}</td>
      <td style="font-weight: 700;">${op.name}</td>
      <td><span style="background: rgba(255,255,255,0.06); padding: 0.15rem 0.4rem; border-radius: 4px; font-size: 0.75rem; font-family: var(--font-mono);">${op.data_type}</span>${unitBadge}</td>
      <td><div>${op.description || 'No description provided'}</div>${enumSummary}</td>
      <td>${actionBtn}</td>
    `;
    tbody.appendChild(tr);
  });

  tbody.querySelectorAll("[data-promote-opcode]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const opId = parseInt(btn.getAttribute("data-promote-opcode"), 10);
      try {
        const resp = await fetch("/api/schema/promote", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ opcode: opId })
        });
        const res = await resp.json();
        if (resp.ok && res.success) {
          loadSchema();
          appendTerminalLine("system", `Promoted auto-discovered Opcode ${opId} ('${res.spec.name}') to permanent schema registry.`);
        } else {
          alert("Promotion failed: " + (res.detail || res.error));
        }
      } catch (e) {
        alert("Error promoting opcode: " + e.message);
      }
    });
  });
}

function setupWebSocket() {
  try {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/api/ws/inspector`;
    
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      const ind = document.getElementById("scribe-ws-indicator");
      const statusEl = document.getElementById("lmdb-status");
      if (ind) ind.style.backgroundColor = "var(--accent-emerald)";
      if (statusEl) statusEl.textContent = "Background Scribe Live (WebSocket Connected)";
      
      if (window.wsHeartbeat) clearInterval(window.wsHeartbeat);
      window.wsHeartbeat = setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send("ping");
        }
      }, 5000);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "MUTATION_COMMIT") {
          addScribeFeedItem(data);
          loadHealth();
          if (data.entity_id === activeEntityId) {
            inspectEntity(activeEntityId);
          }
        } else if (data.event === "SCHEMA_MUTATION" || data.type === "SCHEMA_MUTATION") {
          loadSchema();
          if (data.spec) {
            appendTerminalLine("system", `[Schema Mutation] Dynamic opcode registered: ID ${data.spec.opcode} ('${data.spec.name}')`);
          }
        }
      } catch (err) {
        console.error("WebSocket message parse error:", err);
      }
    };

    ws.onclose = () => {
      const ind = document.getElementById("scribe-ws-indicator");
      const statusEl = document.getElementById("lmdb-status");
      if (ind) ind.style.backgroundColor = "var(--accent-rose)";
      if (statusEl) statusEl.textContent = "Background Scribe Reconnecting...";
      setTimeout(setupWebSocket, 3000);
    };
  } catch(e) {
    console.error("Failed to setup WebSocket:", e);
  }
}

function addScribeFeedItem(event) {
  const feedView = document.getElementById("scribe-feed-view");
  if (!feedView) return;
  if (feedView.querySelector("div[style*='color']")) {
    feedView.innerHTML = "";
  }

  const item = document.createElement("div");
  item.className = "scribe-feed-item";
  item.innerHTML = `
    <div>
      <span style="color: var(--accent-emerald); font-weight: 600;">[COMMIT]</span>
      <b>${event.opcode_name}</b> = <span style="color: var(--accent-cyan);">${event.human_value}</span>
      <div style="font-size: 0.7rem; color: var(--text-muted);">Entity: ${(event.entity_id || '').substring(0, 8)}...</div>
    </div>
    <div style="font-size: 0.7rem; color: var(--text-dim); text-align: right;">
      ${new Date((event.timestamp || 0) * 1000).toLocaleTimeString()}
    </div>
  `;

  feedView.prepend(item);
}

function appendTerminalLine(role, text) {
  const terminalLog = document.getElementById("terminal-log");
  if (!terminalLog) return null;
  const line = document.createElement("div");
  line.className = `terminal-line ${role}-line`;
  
  let prefix = "[USER]";
  if (role === "nostra") prefix = "[DUME]";
  if (role === "system") prefix = "[SYSTEM]";

  line.innerHTML = `<span class="terminal-prefix">${prefix}</span> ${escapeHtml(text || '')}`;
  terminalLog.appendChild(line);
  terminalLog.scrollTop = terminalLog.scrollHeight;
  return line;
}

function escapeHtml(str) {
  if (typeof str !== "string") str = String(str || '');
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function updateScratchpadBadge(sp) {
  const badge = document.getElementById("scratchpad-badge");
  if (!badge || !sp) return;
  const turns = sp.active_turns ?? 0;
  const maxT = sp.max_turns ?? 4;
  const tok = sp.estimated_tokens ?? 0;
  const maxTok = sp.max_tokens ?? 2048;
  badge.textContent = `🧠 Scratchpad: ${turns}/${maxT} Turns (~${tok}/${maxTok} Tok)`;
}

function setupEventListeners() {
  setupIntakeModal();

  addSafeListener("btn-flush-scratchpad", "click", async () => {
    const hiddenInp = document.getElementById("entity_id");
    const id = activeEntityId || (hiddenInp ? hiddenInp.value : null) || "DemoUser-01";
    try {
      const res = await fetch(`/api/session/flush/${id}`, { method: "POST" });
      const data = await res.json();
      updateScratchpadBadge(data);
      appendTerminalLine("system", "Scratchpad flushed. Active state registers preserved in DUMEdb.");
    } catch (err) {
      console.error("Flush scratchpad failed:", err);
    }
  });

  addSafeListener("select-entity", "change", (e) => {
    const val = e.target.value;
    const hiddenInp = document.getElementById("entity_id");
    if (hiddenInp) hiddenInp.value = val;
    activeEntityId = val;
    inspectEntity(val);
  });

  const newContainer = document.getElementById("new-entity-container");
  addSafeListener("btn-toggle-new-entity", "click", () => {
    if (!newContainer) return;
    const isHidden = newContainer.style.display === "none";
    newContainer.style.display = isHidden ? "block" : "none";
    if (isHidden) {
      const inp = document.getElementById("new-entity-name");
      if (inp) inp.focus();
    }
  });

  addSafeListener("btn-create-entity", "click", () => {
    const nameInput = document.getElementById("new-entity-name");
    if (!nameInput) return;
    const name = nameInput.value.trim();
    if (!name) return;

    saveCustomEntity(name);
    activeEntityId = name;
    const hiddenInp = document.getElementById("entity_id");
    if (hiddenInp) hiddenInp.value = name;

    loadEntities(name);
    nameInput.value = "";
    if (newContainer) newContainer.style.display = "none";

    appendTerminalLine("system", `Created new Entity: '${name}'. Selected as active.`);
  });

  addSafeListener("new-entity-name", "keypress", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const btn = document.getElementById("btn-create-entity");
      if (btn) btn.click();
    }
  });

  const newSchemaContainer = document.getElementById("new-schema-container");
  const btnToggleSchema = document.getElementById("btn-toggle-new-schema");
  if (btnToggleSchema && newSchemaContainer) {
    btnToggleSchema.addEventListener("click", () => {
      const isHidden = newSchemaContainer.style.display === "none";
      newSchemaContainer.style.display = isHidden ? "block" : "none";
      if (isHidden) {
        const inp = document.getElementById("new-schema-name");
        if (inp) inp.focus();
      }
    });
  }

  const selectType = document.getElementById("new-schema-type");
  const enumGroup = document.getElementById("new-schema-enum-group");
  if (selectType && enumGroup) {
    selectType.addEventListener("change", (e) => {
      enumGroup.style.display = e.target.value === "ENUM" ? "block" : "none";
    });
  }

  const btnSubmitSchema = document.getElementById("btn-submit-schema");
  if (btnSubmitSchema) {
    btnSubmitSchema.addEventListener("click", async () => {
      const opcodeVal = document.getElementById("new-schema-opcode")?.value;
      const nameVal = document.getElementById("new-schema-name")?.value.trim();
      const typeVal = document.getElementById("new-schema-type")?.value;
      const descVal = document.getElementById("new-schema-desc")?.value.trim();
      const unitVal = document.getElementById("new-schema-unit")?.value.trim();
      const enumRaw = document.getElementById("new-schema-enum-text")?.value.trim();

      if (!nameVal) {
        alert("Opcode Name is required!");
        return;
      }

      let enumMap = null;
      if (typeVal === "ENUM" && enumRaw) {
        enumMap = {};
        enumRaw.split(",").forEach(pair => {
          const parts = pair.split(":");
          if (parts.length === 2) {
            const k = parseInt(parts[0].trim(), 10);
            const v = parts[1].trim();
            if (!isNaN(k) && v) {
              enumMap[k] = v;
            }
          }
        });
      }

      const payload = {
        name: nameVal,
        data_type: typeVal || "INT",
        description: descVal || "",
        unit: unitVal || null,
        enum_values: enumMap
      };
      if (opcodeVal) {
        payload.opcode = parseInt(opcodeVal, 10);
      }

      try {
        const res = await fetch("/api/schema/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok || data.error) {
          alert("Error registering opcode: " + (data.detail || data.error));
          return;
        }

        if (document.getElementById("new-schema-opcode")) document.getElementById("new-schema-opcode").value = "";
        if (document.getElementById("new-schema-name")) document.getElementById("new-schema-name").value = "";
        if (document.getElementById("new-schema-desc")) document.getElementById("new-schema-desc").value = "";
        if (document.getElementById("new-schema-unit")) document.getElementById("new-schema-unit").value = "";
        if (document.getElementById("new-schema-enum-text")) document.getElementById("new-schema-enum-text").value = "";
        if (newSchemaContainer) newSchemaContainer.style.display = "none";

        loadSchema();
        appendTerminalLine("system", `Successfully registered dynamic Opcode ${data.spec.opcode}: '${data.spec.name}'`);
      } catch (err) {
        alert("Failed to register schema opcode: " + err.message);
      }
    });
  }

  const savedKey = localStorage.getItem("dume_gemini_api_key") || "";
  const keyInput = document.getElementById("input-api-key");
  if (keyInput && savedKey) {
    keyInput.value = savedKey;
  }
  if (keyInput) {
    keyInput.addEventListener("input", (e) => {
      localStorage.setItem("dume_gemini_api_key", e.target.value.trim());
    });
  }

  addSafeListener("btn-wake-nostra", "click", () => {
    alert("⚡ DUMEdb External Client Proxy Instructions\n\n1. Point your agent or client to: http://localhost:8090/v1\n2. Optional API Key: dume-local\n3. Header X-Entity-ID: DemoUser-01 (or set target entity)\n\nPrompts routed through the proxy are automatically grounded in active 32-byte state registers!");
  });

  addSafeListener("chat-turn-form", "submit", async (e) => {
    e.preventDefault();
    const hiddenInp = document.getElementById("entity_id");
    const turnInputEl = document.getElementById("turn-input");

    const entityInput = (hiddenInp ? hiddenInp.value.trim() : "") || activeEntityId || "DemoUser-01";
    const turnInput = turnInputEl ? turnInputEl.value.trim() : "";

    if (!turnInput) return;

    appendTerminalLine("user", turnInput);
    if (turnInputEl) turnInputEl.value = "";

    appendTerminalLine("system", "[SYSTEM] No agent connected. Route requests via proxy at http://localhost:8090/v1 to ground prompts in active state registers.");
  });

      const latEl = document.getElementById("metric-latency");
      const tpsEl = document.getElementById("metric-tps");
      const synthEl = document.getElementById("metric-synth-ms");
      const speedBadge = document.getElementById("terminal-speed-badge");
      const previewEl = document.getElementById("chat-output-preview");

      if (latEl) latEl.textContent = `${(data.dispatch_latency_ms ?? 0).toFixed(2)} ms`;
      const tps = data.tokens_per_sec ?? 0;
      const synthMs = data.synthesis_ms ? Math.round(data.synthesis_ms) : 0;
      if (tpsEl) tpsEl.textContent = `${tps} tok/s`;
      if (synthEl) synthEl.textContent = `${synthMs} ms Synthesis Latency`;
      if (speedBadge) speedBadge.textContent = `⚡ ${tps} tok/s (${synthMs}ms)`;

      if (data.scratchpad) {
        updateScratchpadBadge(data.scratchpad);
      }
      
      if (previewEl) previewEl.textContent = data.synthetic_response || "";

      appendTerminalLine("nostra", data.synthetic_response || "");

      inspectEntity(activeEntityId);
      loadHealth();
      loadEntities(activeEntityId);
    } catch (err) {
      if (thinkingLine) thinkingLine.remove();
      appendTerminalLine("system", `Error: ${err.message || "Communication failed"}`);
    }
  });

  addSafeListener("btn-refresh-inspector", "click", () => {
    const hiddenInp = document.getElementById("entity_id");
    const id = (hiddenInp ? hiddenInp.value.trim() : null) || activeEntityId;
    if (id && id !== "NEW") {
      inspectEntity(id);
    }
  });

  const connectModalOverlay = document.getElementById("connect-modal-overlay");
  const btnOpenConnectModal = document.getElementById("btn-open-connect-modal");
  const btnCloseConnectModal = document.getElementById("btn-close-connect-modal");

  if (btnOpenConnectModal && connectModalOverlay) {
    btnOpenConnectModal.addEventListener("click", () => {
      connectModalOverlay.style.display = "flex";
    });
  }

  if (btnCloseConnectModal && connectModalOverlay) {
    btnCloseConnectModal.addEventListener("click", () => {
      connectModalOverlay.style.display = "none";
    });
  }

  if (connectModalOverlay) {
    connectModalOverlay.addEventListener("click", (e) => {
      if (e.target === connectModalOverlay) {
        connectModalOverlay.style.display = "none";
      }
    });
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && connectModalOverlay && connectModalOverlay.style.display !== "none") {
      connectModalOverlay.style.display = "none";
    }
  });

  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-tab");
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));

      btn.classList.add("active");
      const targetPane = document.getElementById(targetId);
      if (targetPane) {
        targetPane.classList.add("active");
      }
    });
  });

  document.querySelectorAll(".btn-copy, .btn-copy-code").forEach(btn => {
    btn.addEventListener("click", async () => {
      const targetId = btn.getAttribute("data-copy-target");
      const targetEl = document.getElementById(targetId);
      if (!targetEl) return;

      let textToCopy = "";
      if (targetEl.tagName === "INPUT" || targetEl.tagName === "TEXTAREA") {
        textToCopy = targetEl.value;
      } else {
        textToCopy = targetEl.textContent || targetEl.innerText;
      }

      try {
        await navigator.clipboard.writeText(textToCopy);
        const originalText = btn.textContent;
        btn.textContent = "Copied!";
        btn.classList.add("copied");
        setTimeout(() => {
          btn.textContent = originalText;
          btn.classList.remove("copied");
        }, 1500);
      } catch (err) {
        console.error("Failed to copy text: ", err);
      }
    });
  });

  document.querySelectorAll(".main-tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const targetView = btn.getAttribute("data-view");
      document.querySelectorAll(".main-tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".main-view").forEach(v => v.style.display = "none");

      btn.classList.add("active");
      const el = document.getElementById(targetView);
      if (el) el.style.display = "block";
    });
  });

  document.querySelectorAll(".filter-pill").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".filter-pill").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentFilter = btn.getAttribute("data-filter") || "all";
      renderSchemaManagerTable();
    });
  });

  const searchInput = document.getElementById("input-schema-search");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      currentSearch = e.target.value.trim();
      renderSchemaManagerTable();
    });
  }

  const customModal = document.getElementById("custom-opcode-modal-overlay");
  const btnOpenCustom = document.getElementById("btn-open-custom-opcode-modal");
  const btnCloseCustom = document.getElementById("btn-close-custom-modal");
  const btnCancelCustom = document.getElementById("btn-cancel-custom-modal");
  const customTypeSelect = document.getElementById("custom-opcode-type");
  const customEnumGroup = document.getElementById("custom-opcode-enum-group");
  const customForm = document.getElementById("custom-opcode-form");

  if (btnOpenCustom && customModal) {
    btnOpenCustom.addEventListener("click", () => {
      customModal.style.display = "flex";
      const nameInp = document.getElementById("custom-opcode-name");
      if (nameInp) nameInp.focus();
    });
  }

  const closeCustomModal = () => {
    if (customModal) customModal.style.display = "none";
  };

  if (btnCloseCustom) btnCloseCustom.addEventListener("click", closeCustomModal);
  if (btnCancelCustom) btnCancelCustom.addEventListener("click", closeCustomModal);

  if (customModal) {
    customModal.addEventListener("click", (e) => {
      if (e.target === customModal) closeCustomModal();
    });
  }

  if (customTypeSelect && customEnumGroup) {
    customTypeSelect.addEventListener("change", (e) => {
      customEnumGroup.style.display = e.target.value === "ENUM" ? "block" : "none";
    });
  }

  if (customForm) {
    customForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const nameVal = document.getElementById("custom-opcode-name")?.value.trim();
      const typeVal = document.getElementById("custom-opcode-type")?.value;
      const descVal = document.getElementById("custom-opcode-desc")?.value.trim();
      const unitVal = document.getElementById("custom-opcode-unit")?.value.trim();
      const enumRaw = document.getElementById("custom-opcode-enum-text")?.value.trim();

      if (!nameVal) return;

      let enumMap = null;
      if (typeVal === "ENUM" && enumRaw) {
        enumMap = {};
        enumRaw.split(",").forEach(pair => {
          const parts = pair.split(":");
          if (parts.length === 2) {
            const k = parseInt(parts[0].trim(), 10);
            const v = parts[1].trim();
            if (!isNaN(k) && v) enumMap[k] = v;
          }
        });
      }

      try {
        const resp = await fetch("/api/schema/custom", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: nameVal,
            data_type: typeVal || "INT",
            description: descVal || "",
            unit: unitVal || null,
            enum_values: enumMap
          })
        });

        const res = await resp.json();
        if (resp.ok && res.success) {
          closeCustomModal();
          customForm.reset();
          if (customEnumGroup) customEnumGroup.style.display = "none";
          loadSchema();
          appendTerminalLine("system", `Successfully minted Custom Opcode ${res.spec.opcode}: '${res.spec.name}'`);
        } else {
          alert("Error minting custom opcode: " + (res.detail || res.error));
        }
      } catch (err) {
        alert("Failed to mint custom opcode: " + err.message);
      }
    });
  }
}

async function inspectEntity(entityId) {
  try {
    const targetId = entityId || activeEntityId || "DemoUser-01";
    const res = await fetch(`/api/inspector/hex/${targetId}`);
    const data = await res.json();

    const dumpContainer = document.getElementById("hex-dump-view");
    const previewEl = document.getElementById("prompt-register-preview");

    if (dumpContainer) dumpContainer.innerHTML = "";

    if (!data.memory_pages || data.memory_pages.length === 0) {
      if (dumpContainer) {
        dumpContainer.innerHTML = `<div style="color: var(--text-muted);">No active state registers found for entity ${targetId}</div>`;
      }
      if (previewEl) {
        previewEl.textContent = "No active registers.";
      }
      return;
    }

    let registersText = [];

    data.memory_pages.forEach(page => {
      const row = document.createElement("div");
      row.className = "hex-row";
      
      const decoded = page.decoded || {};
      const opcodeName = decoded.opcode_name || `OP_${page.opcode}`;
      const humanVal = decoded.human_value !== undefined ? decoded.human_value : (page.value_hex || '');

      row.innerHTML = `
        <span class="hex-chunk hex-uuid" title="Entity UUIDv7 (16 Bytes)">${page.uuid_hex || ''}</span>
        <span class="hex-chunk hex-opcode" title="Opcode ID (2 Bytes)">${page.opcode_hex || ''}</span>
        <span class="hex-chunk hex-value" title="State Value (8 Bytes)">${page.value_hex || ''}</span>
        <span class="hex-chunk hex-ts" title="Timestamp (4 Bytes)">${page.timestamp_hex || ''}</span>
        <span class="hex-chunk hex-flags" title="Bitfield Flags (2 Bytes)">${page.flags_hex || ''}</span>
        <span style="margin-left: auto; font-size: 0.8rem; color: var(--text-muted);">
          <b>${opcodeName}</b> = <span style="color: var(--accent-emerald); font-weight: 600;">${humanVal}</span>
        </span>
      `;
      if (dumpContainer) dumpContainer.appendChild(row);
      registersText.push(`${opcodeName}=${humanVal}`);
    });

    const shortId = targetId.substring(0, 8);
    const regCtx = `[DUME_STATE entity=${shortId}] ${registersText.join(" | ")} [/DUME_STATE]`;
    if (previewEl) {
      previewEl.textContent = regCtx;
    }

  } catch (err) {
    console.error("Failed to fetch hex dump:", err);
  }
}

function setupIntakeModal() {
  const modal = document.getElementById("intake-modal");
  const openBtn = document.getElementById("btn-open-intake-modal");
  const closeBtn = document.getElementById("btn-close-intake-modal");
  const form = document.getElementById("intake-form");
  const entitySelect = document.getElementById("intake-target-entity");
  const docInput = document.getElementById("intake-doc-text");
  const flushCheckbox = document.getElementById("intake-flush-scratchpad");
  const submitBtn = document.getElementById("btn-submit-intake");
  const resultContainer = document.getElementById("intake-result-container");
  const diffView = document.getElementById("intake-diff-view");

  if (!modal || !openBtn) return;

  openBtn.addEventListener("click", () => {
    if (entitySelect && document.getElementById("select-entity")) {
      entitySelect.innerHTML = document.getElementById("select-entity").innerHTML;
      entitySelect.value = activeEntityId || "DemoUser-01";
    }
    if (resultContainer) resultContainer.style.display = "none";
    modal.style.display = "flex";
  });

  if (closeBtn) {
    closeBtn.addEventListener("click", () => {
      modal.style.display = "none";
    });
  }

  modal.addEventListener("click", (e) => {
    if (e.target === modal) modal.style.display = "none";
  });

  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const rawText = docInput ? docInput.value.trim() : "";
      if (!rawText) return;

      const targetEntity = (entitySelect && entitySelect.value) || activeEntityId || "DemoUser-01";
      const shouldFlush = flushCheckbox ? flushCheckbox.checked : true;

      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "⏳ Ingesting...";
      }

      try {
        let batchRegisters = {};
        const noiseWords = new Set([
          "TODAY", "TOMORROW", "OVERWHELMED", "HELLO", "THANKS", "PLEASE",
          "SORRY", "OKAY", "SOMETHING", "HTTP", "HTTPS", "YESTERDAY",
          "REALLY", "ACTUALLY", "BECAUSE", "JUST", "ANYTHING", "EVERYTHING"
        ]);

        const cleanVal = (valStr) => {
          if (!valStr) return "";
          let s = valStr.trim();
          const mdMatch = s.match(/\[.*?\]\((https?:\/\/[^\s)]+)\)/);
          if (mdMatch) {
            s = mdMatch[1];
          } else {
            const mdGen = s.match(/\[.*?\]\((.*?)\)/);
            if (mdGen) s = mdGen[1];
          }
          return s.replace(/\|+$/, "").trim().replace(/^['"]|['"]$/g, "");
        };

        const lines = rawText.split("\n");
        for (let i = 0; i < lines.length; i++) {
          let trimmed = lines[i].trim();
          if (!trimmed || trimmed.startsWith("#")) continue;

          if (trimmed.includes("|")) {
            if (/^[\s|:\-]+$/.test(trimmed)) continue;

            if (i + 1 < lines.length) {
              const nextLine = lines[i + 1].trim();
              if (nextLine.includes("|") && /^[\s|:\-]+$/.test(nextLine)) {
                continue;
              }
            }

            const cells = trimmed.split("|").map(c => c.trim()).filter(c => c.length > 0);
            if (cells.length >= 2) {
              const k = cells[0].toUpperCase().replace(/[^A-Z0-9_]/g, "_").replace(/_+/g, "_").replace(/^_+|_+$/g, "");
              const v = cleanVal(cells[1]);
              if (/^[A-Z0-9_]{3,32}$/.test(k) && !noiseWords.has(k) && v) {
                batchRegisters[k] = v;
              }
              continue;
            }
          }

          const matches = trimmed.matchAll(/(?:^|[\s,;])([A-Za-z0-9_]{3,32})\s*(?:=|\s+(?:is|IS)\s+|(?:(?<!http)(?<!https):))\s*['"]?([^\r\n'";]+)(?:['"]?)/g);
          for (const m of matches) {
            const k = m[1].trim().toUpperCase().replace(/[^A-Z0-9_]/g, "_").replace(/_+/g, "_").replace(/^_+|_+$/g, "");
            const v = cleanVal(m[2]);
            if (/^[A-Z0-9_]{3,32}$/.test(k) && !noiseWords.has(k) && v) {
              batchRegisters[k] = v;
            }
          }
        }

        if (Object.keys(batchRegisters).length > 0) {
          const resp = await fetch("/v1/dume/state/batch", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-Entity-ID": targetEntity
            },
            body: JSON.stringify({
              entity_id: targetEntity,
              registers: batchRegisters,
              flush_scratchpad: shouldFlush
            })
          });
          const resData = await resp.json();

          if (resp.ok && resData.status === "success") {
            if (resultContainer && diffView) {
              resultContainer.style.display = "block";
              diffView.innerHTML = `
                <div style="margin-bottom: 0.5rem; color: var(--accent-cyan);">Committed ${resData.committed_count} Registers (Flush Scratchpad: ${resData.flushed_scratchpad})</div>
                ${resData.records.map(r => `<div><span style="color: var(--accent-amber);">${r.opcode_name}</span> (${r.opcode}) = <span style="color: var(--accent-emerald);">${r.human_value}</span></div>`).join("")}
              `;
            }
            inspectEntity(targetEntity);
            loadHealth();
            appendTerminalLine("system", `Intake complete for '${targetEntity}': ${resData.committed_count} registers written to LMDB.`);
          } else {
            alert("Ingestion error: " + JSON.stringify(resData));
          }
        } else {
          const resp = await fetch("/v1/chat/completions", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-Entity-ID": targetEntity
            },
            body: JSON.stringify({
              model: "nostra-fast",
              messages: [
                { role: "user", content: `!intake ${rawText}` }
              ]
            })
          });
          const resData = await resp.json();
          if (resp.ok) {
            if (resultContainer && diffView) {
              resultContainer.style.display = "block";
              const assistantReply = resData.choices?.[0]?.message?.content || "Intake completed.";
              diffView.innerHTML = `<div style="color: var(--text-main); white-space: pre-wrap;">${assistantReply}</div>`;
            }
            inspectEntity(targetEntity);
            loadHealth();
            appendTerminalLine("system", `Intake directive processed for '${targetEntity}'.`);
          } else {
            alert("Intake completion error: " + JSON.stringify(resData));
          }
        }
      } catch (err) {
        alert("Ingestion failed: " + err.message);
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = "🚀 Run Ingestion";
        }
      }
    });
  }
}
