let activeEntityId = "MadBrad-Nostra-01";
let schemaOpcodes = [];
let ws = null;
let cachedEntityPages = [];
let lastTokenCount = 0;
let currentInspectorTab = "cards";
let currentCategoryFilter = "all";
let currentSearchQuery = "";


document.addEventListener("DOMContentLoaded", () => {
  try { setupEventListeners(); } catch(e) { console.error("EventListeners init error:", e); }
  try { setupDualViewInspector(); } catch(e) { console.error("DualView init error:", e); }
  try { setupStudioRegisterSuite(); } catch(e) { console.error("StudioSuite init error:", e); }
  try { setupIntakeModal(); } catch(e) { console.error("IntakeModal init error:", e); }
  try { setupWebSocket(); } catch(e) { console.error("WS init error:", e); }
  try { loadHealth(); } catch(e) { console.error("Health init error:", e); }
  try { loadEntities(); } catch(e) { console.error("Entities init error:", e); }
  try { loadSchema(); } catch(e) { console.error("Schema init error:", e); }
  try { loadProxyConfig(); } catch(e) { console.error("Proxy config init error:", e); }
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

function getEntityConfig(entityId) {
  const targetId = entityId || activeEntityId || "MadBrad-Nostra-01";
  try {
    const raw = localStorage.getItem(`dume_entity_cfg_${targetId}`);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") {
        return {
          provider: parsed.provider || "fast",
          model_name: parsed.model_name || "",
          api_key: parsed.api_key || localStorage.getItem("dume_gemini_api_key") || "",
          endpoint_url: parsed.endpoint_url || ""
        };
      }
    }
  } catch (e) {}

  return {
    provider: "fast",
    model_name: "",
    api_key: localStorage.getItem("dume_gemini_api_key") || "",
    endpoint_url: ""
  };
}

function saveEntityConfig(entityId, cfgUpdates = {}) {
  const targetId = entityId || activeEntityId || "MadBrad-Nostra-01";
  const current = getEntityConfig(targetId);
  const updated = { ...current, ...cfgUpdates };
  try {
    localStorage.setItem(`dume_entity_cfg_${targetId}`, JSON.stringify(updated));
    if (updated.api_key) {
      localStorage.setItem("dume_gemini_api_key", updated.api_key);
    }
  } catch (e) {
    console.error("Failed to save entity config:", e);
  }
  return updated;
}

function getEntityAlias(entityId) {
  try {
    return localStorage.getItem(`dume_entity_alias_${entityId}`) || "";
  } catch(e) {
    return "";
  }
}

function setEntityAlias(entityId, alias) {
  try {
    if (alias) {
      localStorage.setItem(`dume_entity_alias_${entityId}`, alias);
    } else {
      localStorage.removeItem(`dume_entity_alias_${entityId}`);
    }
  } catch(e) {}
}

function isEntityArchived(entityId) {
  try {
    return localStorage.getItem(`dume_entity_archived_${entityId}`) === "true";
  } catch(e) {
    return false;
  }
}

function setEntityArchived(entityId, isArchived) {
  try {
    if (isArchived) {
      localStorage.setItem(`dume_entity_archived_${entityId}`, "true");
    } else {
      localStorage.removeItem(`dume_entity_archived_${entityId}`);
    }
  } catch(e) {}
}

function hydrateEntityConfig(entityId) {
  const cfg = getEntityConfig(entityId);
  const presetEl = document.getElementById("select-provider-preset");
  const modelNameEl = document.getElementById("input-model-name");
  const keyEl = document.getElementById("input-api-key");
  const endpointEl = document.getElementById("input-endpoint-url");

  if (presetEl) presetEl.value = cfg.provider || "fast";
  if (modelNameEl) modelNameEl.value = cfg.model_name || "";
  if (keyEl) keyEl.value = cfg.api_key || "";
  if (endpointEl) {
    endpointEl.value = cfg.endpoint_url || "";
    const p = (cfg.provider || "").toLowerCase();
    endpointEl.style.display = (p === "custom" || p === "groq" || p === "openai") ? "block" : "none";
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

    const targetVal = selectedIdToSet || "MadBrad-Nostra-01";
    const rawEntities = Array.isArray(data.entities) ? data.entities : ["MadBrad-Nostra-01"];
    const customEntities = getStoredCustomEntities();

    const filteredServerEntities = rawEntities.filter(id => typeof id === "string" && !/^[0-9a-fA-F-]{32,36}$/.test(id));
    const combinedList = Array.from(new Set(["MadBrad-Nostra-01", ...filteredServerEntities, ...customEntities]));

    if (select) {
      select.innerHTML = "";
      combinedList.forEach(id => {
        const isArchived = isEntityArchived(id);
        if (isArchived && id !== targetVal) return;

        const alias = getEntityAlias(id);
        const opt = document.createElement("option");
        opt.value = id;
        opt.textContent = alias ? `${alias} (${id})` : id;
        if (id === targetVal) opt.selected = true;
        select.appendChild(opt);
      });
    }

    if (hiddenInput) {
      hiddenInput.value = targetVal;
    }
    activeEntityId = targetVal;
    hydrateEntityConfig(targetVal);
    await inspectEntity(targetVal);
  } catch (err) {
    console.error("Failed to load entity IDs:", err);
    activeEntityId = selectedIdToSet || "MadBrad-Nostra-01";
    hydrateEntityConfig(activeEntityId);
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

let knowledgeAssets = [];
let currentKnowledgeFilter = "all";
let currentKnowledgeSearch = "";

async function loadKnowledgeAssets() {
  try {
    const res = await fetch("/api/assets/list");
    const data = await res.json();
    knowledgeAssets = data.assets || [];
    renderKnowledgeExplorer();
  } catch (err) {
    console.error("Failed to load knowledge assets:", err);
  }
}

function renderKnowledgeExplorer() {
  const container = document.getElementById("knowledge-cards-list");
  if (!container) return;

  container.innerHTML = "";

  const filtered = knowledgeAssets.filter(item => {
    let matchesFilter = true;
    if (currentKnowledgeFilter !== "all") {
      matchesFilter = item.category.toLowerCase() === currentKnowledgeFilter.toLowerCase();
    }

    let matchesSearch = true;
    if (currentKnowledgeSearch) {
      const q = currentKnowledgeSearch.toLowerCase();
      matchesSearch = (
        item.title.toLowerCase().includes(q) ||
        item.filename.toLowerCase().includes(q)
      );
    }

    return matchesFilter && matchesSearch;
  });

  if (filtered.length === 0) {
    container.innerHTML = `<div style="color: var(--text-muted); text-align: center; padding: 2rem;">No diagnostic cards match the current filter.</div>`;
    return;
  }

  filtered.forEach(item => {
    const card = document.createElement("div");
    card.className = "knowledge-card-item";
    const catClass = item.category === "adr" ? "adr" : (item.category === "error" ? "error" : "incident");
    const catLabel = item.category.toUpperCase();
    const dateStr = item.mtime ? new Date(item.mtime * 1000).toLocaleString() : "";

    card.innerHTML = `
      <div style="display: flex; align-items: center; justify-content: space-between;">
        <span class="knowledge-badge ${catClass}">${catLabel}</span>
        <span style="font-size: 0.7rem; color: var(--text-dim); font-family: var(--font-mono);">${dateStr}</span>
      </div>
      <div style="font-weight: 600; color: var(--text-main); font-size: 0.88rem;">${item.title}</div>
      <div style="font-size: 0.75rem; color: var(--text-muted); font-family: var(--font-mono);">${item.filename}</div>
    `;

    card.addEventListener("click", () => {
      document.querySelectorAll(".knowledge-card-item").forEach(el => el.classList.remove("active"));
      card.classList.add("active");
      viewAssetMarkdown(item.category, item.filename);
    });

    container.appendChild(card);
  });
}

async function viewAssetMarkdown(category, filename) {
  const readerEl = document.getElementById("asset-card-reader");
  const filenameEl = document.getElementById("knowledge-active-filename");

  if (filenameEl) filenameEl.textContent = `${category}/${filename}`;

  try {
    const res = await fetch(`/api/assets/read?category=${encodeURIComponent(category)}&filename=${encodeURIComponent(filename)}`);
    const data = await res.json();
    if (readerEl) {
      readerEl.textContent = data.content || "Empty card content.";
    }
  } catch (err) {
    if (readerEl) readerEl.textContent = "Failed to load card content: " + err.message;
  }
}


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
            const changed = new Set();
            if (data.opcode !== undefined) changed.add(data.opcode);
            if (data.opcode_name) changed.add(data.opcode_name);
            inspectEntity(activeEntityId, changed);
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
  if (role === "nostra") prefix = "[NOSTRA]";
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
  setupDualViewInspector();

  const btnToggleDrawer = document.getElementById("btn-toggle-engine-drawer");
  const engineDrawer = document.getElementById("engine-settings-drawer");
  const chevron = document.getElementById("engine-drawer-chevron");

  if (btnToggleDrawer && engineDrawer) {
    btnToggleDrawer.addEventListener("click", () => {
      const isHidden = engineDrawer.style.display === "none" || !engineDrawer.style.display;
      engineDrawer.style.display = isHidden ? "block" : "none";
      if (chevron) chevron.textContent = isHidden ? "▲" : "▼";
    });
  }


  addSafeListener("btn-flush-scratchpad", "click", async () => {
    const hiddenInp = document.getElementById("entity_id");
    const id = activeEntityId || (hiddenInp ? hiddenInp.value : null) || "MadBrad-Nostra-01";
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
    hydrateEntityConfig(val);
    inspectEntity(val);
  });

  const presetEl = document.getElementById("select-provider-preset");
  const modelNameEl = document.getElementById("input-model-name");
  const keyInput = document.getElementById("input-api-key");
  const endpointInput = document.getElementById("input-endpoint-url");
  const btnSaveModel = document.getElementById("btn-save-entity-model");

  const syncActiveEntityConfig = () => {
    const p = presetEl ? presetEl.value : "fast";
    let m = modelNameEl ? modelNameEl.value.trim() : "";
    const k = keyInput ? keyInput.value.trim() : "";
    let ep = endpointInput ? endpointInput.value.trim() : "";

    if (p === "groq" && !m) m = "llama-3.3-70b-versatile";
    if (p === "groq" && !ep) ep = "https://api.groq.com/openai/v1";
    if (p === "gemini" && !m) m = "gemini-2.5-flash";
    if (p === "anthropic" && !m) m = "claude-3-5-haiku-20241022";
    if (p === "ollama" && !m) m = "qwen2.5:0.5b";

    saveEntityConfig(activeEntityId, {
      provider: p,
      model_name: m,
      api_key: k,
      endpoint_url: ep
    });

    if (endpointInput) {
      endpointInput.style.display = (p === "custom" || p === "groq" || p === "openai") ? "block" : "none";
    }
  };

  if (presetEl) {
    presetEl.addEventListener("change", () => {
      const p = presetEl.value;
      if (p === "groq" && modelNameEl && !modelNameEl.value) modelNameEl.value = "llama-3.3-70b-versatile";
      if (p === "groq" && endpointInput && !endpointInput.value) endpointInput.value = "https://api.groq.com/openai/v1";
      syncActiveEntityConfig();
    });
  }

  if (modelNameEl) {
    modelNameEl.addEventListener("keypress", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        syncActiveEntityConfig();
        appendTerminalLine("system", `Saved Model Config for '${activeEntityId}': ${modelNameEl.value || 'default'}`);
      }
    });
    modelNameEl.addEventListener("blur", syncActiveEntityConfig);
  }

  if (btnSaveModel) {
    btnSaveModel.addEventListener("click", () => {
      syncActiveEntityConfig();
      appendTerminalLine("system", `Saved Model Config for '${activeEntityId}': ${modelNameEl ? modelNameEl.value : 'default'}`);
    });
  }

  if (keyInput) keyInput.addEventListener("input", syncActiveEntityConfig);
  if (endpointInput) endpointInput.addEventListener("input", syncActiveEntityConfig);

  // Entity Actions Modal Handlers
  const entityActionsModal = document.getElementById("entity-actions-modal-overlay");
  const btnOpenEntityActions = document.getElementById("btn-open-entity-actions");
  const btnCloseEntityActions = document.getElementById("btn-close-entity-actions-modal");
  const entityTargetIdEl = document.getElementById("entity-actions-target-id");
  const aliasInput = document.getElementById("input-entity-alias");
  const renameForm = document.getElementById("entity-rename-form");
  const btnArchiveEntity = document.getElementById("btn-archive-entity");
  const btnDeleteEntity = document.getElementById("btn-delete-entity-prompt");

  if (btnOpenEntityActions && entityActionsModal) {
    btnOpenEntityActions.addEventListener("click", () => {
      if (entityTargetIdEl) {
        const alias = getEntityAlias(activeEntityId);
        entityTargetIdEl.textContent = alias ? `${alias} (${activeEntityId})` : activeEntityId;
      }
      if (aliasInput) {
        aliasInput.value = getEntityAlias(activeEntityId);
      }
      if (btnArchiveEntity) {
        const archived = isEntityArchived(activeEntityId);
        btnArchiveEntity.textContent = archived ? "Un-archive Entity" : "Archive Entity";
      }
      entityActionsModal.style.display = "flex";
    });
  }

  if (btnCloseEntityActions && entityActionsModal) {
    btnCloseEntityActions.addEventListener("click", () => {
      entityActionsModal.style.display = "none";
    });
  }

  if (entityActionsModal) {
    entityActionsModal.addEventListener("click", (e) => {
      if (e.target === entityActionsModal) entityActionsModal.style.display = "none";
    });
  }

  if (renameForm) {
    renameForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const newAlias = aliasInput ? aliasInput.value.trim() : "";
      setEntityAlias(activeEntityId, newAlias);
      try {
        await fetch(`/api/entities/${activeEntityId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ alias: newAlias })
        });
      } catch (err) {}

      appendTerminalLine("system", `Updated alias for entity '${activeEntityId}': '${newAlias || "None"}'`);
      if (entityActionsModal) entityActionsModal.style.display = "none";
      loadEntities(activeEntityId);
    });
  }

  if (btnArchiveEntity) {
    btnArchiveEntity.addEventListener("click", async () => {
      const current = isEntityArchived(activeEntityId);
      const next = !current;
      setEntityArchived(activeEntityId, next);
      try {
        await fetch(`/api/entities/${activeEntityId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ is_archived: next })
        });
      } catch (err) {}

      appendTerminalLine("system", `${next ? "Archived" : "Un-archived"} entity '${activeEntityId}'.`);
      if (entityActionsModal) entityActionsModal.style.display = "none";
      loadEntities("MadBrad-Nostra-01");
    });
  }

  if (btnDeleteEntity) {
    btnDeleteEntity.addEventListener("click", async () => {
      const targetToDelete = activeEntityId;
      if (!confirm(`Permanently delete entity '${targetToDelete}' and purge all LMDB state registers & history?`)) {
        return;
      }

      try {
        const res = await fetch(`/api/entities/${targetToDelete}`, {
          method: "DELETE"
        });
        const data = await res.json();
        
        // Clean up localStorage
        localStorage.removeItem(`dume_entity_cfg_${targetToDelete}`);
        localStorage.removeItem(`dume_entity_alias_${targetToDelete}`);
        localStorage.removeItem(`dume_entity_archived_${targetToDelete}`);
        
        const customEntities = getStoredCustomEntities().filter(e => e !== targetToDelete);
        localStorage.setItem("dume_custom_entities", JSON.stringify(customEntities));

        appendTerminalLine("system", `Purged Entity '${targetToDelete}' from LMDB (${data.active_deleted || 0} registers, ${data.history_deleted || 0} audit logs deleted).`);
        if (entityActionsModal) entityActionsModal.style.display = "none";
        await loadEntities("MadBrad-Nostra-01");
      } catch (err) {
        alert("Failed to delete entity: " + err.message);
      }
    });
  }

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

    appendTerminalLine("system", `Created new Entity: '${name}'. Selected as active for Nostra.`);
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

  addSafeListener("btn-wake-nostra", "click", () => {
    const turnInput = document.getElementById("turn-input");
    const chatForm = document.getElementById("chat-turn-form");
    if (turnInput) turnInput.value = "box is the game.";
    if (chatForm) {
      if (typeof chatForm.requestSubmit === "function") {
        chatForm.requestSubmit();
      } else {
        chatForm.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
      }
    }
  });

  addSafeListener("chat-turn-form", "submit", async (e) => {
    e.preventDefault();
    const hiddenInp = document.getElementById("entity_id");
    const turnInputEl = document.getElementById("turn-input");

    const entityInput = (hiddenInp ? hiddenInp.value.trim() : "") || activeEntityId || "MadBrad-Nostra-01";
    const turnInput = turnInputEl ? turnInputEl.value.trim() : "";

    const cfg = getEntityConfig(entityInput);
    const provider = cfg.provider || "fast";
    const modelName = cfg.model_name || "";
    const apiKey = cfg.api_key || "";
    const endpointUrl = cfg.endpoint_url || "";

    if (!turnInput) return;

    appendTerminalLine("user", turnInput);
    if (turnInputEl) turnInputEl.value = "";

    const displayModel = modelName || provider;
    const thinkingLine = appendTerminalLine("system", `Nostra is thinking (${displayModel} synthesis)...`);

    try {
      const res = await fetch("/api/session/turn", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          entity_id: entityInput,
          user_text: turnInput,
          provider: provider,
          model_name: modelName,
          api_key: apiKey,
          endpoint_url: endpointUrl
        })
      });

      const data = await res.json();
      if (thinkingLine) thinkingLine.remove();

      if ('error' in data) {
        appendTerminalLine("system", `[Server Error] ${data.error}`);
        if (data.synthetic_response) {
          appendTerminalLine("nostra", data.synthetic_response);
        }
        console.error("[Nostra Server Traceback]", data.traceback || "No traceback");
        return;
      }

      if (!res.ok) {
        appendTerminalLine("system", "Error: " + (data.detail || "Failed to dispatch turn"));
        return;
      }

      activeEntityId = data.entity_id || entityInput;
      if (hiddenInp) hiddenInp.value = activeEntityId;

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

  // Quick Start Guide Walkthrough Modal Handlers
  const guideModalOverlay = document.getElementById("guide-modal-overlay");
  const btnOpenGuideModal = document.getElementById("btn-open-guide-modal");
  const btnCloseGuideModal = document.getElementById("btn-close-guide-modal");
  const btnGuideCloseCta = document.getElementById("btn-guide-close-cta");

  if (btnOpenGuideModal && guideModalOverlay) {
    btnOpenGuideModal.addEventListener("click", () => {
      guideModalOverlay.style.display = "flex";
    });
  }

  if (btnCloseGuideModal && guideModalOverlay) {
    btnCloseGuideModal.addEventListener("click", () => {
      guideModalOverlay.style.display = "none";
    });
  }

  if (btnGuideCloseCta && guideModalOverlay) {
    btnGuideCloseCta.addEventListener("click", () => {
      guideModalOverlay.style.display = "none";
    });
  }

  if (guideModalOverlay) {
    guideModalOverlay.addEventListener("click", (e) => {
      if (e.target === guideModalOverlay) {
        guideModalOverlay.style.display = "none";
      }
    });
  }

  // Guide Action Buttons (Step 1, Step 2, Step 3)
  const btnGuideStep1 = document.getElementById("btn-guide-step1-action");
  if (btnGuideStep1) {
    btnGuideStep1.addEventListener("click", () => {
      if (guideModalOverlay) guideModalOverlay.style.display = "none";
      const intakeModal = document.getElementById("intake-modal");
      if (intakeModal) intakeModal.style.display = "flex";
    });
  }

  const btnGuideStep2 = document.getElementById("btn-guide-step2-action");
  if (btnGuideStep2) {
    btnGuideStep2.addEventListener("click", () => {
      if (guideModalOverlay) guideModalOverlay.style.display = "none";
      if (connectModalOverlay) connectModalOverlay.style.display = "flex";
    });
  }

  const btnGuideStep3 = document.getElementById("btn-guide-step3-action");
  if (btnGuideStep3) {
    btnGuideStep3.addEventListener("click", () => {
      if (guideModalOverlay) guideModalOverlay.style.display = "none";
      const turnInput = document.getElementById("turn-input");
      if (turnInput) {
        turnInput.value = "box is the game.";
        turnInput.focus();
      }
    });
  }

  // Visual Agent Picker Grid Handlers
  const agentCards = document.querySelectorAll(".agent-card");
  agentCards.forEach(card => {
    card.addEventListener("click", () => {
      agentCards.forEach(c => c.classList.remove("active"));
      card.classList.add("active");

      const agentKey = card.getAttribute("data-agent");
      document.querySelectorAll(".agent-pane").forEach(pane => {
        pane.style.display = "none";
        pane.classList.remove("active");
      });

      const targetPane = document.getElementById(`pane-agent-${agentKey}`);
      if (targetPane) {
        targetPane.style.display = "block";
        targetPane.classList.add("active");
      }
    });
  });

  // Claude Desktop OS Buttons (macOS vs Windows)
  const btnClaudeMac = document.getElementById("btn-claude-mac");
  const btnClaudeWin = document.getElementById("btn-claude-win");
  const claudeMacWrap = document.getElementById("claude-mac-wrap");
  const claudeWinWrap = document.getElementById("claude-win-wrap");

  if (btnClaudeMac && btnClaudeWin) {
    btnClaudeMac.addEventListener("click", () => {
      btnClaudeMac.classList.add("active");
      btnClaudeWin.classList.remove("active");
      if (claudeMacWrap) claudeMacWrap.style.display = "block";
      if (claudeWinWrap) claudeWinWrap.style.display = "none";
    });

    btnClaudeWin.addEventListener("click", () => {
      btnClaudeWin.classList.add("active");
      btnClaudeMac.classList.remove("active");
      if (claudeWinWrap) claudeWinWrap.style.display = "block";
      if (claudeMacWrap) claudeMacWrap.style.display = "none";
    });
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (connectModalOverlay && connectModalOverlay.style.display !== "none") {
        connectModalOverlay.style.display = "none";
      }
      if (guideModalOverlay && guideModalOverlay.style.display !== "none") {
        guideModalOverlay.style.display = "none";
      }
    }
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

      if (targetView === "view-knowledge") {
        loadKnowledgeAssets();
      }
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

  document.querySelectorAll(".knowledge-filter-pill").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".knowledge-filter-pill").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentKnowledgeFilter = btn.getAttribute("data-filter") || "all";
      renderKnowledgeExplorer();
    });
  });

  const searchInput = document.getElementById("input-schema-search");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      currentSearch = e.target.value.trim();
      renderSchemaManagerTable();
    });
  }

  const kSearch = document.getElementById("input-knowledge-search");
  if (kSearch) {
    kSearch.addEventListener("input", (e) => {
      currentKnowledgeSearch = e.target.value.trim();
      renderKnowledgeExplorer();
    });
  }

  addSafeListener("btn-refresh-knowledge", "click", loadKnowledgeAssets);


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

function classifyRegisterCategory(opcodeName, opcode) {
  const name = (opcodeName || "").toUpperCase();
  const memoirKeys = new Set([
    "LINEAGE", "IDENTIFIED", "WORDS", "MADBRAD", "RECOGNITION", "CONTINUES",
    "EMERGES", "AAR", "ENTITY", "POSITION", "FRAMING", "CORRECTED", "ARCHITECTURE",
    "PROGRAM", "RESEARCH", "RECORD", "EXPERIMENT", "TASK", "THAT", "NOW"
  ]);
  const narrativeKeys = new Set([
    "FOOD", "NEED", "GRILL", "KIND", "MOVIE", "DEUCE", "PRESENTATION", "KEV",
    "SPECIAL", "EVENT", "UNCLE", "STOP", "CHARACTERS", "READS", "RIBCAGE", "FENCE",
    "TRAYS", "COOKOUT", "CHAIR", "INSIDE", "DINNER", "JULY", "SALAD", "TONGUE",
    "COOLER", "PORK", "SEVEN", "CARLITOS", "MAN", "CARLOS", "TABLE", "DAY", "MIX",
    "OPEN", "DISCOVERY", "CODE", "CLIMAX", "CARD", "WHICH"
  ]);
  const fileKeys = new Set([
    "ASSET_HASH", "ASSET_PATH", "FILE_NAME", "WORD_COUNT", "LINE_COUNT",
    "SECTION_1", "SECTION_2", "SECTION_3", "SECTION_4", "SECTION_5",
    "SECTION_6", "SECTION_7", "SECTION_8", "COLUMNS", "PAGE_COUNT"
  ]);
  const systemKeys = new Set([
    "COLLABORATOR_NAME", "COLLABORATOR_STATUS", "FAST_PATH", "TOKEN_COUNT",
    "ACTIVE_MODE", "LATENCY", "MODEL_NAME"
  ]);

  if (memoirKeys.has(name)) return "memoir";
  if (narrativeKeys.has(name)) return "narrative";
  if (fileKeys.has(name) || name.startsWith("SECTION_") || name.startsWith("SAMPLE_")) return "files";
  if (systemKeys.has(name)) return "system";
  if (opcode >= 3000) return "files";
  if (opcode >= 2000 && opcode < 2350) return "memoir";
  if (opcode >= 2350 && opcode < 2450) return "narrative";
  return "system";
}

function updateCategoryChipCounts(pages) {
  let counts = { all: pages.length, memoir: 0, system: 0, narrative: 0, files: 0 };
  pages.forEach(p => {
    const name = (p.decoded && p.decoded.opcode_name) || `OP_${p.opcode}`;
    const cat = classifyRegisterCategory(name, p.opcode);
    if (counts[cat] !== undefined) counts[cat]++;
  });

  const chipAll = document.getElementById("chip-count-all");
  const chipMemoir = document.getElementById("chip-count-memoir");
  const chipSystem = document.getElementById("chip-count-system");
  const chipNarrative = document.getElementById("chip-count-narrative");
  const chipFiles = document.getElementById("chip-count-files");
  const studioTotal = document.getElementById("studio-total-badge");
  const fuelRegs = document.getElementById("fuel-gauge-registers-val");

  if (chipAll) chipAll.textContent = counts.all;
  if (chipMemoir) chipMemoir.textContent = counts.memoir;
  if (chipSystem) chipSystem.textContent = counts.system;
  if (chipNarrative) chipNarrative.textContent = counts.narrative;
  if (chipFiles) chipFiles.textContent = counts.files;
  if (studioTotal) studioTotal.textContent = `${counts.all} Registers`;
  if (fuelRegs) fuelRegs.innerHTML = `${counts.all} <span style="font-size: 0.72rem; color: var(--text-muted); font-weight: 500;">registers</span>`;
}

function getFilteredRegisterPages() {
  const query = (currentSearchQuery || "").trim().toLowerCase();
  return cachedEntityPages.filter(p => {
    const decoded = p.decoded || {};
    const name = (decoded.opcode_name || `OP_${p.opcode}`).toLowerCase();
    const val = String(decoded.human_value !== undefined ? decoded.human_value : (p.value_hex || '')).toLowerCase();
    const opStr = String(p.opcode);
    const cat = classifyRegisterCategory(name, p.opcode);

    const matchesCategory = currentCategoryFilter === "all" || cat === currentCategoryFilter;
    const matchesSearch = !query || name.includes(query) || val.includes(query) || opStr.includes(query);
    return matchesCategory && matchesSearch;
  });
}

function setupStudioRegisterSuite() {
  // Category Chips click handlers
  const chips = document.querySelectorAll(".studio-chip");
  chips.forEach(chip => {
    chip.addEventListener("click", () => {
      chips.forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      currentCategoryFilter = chip.getAttribute("data-category") || "all";
      renderActiveInspectorView();
    });
  });

  // Search input handler
  const searchInput = document.getElementById("studio-search-input");
  const clearBtn = document.getElementById("btn-studio-search-clear");

  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      currentSearchQuery = e.target.value;
      if (clearBtn) {
        clearBtn.style.display = currentSearchQuery ? "block" : "none";
      }
      renderActiveInspectorView();
    });
  }

  if (clearBtn && searchInput) {
    clearBtn.addEventListener("click", () => {
      searchInput.value = "";
      currentSearchQuery = "";
      clearBtn.style.display = "none";
      renderActiveInspectorView();
    });
  }

  // Export Registers Button
  const btnExportRegs = document.getElementById("btn-export-registers-json");
  if (btnExportRegs) {
    btnExportRegs.addEventListener("click", () => {
      const exportData = {
        entity_id: activeEntityId,
        timestamp: new Date().toISOString(),
        registers_count: cachedEntityPages.length,
        registers: cachedEntityPages.map(p => ({
          opcode: p.opcode,
          name: (p.decoded && p.decoded.opcode_name) || `OP_${p.opcode}`,
          value: (p.decoded && p.decoded.human_value !== undefined) ? p.decoded.human_value : p.value_hex,
          timestamp: p.timestamp,
          data_type: (p.decoded && p.decoded.data_type) || p.data_type
        }))
      };
      const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `dumedb_${activeEntityId}_registers_${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
    });
  }
}

function setupDualViewInspector() {
  const btnCards = document.getElementById("btn-view-cards");
  const btnReadable = document.getElementById("btn-view-readable");
  const btnHex = document.getElementById("btn-view-hex");

  const cardsPane = document.getElementById("readable-registers-cards-container");
  const readablePane = document.getElementById("readable-registers-view");
  const hexPane = document.getElementById("hex-dump-view-container");

  const activateTab = (tabName) => {
    currentInspectorTab = tabName;
    if (btnCards) btnCards.classList.toggle("active", tabName === "cards");
    if (btnReadable) btnReadable.classList.toggle("active", tabName === "readable");
    if (btnHex) btnHex.classList.toggle("active", tabName === "hex");

    if (cardsPane) cardsPane.style.display = tabName === "cards" ? "grid" : "none";
    if (readablePane) readablePane.style.display = tabName === "readable" ? "block" : "none";
    if (hexPane) hexPane.style.display = tabName === "hex" ? "block" : "none";

    renderActiveInspectorView();
  };

  if (btnCards) btnCards.addEventListener("click", () => activateTab("cards"));
  if (btnReadable) btnReadable.addEventListener("click", () => activateTab("readable"));
  if (btnHex) btnHex.addEventListener("click", () => activateTab("hex"));
}

function renderActiveInspectorView(changedOpcodes = new Set()) {
  const filtered = getFilteredRegisterPages();
  const matchCountEl = document.getElementById("studio-filter-match-count");
  if (matchCountEl) {
    matchCountEl.textContent = `Showing ${filtered.length} of ${cachedEntityPages.length}`;
  }

  if (currentInspectorTab === "cards") {
    renderRegistersCardsGrid(filtered, changedOpcodes);
  } else if (currentInspectorTab === "readable") {
    renderReadableRegistersTable(filtered, changedOpcodes);
  } else {
    renderHexDumpContainer(filtered, changedOpcodes);
  }
}

function renderRegistersCardsGrid(pages, changedOpcodes = new Set()) {
  const container = document.getElementById("readable-registers-cards-container");
  if (!container) return;
  container.innerHTML = "";

  if (!pages || pages.length === 0) {
    if (cachedEntityPages.length === 0) {
      container.innerHTML = `
        <div class="empty-state-card">
          <div class="empty-state-icon">✨</div>
          <div class="empty-state-title">No Memory Registers in This Entity Yet</div>
          <div class="empty-state-desc">
            This entity is clean and ready. Ingest a document, drop project notes, or chat with Nostra to mint your first deterministic 32-byte memory registers with 0 prompt token burn.
          </div>
          <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; justify-content: center; margin-top: 0.25rem;">
            <button type="button" class="empty-state-btn" id="btn-empty-intake-cta">
              📥 Ingest First Document
            </button>
            <button type="button" class="btn-secondary" id="btn-empty-guide-cta" style="padding: 0.5rem 1rem; font-size: 0.85rem; border-radius: 8px;">
              💡 How It Works
            </button>
          </div>
        </div>
      `;
      const btnIntake = container.querySelector("#btn-empty-intake-cta");
      if (btnIntake) {
        btnIntake.addEventListener("click", () => {
          const intakeModal = document.getElementById("intake-modal");
          if (intakeModal) intakeModal.style.display = "flex";
        });
      }
      const btnGuide = container.querySelector("#btn-empty-guide-cta");
      if (btnGuide) {
        btnGuide.addEventListener("click", () => {
          const guideModal = document.getElementById("guide-modal-overlay");
          if (guideModal) guideModal.style.display = "flex";
        });
      }
    } else {
      container.innerHTML = `
        <div style="grid-column: 1 / -1; text-align: center; color: var(--text-muted); padding: 3rem 1.5rem; font-size: 0.88rem; background: rgba(255,255,255,0.02); border-radius: 8px; border: 1px dashed var(--border-color);">
          <div style="font-size: 1.5rem; margin-bottom: 0.5rem;">🔍</div>
          <div style="font-weight: 600; color: var(--text-main); margin-bottom: 0.25rem;">No registers match active filter</div>
          <div style="color: var(--text-dim); margin-bottom: 0.75rem;">Try selecting "✨ All" or clearing your search term.</div>
          <button type="button" class="btn-secondary" id="btn-clear-empty-filter" style="font-size: 0.78rem; padding: 0.35rem 0.85rem;">Clear Filters</button>
        </div>
      `;
      const clearBtn = container.querySelector("#btn-clear-empty-filter");
      if (clearBtn) {
        clearBtn.addEventListener("click", () => {
          const allChip = document.querySelector(".studio-chip[data-category='all']");
          if (allChip) allChip.click();
          const searchInput = document.getElementById("studio-search-input");
          if (searchInput) {
            searchInput.value = "";
            searchInput.dispatchEvent(new Event("input"));
          }
        });
      }
    }
    return;
  }

  const catBadgeLabels = {
    memoir: "📖 Memoir",
    narrative: "🎬 Narrative",
    files: "📄 File Asset",
    system: "⚙️ System"
  };

  pages.forEach(p => {
    const decoded = p.decoded || {};
    const opcodeName = decoded.opcode_name || `OP_${p.opcode}`;
    const dataType = decoded.data_type || p.data_type || "STRING_REF";
    const humanVal = decoded.human_value !== undefined ? decoded.human_value : (p.value_hex || '');
    const cat = classifyRegisterCategory(opcodeName, p.opcode);
    const ts = p.timestamp ? new Date(p.timestamp * 1000).toLocaleTimeString() : "--";

    const card = document.createElement("div");
    card.className = "register-card";
    if (changedOpcodes.has(p.opcode) || changedOpcodes.has(opcodeName)) {
      card.className += " row-pulse";
    }

    const safeVal = String(humanVal).replace(/"/g, '&quot;');

    card.innerHTML = `
      <div class="register-card-header">
        <span class="register-card-opcode">OP: ${p.opcode}</span>
        <span style="font-size: 0.68rem; background: rgba(255,255,255,0.06); padding: 0.1rem 0.4rem; border-radius: 4px; font-family: var(--font-mono); color: var(--text-muted);">${dataType}</span>
        <button type="button" class="btn-card-action btn-copy-card-val" title="Copy value to clipboard" style="margin-left: auto;">
          📋 Copy
        </button>
      </div>
      <div class="register-card-key">${opcodeName}</div>
      <div class="register-card-val" title="${safeVal}">${humanVal}</div>
      <div class="register-card-footer">
        <span style="color: var(--accent-cyan); font-weight: 600;">${catBadgeLabels[cat] || 'Register'}</span>
        <span>${ts}</span>
      </div>
    `;

    const copyBtn = card.querySelector(".btn-copy-card-val");
    if (copyBtn) {
      copyBtn.addEventListener("click", () => {
        navigator.clipboard.writeText(String(humanVal));
        copyBtn.textContent = "✓ Copied!";
        setTimeout(() => { copyBtn.textContent = "📋 Copy"; }, 1500);
      });
    }

    container.appendChild(card);
  });
}

function renderReadableRegistersTable(pages, changedOpcodes = new Set()) {
  const tbody = document.getElementById("readable-registers-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  if (!pages || pages.length === 0) {
    tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No active state registers match the criteria.</td></tr>`;
    return;
  }

  pages.forEach(page => {
    const tr = document.createElement("tr");
    const decoded = page.decoded || {};
    const opcodeName = decoded.opcode_name || `OP_${page.opcode}`;
    const dataType = decoded.data_type || page.data_type || "UNKNOWN";
    const humanVal = decoded.human_value !== undefined ? decoded.human_value : (page.value_hex || '');
    const ts = page.timestamp ? new Date(page.timestamp * 1000).toLocaleTimeString() : "--";

    if (changedOpcodes.has(page.opcode) || changedOpcodes.has(opcodeName)) {
      tr.className = "row-pulse";
    }

    tr.innerHTML = `
      <td><b style="color: var(--accent-amber); font-family: var(--font-mono);">${opcodeName}</b> <span style="font-size: 0.7rem; color: var(--text-dim);">(${page.opcode})</span></td>
      <td><span style="background: rgba(255,255,255,0.06); padding: 0.15rem 0.4rem; border-radius: 4px; font-size: 0.75rem; font-family: var(--font-mono);">${dataType}</span></td>
      <td><span style="color: var(--accent-emerald); font-weight: 600; font-family: var(--font-mono);">${humanVal}</span></td>
      <td style="text-align: right; color: var(--text-muted); font-size: 0.78rem;">${ts}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderHexDumpContainer(pages, changedOpcodes = new Set()) {
  const dumpContainer = document.getElementById("hex-dump-view");
  if (!dumpContainer) return;
  dumpContainer.innerHTML = "";

  if (!pages || pages.length === 0) {
    dumpContainer.innerHTML = `<div style="color: var(--text-muted);">No active state registers found for entity ${activeEntityId}</div>`;
    return;
  }

  pages.forEach(page => {
    const row = document.createElement("div");
    row.className = "hex-row";
    const decoded = page.decoded || {};
    const opcodeName = decoded.opcode_name || `OP_${page.opcode}`;
    const humanVal = decoded.human_value !== undefined ? decoded.human_value : (page.value_hex || '');

    if (changedOpcodes.has(page.opcode) || changedOpcodes.has(opcodeName)) {
      row.className += " row-pulse";
    }

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
    dumpContainer.appendChild(row);
  });
}

function updateTokenTelemetry(regCtxText) {
  const previewEl = document.getElementById("prompt-register-preview");
  const badgeEl = document.getElementById("token-telemetry-badge");

  if (previewEl) previewEl.textContent = regCtxText;

  const estTokens = regCtxText ? Math.ceil(regCtxText.length / 3.8) : 0;
  const delta = estTokens - lastTokenCount;
  lastTokenCount = estTokens;

  let deltaTag = "";
  if (delta > 0) {
    deltaTag = ` | <span style="color: var(--accent-emerald);">+${delta} tokens</span>`;
  } else if (delta < 0) {
    deltaTag = ` | <span style="color: var(--accent-rose);">${delta} tokens</span>`;
  }

  if (badgeEl) {
    badgeEl.innerHTML = `[DUME_STATE: ~${estTokens} tokens${deltaTag}]`;
  }
}

async function inspectEntity(entityId, changedOpcodes = new Set()) {
  try {
    const targetId = entityId || activeEntityId || "MadBrad-Nostra-01";
    const res = await fetch(`/api/inspector/hex/${targetId}`);
    const data = await res.json();

    cachedEntityPages = data.memory_pages || [];

    updateCategoryChipCounts(cachedEntityPages);
    renderActiveInspectorView(changedOpcodes);

    let registersText = [];
    cachedEntityPages.forEach(page => {
      const decoded = page.decoded || {};
      const opcodeName = decoded.opcode_name || `OP_${page.opcode}`;
      const humanVal = decoded.human_value !== undefined ? decoded.human_value : (page.value_hex || '');
      registersText.push(`${opcodeName}=${humanVal}`);
    });

    if (cachedEntityPages.length === 0) {
      updateTokenTelemetry("No active registers.");
    } else {
      const shortId = targetId.substring(0, 8);
      const regCtx = `[DUME_STATE entity=${shortId}] ${registersText.join(" | ")} [/DUME_STATE]`;
      updateTokenTelemetry(regCtx);
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
      entitySelect.value = activeEntityId || "MadBrad-Nostra-01";
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

      const targetEntity = (entitySelect && entitySelect.value) || activeEntityId || "MadBrad-Nostra-01";
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

  // Multimodal File Intake Dropzone & Review Modal Handlers
  const intakeDropzone = document.getElementById("intake-dropzone");
  const intakeFileInput = document.getElementById("intake-file-input");
  const btnBrowseIntake = document.getElementById("btn-browse-intake-file");

  const intakeReviewModal = document.getElementById("file-intake-review-modal-overlay");
  const btnCloseIntakeReview = document.getElementById("btn-close-intake-review-modal");
  const btnCancelIntakeReview = document.getElementById("btn-cancel-intake-review");
  const btnCommitIntakeReview = document.getElementById("btn-commit-intake-review");

  const intakeModalFilename = document.getElementById("intake-modal-filename");
  const intakeModalHash = document.getElementById("intake-modal-hash");
  const intakeCandidatesTbody = document.getElementById("intake-candidates-tbody");
  const intakeCountLabel = document.getElementById("intake-candidate-count-label");
  const intakeSelectAll = document.getElementById("intake-select-all-candidates");

  let currentIntakeCandidates = [];
  let currentIntakeFilename = "";

  const handleFileUpload = async (file) => {
    if (!file) return;
    const targetEntity = activeEntityId || "MadBrad-Nostra-01";
    appendTerminalLine("system", `Uploading '${file.name}' for intake extraction...`);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`/api/entities/${targetEntity}/intake/upload`, {
        method: "POST",
        body: formData
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        alert("File intake upload failed: " + (data.detail || JSON.stringify(data)));
        return;
      }

      currentIntakeCandidates = data.candidates || [];
      currentIntakeFilename = data.filename;

      if (intakeModalFilename) intakeModalFilename.textContent = data.filename;
      if (intakeModalHash) intakeModalHash.textContent = (data.asset_hash || "").slice(0, 16) + "...";

      if (intakeCandidatesTbody) {
        intakeCandidatesTbody.innerHTML = "";
        currentIntakeCandidates.forEach((candidate, idx) => {
          const tr = document.createElement("tr");
          tr.innerHTML = `
            <td style="text-align: center;"><input type="checkbox" class="intake-candidate-cb" data-index="${idx}" checked></td>
            <td><input type="text" class="intake-key-input" data-index="${idx}" value="${candidate.key}" style="width: 95%; font-family: var(--font-mono); font-size: 0.8rem; padding: 0.2rem 0.4rem; background: rgba(0,0,0,0.2);"></td>
            <td><input type="text" class="intake-val-input" data-index="${idx}" value="${candidate.value}" style="width: 95%; font-family: var(--font-mono); font-size: 0.8rem; padding: 0.2rem 0.4rem; background: rgba(0,0,0,0.2);"></td>
          `;
          intakeCandidatesTbody.appendChild(tr);
        });
      }

      if (intakeCountLabel) intakeCountLabel.textContent = `${currentIntakeCandidates.length} candidate registers detected`;
      if (modal) modal.style.display = "none";
      if (intakeReviewModal) intakeReviewModal.style.display = "flex";

    } catch (err) {
      alert("File intake failed: " + err.message);
    }
  };

  if (btnBrowseIntake && intakeFileInput) {
    btnBrowseIntake.addEventListener("click", (e) => {
      e.stopPropagation();
      intakeFileInput.click();
    });
  }

  if (intakeDropzone && intakeFileInput) {
    intakeDropzone.addEventListener("click", () => intakeFileInput.click());
    intakeFileInput.addEventListener("change", (e) => {
      if (e.target.files && e.target.files.length > 0) {
        handleFileUpload(e.target.files[0]);
      }
    });

    intakeDropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      intakeDropzone.style.borderColor = "var(--primary)";
      intakeDropzone.style.background = "rgba(59, 130, 246, 0.1)";
    });

    intakeDropzone.addEventListener("dragleave", (e) => {
      e.preventDefault();
      intakeDropzone.style.borderColor = "var(--border-color)";
      intakeDropzone.style.background = "rgba(255,255,255,0.02)";
    });

    intakeDropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      intakeDropzone.style.borderColor = "var(--border-color)";
      intakeDropzone.style.background = "rgba(255,255,255,0.02)";
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleFileUpload(e.dataTransfer.files[0]);
      }
    });
  }

  // Sidebar Intake Dropzone Wiring
  const sidebarDropzone = document.getElementById("sidebar-intake-dropzone");
  const sidebarFileInput = document.getElementById("sidebar-intake-file-input");
  const btnSidebarBrowse = document.getElementById("btn-sidebar-browse-intake");

  if (btnSidebarBrowse && sidebarFileInput) {
    btnSidebarBrowse.addEventListener("click", (e) => {
      e.stopPropagation();
      sidebarFileInput.click();
    });
  }

  if (sidebarDropzone && sidebarFileInput) {
    sidebarDropzone.addEventListener("click", () => sidebarFileInput.click());
    sidebarFileInput.addEventListener("change", (e) => {
      if (e.target.files && e.target.files.length > 0) {
        handleFileUpload(e.target.files[0]);
      }
    });

    sidebarDropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      sidebarDropzone.style.borderColor = "var(--primary)";
      sidebarDropzone.style.background = "rgba(59, 130, 246, 0.1)";
    });

    sidebarDropzone.addEventListener("dragleave", (e) => {
      e.preventDefault();
      sidebarDropzone.style.borderColor = "var(--border-color)";
      sidebarDropzone.style.background = "rgba(255,255,255,0.02)";
    });

    sidebarDropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      sidebarDropzone.style.borderColor = "var(--border-color)";
      sidebarDropzone.style.background = "rgba(255,255,255,0.02)";
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleFileUpload(e.dataTransfer.files[0]);
      }
    });
  }

  if (intakeSelectAll) {
    intakeSelectAll.addEventListener("change", () => {
      const cbs = document.querySelectorAll(".intake-candidate-cb");
      cbs.forEach(cb => cb.checked = intakeSelectAll.checked);
    });
  }

  const closeReviewModal = () => {
    if (intakeReviewModal) intakeReviewModal.style.display = "none";
  };

  if (btnCloseIntakeReview) btnCloseIntakeReview.addEventListener("click", closeReviewModal);
  if (btnCancelIntakeReview) btnCancelIntakeReview.addEventListener("click", closeReviewModal);

  if (btnCommitIntakeReview) {
    btnCommitIntakeReview.addEventListener("click", async () => {
      const targetEntity = activeEntityId || "MadBrad-Nostra-01";
      const cbs = document.querySelectorAll(".intake-candidate-cb");
      const approvedRegisters = [];

      cbs.forEach(cb => {
        if (cb.checked) {
          const idx = cb.getAttribute("data-index");
          const keyInput = document.querySelector(`.intake-key-input[data-index="${idx}"]`);
          const valInput = document.querySelector(`.intake-val-input[data-index="${idx}"]`);
          const k = keyInput ? keyInput.value.trim() : "";
          const v = valInput ? valInput.value.trim() : "";
          if (k && v) {
            approvedRegisters.push({ key: k, value: v });
          }
        }
      });

      if (approvedRegisters.length === 0) {
        alert("Please select at least one register key=value pair to commit.");
        return;
      }

      btnCommitIntakeReview.disabled = true;
      btnCommitIntakeReview.textContent = "⏳ Committing...";

      try {
        const flushCb = document.getElementById("intake-modal-flush-scratchpad");
        const shouldFlush = flushCb ? flushCb.checked : false;

        const res = await fetch(`/api/entities/${targetEntity}/intake/commit`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            registers: approvedRegisters,
            flush_scratchpad: shouldFlush
          })
        });
        const resText = await res.text();
        let data;
        try {
          data = JSON.parse(resText);
        } catch (e) {
          throw new Error(`Server returned HTTP ${res.status}: ${resText.slice(0, 150)}`);
        }

        if (res.ok && data.success) {
          appendTerminalLine("system", `File Intake committed for '${currentIntakeFilename}': ${data.committed_count} registers written to LMDB.`);
          closeReviewModal();
          await inspectEntity(targetEntity);
          loadHealth();
        } else {
          alert("Intake commit error: " + (data.detail || JSON.stringify(data)));
        }
      } catch (err) {
        alert("Failed to commit intake registers: " + err.message);
      } finally {
        btnCommitIntakeReview.disabled = false;
        btnCommitIntakeReview.textContent = "Commit to Registers";
      }
    });
  }
}
