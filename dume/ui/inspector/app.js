let activeEntityId = "";
let schemaOpcodes = [];
let ws = null;
let cachedEntityPages = [];
let lastTokenCount = 0;
let currentInspectorTab = "cards";
let currentCategoryFilter = "all";
let currentSearchQuery = "";


document.addEventListener("DOMContentLoaded", async () => {
  try { setupEventListeners(); } catch(e) { console.error("EventListeners init error:", e); }
  try { setupDualViewInspector(); } catch(e) { console.error("DualView init error:", e); }
  try { setupStudioRegisterSuite(); } catch(e) { console.error("StudioSuite init error:", e); }
  try { setupIntakeModal(); } catch(e) { console.error("IntakeModal init error:", e); }
  try { setupWebSocket(); } catch(e) { console.error("WS init error:", e); }
  try { loadHealth(); } catch(e) { console.error("Health init error:", e); }
  try { loadSchema(); } catch(e) { console.error("Schema init error:", e); }
  try { loadProxyConfig(); } catch(e) { console.error("Proxy config init error:", e); }
  try { setupOnboardingModal(); } catch(e) { console.error("Onboarding modal init error:", e); }
  try { setupCabinetEventListeners(); } catch(e) { console.error("Cabinet init error:", e); }
  try { await checkOnboarding(); } catch(e) { console.error("Onboarding status check error:", e); }
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

    const configuredEntity = (window.dumeUserConfig && window.dumeUserConfig.entity_id) || null;
    const rawEntities = Array.isArray(data.entities) ? data.entities : [];
    const customEntities = getStoredCustomEntities();

    const entitySet = new Set();
    if (selectedIdToSet) entitySet.add(selectedIdToSet);
    if (configuredEntity) entitySet.add(configuredEntity);

    rawEntities.forEach(id => {
      if (!configuredEntity || id === configuredEntity || !id.toLowerCase().includes("nostra")) {
        entitySet.add(id);
      }
    });
    customEntities.forEach(id => {
      if (!configuredEntity || id === configuredEntity || id === selectedIdToSet) {
        entitySet.add(id);
      }
    });

    if (entitySet.size === 0) {
      entitySet.add(configuredEntity || "Default-Agent-01");
    }

    const combinedList = Array.from(entitySet);
    const targetVal = selectedIdToSet || (configuredEntity && entitySet.has(configuredEntity) ? configuredEntity : (activeEntityId && entitySet.has(activeEntityId) ? activeEntityId : combinedList[0]));

    if (select) {
      select.innerHTML = "";
      combinedList.forEach(id => {
        const isArchived = isEntityArchived(id);
        if (isArchived && id !== targetVal) return;

        const alias = getEntityAlias(id);
        const opt = document.createElement("option");
        opt.value = id;
        if (id === configuredEntity) {
          opt.textContent = `⭐ ${alias || configuredEntity} (Primary Workspace)`;
        } else if (alias) {
          opt.textContent = `📁 ${alias} (${id})`;
        } else {
          opt.textContent = `📁 ${id}`;
        }
        if (id === targetVal) opt.selected = true;
        select.appendChild(opt);
      });
    }

    const activeIdEl = document.getElementById("workspace-active-id-text");
    if (activeIdEl) {
      activeIdEl.textContent = targetVal;
    }

    if (hiddenInput) {
      hiddenInput.value = targetVal;
    }
    activeEntityId = targetVal;
    hydrateEntityConfig(targetVal);
    await inspectEntity(targetVal);
  } catch (err) {
    console.error("Failed to load entity IDs:", err);
    activeEntityId = selectedIdToSet || (window.dumeUserConfig && window.dumeUserConfig.entity_id) || "Default-Agent-01";
    const select = document.getElementById("select-entity");
    const hiddenInput = document.getElementById("entity_id");
    const activeIdEl = document.getElementById("workspace-active-id-text");
    if (activeIdEl) {
      activeIdEl.textContent = activeEntityId;
    }
    if (select) {
      select.innerHTML = `<option value="${activeEntityId}" selected>⭐ ${activeEntityId} (Primary Workspace)</option>`;
    }
    if (hiddenInput) {
      hiddenInput.value = activeEntityId;
    }
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
let activeCardData = null;

function formatMarkdownToHtml(raw) {
  if (!raw) return "";
  
  // Normalize line endings
  let text = String(raw).replace(/\r\n/g, "\n");

  // Protect code fences
  const codeBlocks = [];
  text = text.replace(/```([a-zA-Z0-9_\-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
    const idx = codeBlocks.length;
    const escapedCode = code.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    codeBlocks.push(`<pre><code class="language-${lang || 'text'}">${escapedCode}</code></pre>`);
    return `%%CODEBLOCK_${idx}%%`;
  });

  // Protect inline code
  const inlineCodes = [];
  text = text.replace(/`([^`\n]+)`/g, (match, code) => {
    const idx = inlineCodes.length;
    const escaped = code.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    inlineCodes.push(`<code>${escaped}</code>`);
    return `%%INLINECODE_${idx}%%`;
  });

  // Headers
  text = text.replace(/^#### (.*?)$/gm, "<h4>$1</h4>");
  text = text.replace(/^### (.*?)$/gm, "<h3>$1</h3>");
  text = text.replace(/^## (.*?)$/gm, "<h2>$1</h2>");
  text = text.replace(/^# (.*?)$/gm, "<h1>$1</h1>");

  // Horizontal rules
  text = text.replace(/^---$/gm, "<hr style='border: none; border-top: 1px solid rgba(255,255,255,0.1); margin: 1.25rem 0;'>");

  // Bold & Italic
  text = text.replace(/\*\*(.*?)\*\*/g, "<b>$1</b>");
  text = text.replace(/\*(.*?)\*/g, "<i>$1</i>");

  // Blockquotes
  text = text.replace(/^> (.*?)$/gm, "<blockquote>$1</blockquote>");

  // Unordered list items
  text = text.replace(/^[*\-] (.*?)$/gm, "<li>$1</li>");
  text = text.replace(/(<li>[\s\S]*?<\/li>)/g, "<ul>$1</ul>");
  // Clean duplicate nested uls
  text = text.replace(/<\/ul>\s*<ul>/g, "");

  // Paragraphs
  const lines = text.split("\n\n");
  text = lines.map(block => {
    block = block.trim();
    if (!block) return "";
    if (block.startsWith("<h") || block.startsWith("<pre") || block.startsWith("<ul>") || block.startsWith("<blockquote>") || block.startsWith("<hr")) {
      return block;
    }
    return `<p>${block.replace(/\n/g, "<br>")}</p>`;
  }).join("\n");

  // Restore inline code
  text = text.replace(/%%INLINECODE_(\d+)%%/g, (match, idx) => inlineCodes[idx] || "");

  // Restore code blocks
  text = text.replace(/%%CODEBLOCK_(\d+)%%/g, (match, idx) => codeBlocks[idx] || "");

  return `<div class="card-reader-rendered">${text}</div>`;
}

async function loadKnowledgeAssets() {
  try {
    const res = await fetch("/api/assets/list");
    const data = await res.json();
    knowledgeAssets = data.assets || [];

    const badgeEl = document.getElementById("knowledge-card-count-badge");
    if (badgeEl) {
      badgeEl.textContent = `${knowledgeAssets.length} cards`;
    }

    renderKnowledgeExplorer();

    // Auto-select first card if reader is blank
    if (!activeCardData && knowledgeAssets.length > 0) {
      const first = knowledgeAssets[0];
      viewAssetMarkdown(first.category, first.filename);
    }
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
      const cat = (item.category || "").toLowerCase();
      const target = currentKnowledgeFilter.toLowerCase();
      matchesFilter = cat === target || cat === target + "s" || cat + "s" === target;
    }

    let matchesSearch = true;
    if (currentKnowledgeSearch) {
      const q = currentKnowledgeSearch.toLowerCase();
      matchesSearch = (
        (item.title && item.title.toLowerCase().includes(q)) ||
        (item.filename && item.filename.toLowerCase().includes(q))
      );
    }

    return matchesFilter && matchesSearch;
  });

  if (filtered.length === 0) {
    container.innerHTML = `<div style="color: var(--text-muted); text-align: center; padding: 2.5rem 1rem;">No knowledge cards match the current filter.</div>`;
    return;
  }

  filtered.forEach(item => {
    const card = document.createElement("div");
    card.className = "knowledge-card-item";
    if (activeCardData && activeCardData.filename === item.filename) {
      card.classList.add("active");
    }

    const catClass = item.category === "adr" ? "adr" : (item.category === "doc" ? "doc" : (item.category === "error" ? "error" : "incident"));
    const catLabel = (item.category || "DOC").toUpperCase();
    const dateStr = item.mtime ? new Date(item.mtime * 1000).toLocaleDateString() : "";
    const tokensSaved = item.est_tokens_saved || Math.round((item.word_count || 100) * 1.33);

    card.innerHTML = `
      <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.3rem;">
        <span class="knowledge-badge ${catClass}">${catLabel}</span>
        <span style="font-size: 0.7rem; color: #34d399; font-family: var(--font-mono); background: rgba(16, 185, 129, 0.1); padding: 0.1rem 0.35rem; border-radius: 4px;" title="Estimated prompt tokens saved from context burn">⚡ ~${tokensSaved} Tok</span>
      </div>
      <div style="font-weight: 600; color: var(--text-main); font-size: 0.88rem; line-height: 1.35; margin-bottom: 0.25rem;">${escapeHtml(item.title)}</div>
      <div style="display: flex; justify-content: space-between; font-size: 0.72rem; color: var(--text-dim); font-family: var(--font-mono);">
        <span>${escapeHtml(item.filename)}</span>
        <span>${dateStr}</span>
      </div>
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
  const readerBadge = document.getElementById("knowledge-reader-badge");
  const readerTitle = document.getElementById("knowledge-reader-title");
  const readerPath = document.getElementById("knowledge-reader-path");
  const readerSavings = document.getElementById("knowledge-reader-savings");
  const btnCopy = document.getElementById("btn-copy-card-markdown");
  const btnDownload = document.getElementById("btn-download-card-markdown");

  if (readerPath) readerPath.textContent = `${category}/${filename}`;

  try {
    const res = await fetch(`/api/assets/read?category=${encodeURIComponent(category)}&filename=${encodeURIComponent(filename)}`);
    const data = await res.json();
    activeCardData = data;

    const catClass = category === "adr" ? "adr" : (category === "doc" ? "doc" : (category === "error" ? "error" : "incident"));
    if (readerBadge) {
      readerBadge.className = `knowledge-badge ${catClass}`;
      readerBadge.textContent = category.toUpperCase();
      readerBadge.style.display = "inline-block";
    }

    if (readerTitle) {
      const firstLine = (data.content || "").split("\n")[0].replace(/^#+\s*/, "").trim();
      readerTitle.textContent = firstLine || filename;
    }

    if (readerPath) {
      readerPath.textContent = data.path || `${category}/${filename}`;
    }

    const tokensSaved = data.est_tokens_saved || Math.round((data.word_count || 100) * 1.33);
    if (readerSavings) {
      readerSavings.textContent = `⚡ ~${tokensSaved} Tokens Saved (Zero Prompt Burn)`;
      readerSavings.style.display = "inline-block";
    }

    if (btnCopy) btnCopy.style.display = "inline-block";
    if (btnDownload) btnDownload.style.display = "inline-block";

    if (readerEl) {
      readerEl.innerHTML = formatMarkdownToHtml(data.content || "Empty card content.");
    }

    // Highlight card in list if exists
    document.querySelectorAll(".knowledge-card-item").forEach(el => {
      if (el.textContent.includes(filename)) el.classList.add("active");
      else el.classList.remove("active");
    });
  } catch (err) {
    if (readerEl) readerEl.innerHTML = `<div style="color: var(--accent-rose); padding: 2rem; text-align: center;">Failed to load card content: ${err.message}</div>`;
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

  const activeInUseCount = schemaOpcodes.filter(op => cachedEntityPages.some(p => p.opcode === op.opcode)).length;
  const activePill = document.querySelector('.filter-pill[data-filter="active"]');
  if (activePill) {
    activePill.textContent = `🟢 In Active Memory (${activeInUseCount})`;
  }

  const filtered = schemaOpcodes.filter(op => {
    let matchesFilter = true;
    if (currentFilter === "active") {
      matchesFilter = cachedEntityPages.some(p => p.opcode === op.opcode);
    } else if (currentFilter === "preset") {
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

    const activeRegister = cachedEntityPages.find(p => p.opcode === op.opcode);
    const isInUse = !!activeRegister;
    let inUseBadge = "";
    let activeValSubtitle = "";
    if (isInUse) {
      const rawVal = activeRegister.decoded?.human_value !== undefined ? activeRegister.decoded.human_value : (activeRegister.value_hex || '');
      const hVal = escapeHtml(String(rawVal));
      inUseBadge = ` <span class="in-use-pill" title="Currently holding value in active workspace '${activeEntityId}': ${hVal}">● IN USE</span>`;
      activeValSubtitle = `<div style="font-size: 0.72rem; color: #34d399; font-family: var(--font-mono); margin-top: 0.2rem; font-weight: 500;">⚡ Active: ${hVal}</div>`;
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
      <td style="font-weight: 700;">${op.name}${inUseBadge}${activeValSubtitle}</td>
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

function appendTerminalLine(role, text, meta = null) {
  const terminalLog = document.getElementById("terminal-log");
  if (!terminalLog) {
    console.log(`[DUME ${role.toUpperCase()}]:`, text);
    return null;
  }
  const line = document.createElement("div");
  line.className = `terminal-line ${role}-line`;
  
  let prefix = "[USER]";
  if (role === "nostra") {
    const agName = (window.dumeUserConfig && window.dumeUserConfig.agent_name) || "Agent";
    prefix = `[${agName.toUpperCase()}]`;
  }
  if (role === "system") prefix = "[SYSTEM]";

  let contentHtml = `<span class="terminal-prefix">${prefix}</span> ${escapeHtml(text || '')}`;

  if (role === "nostra" && meta && meta.scratchpad) {
    const sp = meta.scratchpad;
    const tok = sp.estimated_tokens ?? 0;
    const maxTok = sp.max_tokens ?? 2048;
    const turns = sp.active_turns ?? 0;
    const maxTurns = sp.max_turns ?? 4;
    const pct = Math.min(100, Math.round((tok / maxTok) * 100));
    const pctColor = pct >= 80 ? "#f87171" : (pct >= 50 ? "#fbbf24" : "#34d399");
    const synthMs = meta.synthMs ? Math.round(meta.synthMs) : 0;
    const tps = meta.tps ? Number(meta.tps).toFixed(1) : "--";

    contentHtml += `
      <div class="turn-context-bar" style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.45rem; padding-top: 0.35rem; border-top: 1px dashed rgba(255,255,255,0.12); font-size: 0.72rem; font-family: var(--font-mono); color: #94a3b8;">
        <div style="display: flex; align-items: center; gap: 0.45rem;">
          <span style="color: ${pctColor}; font-weight: 700; display: inline-flex; align-items: center; gap: 0.25rem;">
            <span style="display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: ${pctColor};"></span>
            Context: ${pct}%
          </span>
          <span style="color: #64748b;">(${tok}/${maxTok} tokens · Turn ${turns}/${maxTurns})</span>
        </div>
        <div style="display: flex; align-items: center; gap: 0.4rem;">
          <span style="color: #38bdf8;">⚡ Recall: ${synthMs}ms</span>
          <span style="color: #475569;">|</span>
          <span style="color: #34d399;">${tps} tok/s</span>
        </div>
      </div>
    `;
  }

  line.innerHTML = contentHtml;
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
  const meterBar = document.getElementById("context-meter-bar");
  const meterPct = document.getElementById("context-meter-pct");
  if (!sp) return;
  const turns = sp.active_turns ?? 0;
  const maxT = sp.max_turns ?? 4;
  const tok = sp.estimated_tokens ?? 0;
  const maxTok = sp.max_tokens ?? 2048;
  const pct = Math.min(100, Math.round((tok / maxTok) * 100));

  if (badge) {
    badge.textContent = `${turns}/${maxT} Turns (~${tok}/${maxTok} Tok)`;
  }
  if (meterBar) {
    meterBar.style.width = `${Math.max(pct, turns > 0 ? 4 : 0)}%`;
    if (pct >= 80) {
      meterBar.style.background = "linear-gradient(90deg, #f59e0b, #ef4444)";
    } else if (pct >= 50) {
      meterBar.style.background = "linear-gradient(90deg, #10b981, #f59e0b)";
    } else {
      meterBar.style.background = "linear-gradient(90deg, #10b981, #38bdf8)";
    }
  }
  if (meterPct) {
    meterPct.textContent = `${pct}%`;
    meterPct.style.color = pct >= 80 ? "#f87171" : (pct >= 50 ? "#fbbf24" : "#38bdf8");
  }
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

  // 1-Click Active Partition ID Copy in Workspace Bar
  const activeIdBadge = document.getElementById("workspace-active-id-badge");
  if (activeIdBadge) {
    activeIdBadge.addEventListener("click", () => {
      const activeIdEl = document.getElementById("workspace-active-id-text");
      const idToCopy = activeEntityId || (activeIdEl ? activeIdEl.textContent : "");
      if (!idToCopy) return;
      navigator.clipboard.writeText(idToCopy).then(() => {
        if (activeIdEl) {
          const original = activeIdEl.textContent;
          activeIdEl.textContent = "Copied!";
          activeIdEl.style.color = "#34d399";
          setTimeout(() => {
            activeIdEl.textContent = original;
            activeIdEl.style.color = "";
          }, 1500);
        }
      }).catch(() => {
        prompt("Copy Workspace Partition ID:", idToCopy);
      });
    });
  }

  // Create Workspace Modal Handlers
  const createWsModal = document.getElementById("create-workspace-modal-overlay");
  const btnOpenCreateWs = document.getElementById("btn-open-create-workspace-modal");
  const btnCloseCreateWs = document.getElementById("btn-close-create-workspace");
  const btnCancelCreateWs = document.getElementById("btn-cancel-create-workspace");
  const createWsForm = document.getElementById("create-workspace-form");
  const createWsNameInput = document.getElementById("create-ws-name");
  const createWsIdInput = document.getElementById("create-ws-id");
  let userEditedSlug = false;

  if (btnOpenCreateWs && createWsModal) {
    btnOpenCreateWs.addEventListener("click", () => {
      userEditedSlug = false;
      if (createWsNameInput) createWsNameInput.value = "";
      if (createWsIdInput) createWsIdInput.value = "";
      createWsModal.style.display = "flex";
      setTimeout(() => {
        if (createWsNameInput) createWsNameInput.focus();
      }, 50);
    });
  }

  const closeCreateWsModal = () => {
    if (createWsModal) createWsModal.style.display = "none";
  };
  if (btnCloseCreateWs) btnCloseCreateWs.addEventListener("click", closeCreateWsModal);
  if (btnCancelCreateWs) btnCancelCreateWs.addEventListener("click", closeCreateWsModal);
  if (createWsModal) {
    createWsModal.addEventListener("click", (e) => {
      if (e.target === createWsModal) closeCreateWsModal();
    });
  }

  // Live Auto-Slugger for Workspace Identifier
  if (createWsIdInput) {
    createWsIdInput.addEventListener("input", () => {
      userEditedSlug = !!createWsIdInput.value.trim();
    });
  }

  if (createWsNameInput && createWsIdInput) {
    createWsNameInput.addEventListener("input", () => {
      if (!userEditedSlug) {
        const raw = createWsNameInput.value.trim();
        if (raw) {
          const slug = raw
            .replace(/[^a-zA-Z0-9_\s-]/g, "")
            .replace(/\s+/g, "_")
            .slice(0, 24);
          createWsIdInput.value = `${slug}-01`;
        } else {
          createWsIdInput.value = "";
        }
      }
    });
  }

  // Category Chip Selector in Create Workspace Modal
  const categoryChips = document.querySelectorAll("#ws-category-chips .ws-type-chip");
  categoryChips.forEach(chip => {
    chip.addEventListener("click", () => {
      categoryChips.forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      const radio = chip.querySelector('input[type="radio"]');
      if (radio) radio.checked = true;
    });
  });

  // Create Workspace Form Submit
  if (createWsForm) {
    createWsForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const wsName = createWsNameInput ? createWsNameInput.value.trim() : "";
      let wsId = createWsIdInput ? createWsIdInput.value.trim() : "";

      if (!wsName) {
        alert("Please enter a Project / Workspace Name.");
        return;
      }
      if (!wsId) {
        wsId = wsName.replace(/[^a-zA-Z0-9_\s-]/g, "").replace(/\s+/g, "_") + "-01";
      }

      // Save custom entity and alias
      saveCustomEntity(wsId);
      setEntityAlias(wsId, wsName);

      const hiddenInp = document.getElementById("entity_id");
      if (hiddenInp) hiddenInp.value = wsId;
      activeEntityId = wsId;

      closeCreateWsModal();
      await loadEntities(wsId);

      appendTerminalLine("system", `Created & switched to Workspace: '${wsName}' [Partition ID: ${wsId}]`);
    });
  }

  // Workspace Settings / Lifecycle Modal Handlers
  const entityActionsModal = document.getElementById("entity-actions-modal-overlay");
  const btnOpenEntityActions = document.getElementById("btn-open-entity-actions");
  const btnCloseEntityActions = document.getElementById("btn-close-entity-actions-modal");
  const entityTargetIdEl = document.getElementById("entity-actions-target-id");
  const aliasInput = document.getElementById("input-entity-alias");
  const renameForm = document.getElementById("entity-rename-form");
  const btnArchiveEntity = document.getElementById("btn-archive-entity");
  const btnDeleteEntity = document.getElementById("btn-delete-entity-prompt");
  const btnCopyHeader = document.getElementById("btn-copy-partition-header");

  if (btnOpenEntityActions && entityActionsModal) {
    btnOpenEntityActions.addEventListener("click", () => {
      const alias = getEntityAlias(activeEntityId);
      if (entityTargetIdEl) {
        entityTargetIdEl.textContent = alias ? `${alias} (${activeEntityId})` : activeEntityId;
      }
      if (aliasInput) {
        aliasInput.value = alias || "";
      }
      if (btnArchiveEntity) {
        const archived = isEntityArchived(activeEntityId);
        btnArchiveEntity.textContent = archived ? "Un-archive Workspace" : "Archive Workspace";
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

  // Copy X-Entity-ID Header button in Settings Modal
  if (btnCopyHeader) {
    btnCopyHeader.addEventListener("click", () => {
      const headerText = `X-Entity-ID: ${activeEntityId}`;
      navigator.clipboard.writeText(headerText).then(() => {
        btnCopyHeader.innerHTML = `✅ <span>Copied Header!</span>`;
        setTimeout(() => {
          btnCopyHeader.innerHTML = `📋 <span>Copy Header</span>`;
        }, 1500);
      }).catch(() => {
        prompt("Copy Proxy Header:", headerText);
      });
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

      appendTerminalLine("system", `Updated alias for workspace '${activeEntityId}': '${newAlias || "None"}'`);
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

      appendTerminalLine("system", `${next ? "Archived" : "Un-archived"} workspace '${activeEntityId}'.`);
      if (entityActionsModal) entityActionsModal.style.display = "none";
      const configured = (window.dumeUserConfig && window.dumeUserConfig.entity_id) || "MadBrad-Nostra-01";
      loadEntities(configured);
    });
  }

  if (btnDeleteEntity) {
    btnDeleteEntity.addEventListener("click", async () => {
      const targetToDelete = activeEntityId;
      if (!confirm(`Permanently purge workspace '${targetToDelete}' and delete all its LMDB state registers & history?`)) {
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

        appendTerminalLine("system", `Purged Workspace '${targetToDelete}' from LMDB (${data.active_deleted || 0} registers, ${data.history_deleted || 0} audit logs deleted).`);
        if (entityActionsModal) entityActionsModal.style.display = "none";
        const configured = (window.dumeUserConfig && window.dumeUserConfig.entity_id) || "MadBrad-Nostra-01";
        await loadEntities(configured);
      } catch (err) {
        alert("Failed to delete workspace: " + err.message);
      }
    });
  }

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
      openOnboardingModal();
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
      } else if (targetView === "view-cabinet") {
        loadCabinetWorkflows();
        loadCabinetHealth();
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


  // Knowledge Base Reader Copy & Download Actions
  const btnCopyCard = document.getElementById("btn-copy-card-markdown");
  if (btnCopyCard) {
    btnCopyCard.addEventListener("click", () => {
      if (!activeCardData || !activeCardData.content) return;
      navigator.clipboard.writeText(activeCardData.content).then(() => {
        const orig = btnCopyCard.textContent;
        btnCopyCard.textContent = "✅ Copied!";
        setTimeout(() => { btnCopyCard.textContent = orig; }, 1500);
      }).catch(() => {
        prompt("Copy Card Markdown:", activeCardData.content);
      });
    });
  }

  const btnDownloadCard = document.getElementById("btn-download-card-markdown");
  if (btnDownloadCard) {
    btnDownloadCard.addEventListener("click", () => {
      if (!activeCardData || !activeCardData.content) return;
      const blob = new Blob([activeCardData.content], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = activeCardData.filename || "knowledge_card.md";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    });
  }

  // Create Knowledge Card Modal Handlers
  const createCardModal = document.getElementById("create-knowledge-modal-overlay");
  const btnOpenCreateCard = document.getElementById("btn-open-create-knowledge-modal");
  const btnCloseCreateCard = document.getElementById("btn-close-create-knowledge-modal");
  const btnCancelCreateCard = document.getElementById("btn-cancel-create-knowledge");
  const createCardForm = document.getElementById("create-knowledge-form");
  const createCardTitle = document.getElementById("create-card-title");
  const createCardFilename = document.getElementById("create-card-filename");
  const createCardContent = document.getElementById("create-card-content");
  const createCardPreview = document.getElementById("create-card-filename-preview");
  const btnLoadTemplate = document.getElementById("btn-load-card-template");
  let currentCardCategory = "adr";

  const cardTemplates = {
    adr: `# ADR-XXX: Title

## Status
Accepted & Active

## Context
Describe the architectural context, problem, or decision drivers...

## Decision
Describe the deterministic design decision, register schema, or storage structure...

## Consequences
- **Token Burn**: 0 prompt token overhead
- **Latency**: < 0.2ms local memory-mapped reads
- **Living Cabinet**: Synchronized with Sentinel and Nostra protocols
`,
    doc: `# DOC-XXX: Specification Sheet

## Overview
High-level description of this project module, spatial system, or data contract...

## Key Architecture & Registers
- State Register 1: ...
- State Register 2: ...

## Operational Runbook
1. Initialize environment...
2. Execute workflow...
`,
    error: `# ERR-XXX: Error Pattern & Fingerprint

## Pattern
Error message, exception traceback, or failure mode string...

## Root Cause
Detailed explanation of why this error state occurs...

## Resolution Runbook
1. Step 1 to diagnose...
2. Step 2 to remediate...
`,
    incident: `# INC-XXX: Incident Postmortem

## Summary & Impact
What occurred, severity, and customer/agent impact...

## Root Cause
Technical breakdown of the underlying defect or state drift...

## Corrective Actions & Preventative Rules
1. Action item 1...
2. Action item 2...
`
  };

  const updateFilenamePreview = () => {
    const title = createCardTitle ? createCardTitle.value.trim() : "";
    const explicitFname = createCardFilename ? createCardFilename.value.trim() : "";
    const catFolder = currentCardCategory + "s";
    if (explicitFname) {
      if (createCardPreview) createCardPreview.textContent = `${catFolder}/${explicitFname}`;
    } else if (title) {
      const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
      if (createCardPreview) createCardPreview.textContent = `${catFolder}/${currentCardCategory.toUpperCase()}-${slug}.md`;
    } else {
      if (createCardPreview) createCardPreview.textContent = `${catFolder}/${currentCardCategory.toUpperCase()}-...md`;
    }
  };

  if (btnOpenCreateCard && createCardModal) {
    btnOpenCreateCard.addEventListener("click", () => {
      createCardModal.style.display = "flex";
      if (createCardTitle) {
        createCardTitle.value = "";
        createCardTitle.focus();
      }
      if (createCardFilename) createCardFilename.value = "";
      if (createCardContent && !createCardContent.value) {
        createCardContent.value = cardTemplates[currentCardCategory] || "";
      }
      updateFilenamePreview();
    });
  }

  const closeCreateCardModal = () => {
    if (createCardModal) createCardModal.style.display = "none";
  };

  if (btnCloseCreateCard) btnCloseCreateCard.addEventListener("click", closeCreateCardModal);
  if (btnCancelCreateCard) btnCancelCreateCard.addEventListener("click", closeCreateCardModal);

  if (createCardModal) {
    createCardModal.addEventListener("click", (e) => {
      if (e.target === createCardModal) closeCreateCardModal();
    });
  }

  document.querySelectorAll("#knowledge-category-chips .ws-type-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      document.querySelectorAll("#knowledge-category-chips .ws-type-chip").forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      const radio = chip.querySelector('input[type="radio"]');
      if (radio) {
        radio.checked = true;
        currentCardCategory = radio.value;
      } else {
        currentCardCategory = chip.getAttribute("data-category") || "adr";
      }
      updateFilenamePreview();
      if (createCardContent && (!createCardContent.value.trim() || Object.values(cardTemplates).some(t => t.trim() === createCardContent.value.trim()))) {
        createCardContent.value = cardTemplates[currentCardCategory] || "";
      }
    });
  });

  if (createCardTitle) createCardTitle.addEventListener("input", updateFilenamePreview);
  if (createCardFilename) createCardFilename.addEventListener("input", updateFilenamePreview);

  if (btnLoadTemplate) {
    btnLoadTemplate.addEventListener("click", () => {
      if (createCardContent) {
        createCardContent.value = cardTemplates[currentCardCategory] || "";
      }
    });
  }

  if (createCardForm) {
    createCardForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const title = createCardTitle ? createCardTitle.value.trim() : "";
      const content = createCardContent ? createCardContent.value : "";
      const explicitFname = createCardFilename ? createCardFilename.value.trim() : "";
      if (!title || !content) return;

      const btnSubmit = document.getElementById("btn-submit-create-knowledge");
      if (btnSubmit) btnSubmit.textContent = "Saving...";

      try {
        const resp = await fetch("/api/assets/create", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            category: currentCardCategory,
            title: title,
            content: content,
            filename: explicitFname || null
          })
        });
        const res = await resp.json();
        if (resp.ok && res.success) {
          closeCreateCardModal();
          createCardForm.reset();
          appendTerminalLine("system", `Created & Ingested Knowledge Card: '${res.title}' (${res.category}/${res.filename})`);
          await loadKnowledgeAssets();
          viewAssetMarkdown(res.category, res.filename);
        } else {
          alert("Failed to create knowledge card: " + (res.detail || res.error));
        }
      } catch (err) {
        alert("Error creating knowledge card: " + err.message);
      } finally {
        if (btnSubmit) btnSubmit.innerHTML = `💾 Save & Ingest Card`;
      }
    });
  }

  // Custom Opcode Modal Logic
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

      // Calculate next available 3xxx custom opcode ID
      const existingCustom = schemaOpcodes.filter(op => op.opcode >= 3000 && op.opcode <= 3999).map(op => op.opcode);
      const nextId = existingCustom.length > 0 ? Math.max(...existingCustom) + 1 : 3000;
      const idPreview = document.getElementById("custom-opcode-id-preview");
      if (idPreview) idPreview.textContent = `ID: ${nextId}`;
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

  // Enum quick chip click handlers
  document.querySelectorAll(".enum-quick-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const enumInput = document.getElementById("custom-opcode-enum-text");
      if (enumInput) {
        enumInput.value = chip.getAttribute("data-enum");
      }
    });
  });

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

  // Settings dropdown toggle
  const btnSettingsToggle = document.getElementById("btn-settings-dropdown-toggle");
  const settingsDropdown = document.getElementById("settings-menu-dropdown");

  if (btnSettingsToggle && settingsDropdown) {
    btnSettingsToggle.addEventListener("click", (e) => {
      e.stopPropagation();
      const isVisible = settingsDropdown.style.display !== "none";
      settingsDropdown.style.display = isVisible ? "none" : "flex";
    });

    document.addEventListener("click", (e) => {
      if (!settingsDropdown.contains(e.target) && e.target !== btnSettingsToggle) {
        settingsDropdown.style.display = "none";
      }
    });

    settingsDropdown.querySelectorAll(".settings-menu-item").forEach(item => {
      item.addEventListener("click", () => {
        settingsDropdown.style.display = "none";
      });
    });
  }

  // Launchpad CTA buttons
  addSafeListener("btn-launchpad-intake", "click", () => {
    const intakeModal = document.getElementById("intake-modal");
    if (intakeModal) intakeModal.style.display = "flex";
  });

  addSafeListener("btn-launchpad-connect", "click", () => {
    const connectModal = document.getElementById("connect-modal-overlay");
    if (connectModal) connectModal.style.display = "flex";
  });

  addSafeListener("btn-launchpad-wake", "click", () => {
    openOnboardingModal();
  });
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

  const navMemoryBadge = document.getElementById("nav-badge-memory");
  if (navMemoryBadge) navMemoryBadge.textContent = counts.all;

  const coldLaunchpad = document.getElementById("cold-start-launchpad");
  if (coldLaunchpad) {
    coldLaunchpad.style.display = counts.all === 0 ? "block" : "none";
  }
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
      const agName = (window.dumeUserConfig && window.dumeUserConfig.agent_name) || "your agent";
      container.innerHTML = `
        <div class="empty-state-card">
          <div class="empty-state-icon">✨</div>
          <div class="empty-state-title">No Memory Registers in This Entity Yet</div>
          <div class="empty-state-desc">
            This entity is clean and ready. Ingest a document, drop project notes, or chat with ${agName} to mint your first deterministic 32-byte memory registers with 0 prompt token burn.
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

// Dynamic Port Resolution & Update Helpers
function getActivePort() {
  if (window.location && window.location.port) {
    return window.location.port;
  }
  if (window.dumeUserConfig && window.dumeUserConfig.port) {
    return String(window.dumeUserConfig.port);
  }
  return "8095";
}

function updatePortReferences(port) {
  const activePort = port || getActivePort();
  const host = window.location.hostname || "localhost";
  const baseUrl = `http://${host}:${activePort}/v1`;

  // 1. Header live status pill
  const liveStatus = document.getElementById("header-live-status-text");
  const agName = (window.dumeUserConfig && window.dumeUserConfig.agent_name) || "Ste4ve";
  if (liveStatus) liveStatus.textContent = `${agName} Active (${activePort})`;

  // 2. Launchpad connect text
  const launchpadConnectDesc = document.getElementById("launchpad-card-connect-desc");
  if (launchpadConnectDesc) {
    launchpadConnectDesc.innerHTML = `Point your editor to <code>${baseUrl}</code> or use our native 1-click MCP config to let your agent query memory.`;
  }

  // 3. Guide modal step 2 desc
  const guideStep2Desc = document.getElementById("guide-step2-desc");
  if (guideStep2Desc) {
    guideStep2Desc.innerHTML = `Point Cursor, Claude Desktop, VS Code (Cline), or your terminal to <code>${baseUrl}</code> or use our native 1-click MCP config.`;
  }

  // 4. Agent connect card sub
  const agentSubPort = document.getElementById("agent-sub-proxy-port");
  if (agentSubPort) agentSubPort.textContent = `Port ${activePort} Universal`;

  // 5. Connect modal code snippets
  const copyBaseUrl = document.getElementById("input-copy-baseurl");
  if (copyBaseUrl) copyBaseUrl.value = baseUrl;

  const cursorOverride = document.getElementById("cursor-override-url");
  if (cursorOverride) cursorOverride.textContent = baseUrl;

  const codeVscode = document.getElementById("code-vscode-settings");
  if (codeVscode) {
    codeVscode.textContent = `Base URL: ${baseUrl}\nAPI Key:  dume\nModel ID: nostra (or qwen2.5:0.5b / llama-3.3-70b-versatile)`;
  }

  const codePs1 = document.getElementById("code-ps1-term");
  if (codePs1) {
    codePs1.textContent = `$env:OPENAI_BASE_URL="${baseUrl}"\n$env:OPENAI_API_KEY="dume"`;
  }

  const codeBash = document.getElementById("code-bash-term");
  if (codeBash) {
    codeBash.textContent = `export OPENAI_BASE_URL="${baseUrl}"\nexport OPENAI_API_KEY="dume"`;
  }

  const codePy = document.getElementById("code-python-sdk");
  if (codePy) {
    const agId = (window.dumeUserConfig && window.dumeUserConfig.entity_id) || "MadBrad-Nostra-01";
    codePy.textContent = `from openai import OpenAI\n\nclient = OpenAI(\n    base_url="${baseUrl}",\n    api_key="dume"\n)\n\nresponse = client.chat.completions.create(\n    model="nostra",\n    messages=[{"role": "user", "content": "box is the game."}],\n    extra_headers={"X-Entity-ID": "${agId}"}\n)\n\nprint(response.choices[0].message.content)`;
  }
}

// Onboarding & Custom Wake Phrase Handlers
function updateAgentUI(agentName, wakePhrase) {
  const opName = (window.dumeUserConfig && window.dumeUserConfig.operator_name) || "MadBrad";
  const agName = agentName || (window.dumeUserConfig && window.dumeUserConfig.agent_name) || "Ste4ve";
  const phrase = wakePhrase || (window.dumeUserConfig && window.dumeUserConfig.wake_phrase) || "box is the game.";

  const headerOp = document.getElementById("header-operator-name");
  const headerAg = document.getElementById("header-agent-name");
  const launchOp = document.getElementById("launchpad-operator-name");
  const launchAg = document.getElementById("launchpad-agent-name");
  const launchWake = document.getElementById("launchpad-wake-code");

  if (headerOp) headerOp.textContent = opName;
  if (headerAg) headerAg.textContent = agName;
  if (launchOp) launchOp.textContent = opName;
  if (launchAg) launchAg.textContent = agName;
  if (launchWake) launchWake.textContent = `"${phrase}"`;

  const entityActionTarget = document.getElementById("entity-actions-target-id");
  if (entityActionTarget && window.dumeUserConfig && window.dumeUserConfig.entity_id) {
    entityActionTarget.textContent = window.dumeUserConfig.entity_id;
  }

  updatePortReferences();
}

async function checkOnboarding() {
  try {
    const res = await fetch("/api/v1/onboarding/status");
    if (!res.ok) return;
    const data = await res.json();
    window.dumeUserConfig = data.config || {};

    const opInput = document.getElementById("onboarding-operator-name");
    const agInput = document.getElementById("onboarding-agent-name");
    const wakeInput = document.getElementById("onboarding-wake-phrase");
    const portInput = document.getElementById("onboarding-port");

    if (data.config) {
      if (opInput && data.config.operator_name) opInput.value = data.config.operator_name;
      if (agInput && data.config.agent_name) agInput.value = data.config.agent_name;
      if (wakeInput && data.config.wake_phrase) wakeInput.value = data.config.wake_phrase;
      if (portInput && data.config.port) portInput.value = data.config.port;
      if (data.config.entity_id) {
        activeEntityId = data.config.entity_id;
        const hiddenInp = document.getElementById("entity_id");
        if (hiddenInp) hiddenInp.value = activeEntityId;
      }
      updateAgentUI(data.config.agent_name, data.config.wake_phrase);
    } else {
      updatePortReferences();
    }

    if (!data.onboarding_completed) {
      openOnboardingModal();
      await loadEntities();
    } else {
      await loadEntities(data.config && data.config.entity_id ? data.config.entity_id : null);
    }
  } catch (err) {
    console.error("Failed to check onboarding status:", err);
  }
}

function openOnboardingModal() {
  const modal = document.getElementById("onboarding-modal-overlay");
  if (modal) modal.style.display = "flex";
}

function closeOnboardingModal() {
  const modal = document.getElementById("onboarding-modal-overlay");
  if (modal) modal.style.display = "none";
}

async function executeResetData() {
  const confirmed = confirm(
    "⚠️ DUMEdb Beta Testing Reset\n\n" +
    "Are you sure you want to clear all data and revert to pristine first-time load state?\n\n" +
    "• Wipes dume_config.json\n" +
    "• Purges test LMDB state registers\n" +
    "• Clears browser entity storage\n\n" +
    "The page will automatically reload to test the Welcome & Onboarding flow."
  );
  if (!confirmed) return;

  try {
    const res = await fetch("/api/v1/onboarding/reset", { method: "POST" });
    if (res.ok) {
      localStorage.removeItem("dume_custom_entities");
      for (let i = localStorage.length - 1; i >= 0; i--) {
        const k = localStorage.key(i);
        if (k && k.startsWith("dume_")) {
          localStorage.removeItem(k);
        }
      }
      alert("✅ Data cleared! DUMEdb is now in pristine first-time load state. Reloading...");
      window.location.reload();
    } else {
      alert("Reset failed: " + res.statusText);
    }
  } catch (err) {
    alert("Error resetting data: " + err.message);
  }
}

function setupOnboardingModal() {
  const openBtn = document.getElementById("btn-open-onboarding-modal");
  const closeBtn = document.getElementById("btn-close-onboarding-modal");
  const cancelBtn = document.getElementById("btn-cancel-onboarding");
  const resetBtnHeader = document.getElementById("btn-reset-clean-state");
  const resetBtnModal = document.getElementById("btn-modal-reset-data");
  const form = document.getElementById("onboarding-setup-form");
  const statusMsg = document.getElementById("onboarding-status-msg");

  if (openBtn) openBtn.addEventListener("click", openOnboardingModal);
  if (closeBtn) closeBtn.addEventListener("click", closeOnboardingModal);
  if (cancelBtn) cancelBtn.addEventListener("click", closeOnboardingModal);
  if (resetBtnHeader) resetBtnHeader.addEventListener("click", executeResetData);
  if (resetBtnModal) resetBtnModal.addEventListener("click", executeResetData);

  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const opName = document.getElementById("onboarding-operator-name")?.value.trim();
      const agName = document.getElementById("onboarding-agent-name")?.value.trim();
      const wakePhrase = document.getElementById("onboarding-wake-phrase")?.value.trim();
      const portVal = parseInt(document.getElementById("onboarding-port")?.value || "8095", 10);
      const chosenPort = isNaN(portVal) ? 8095 : portVal;

      const ides = [];
      if (document.getElementById("ide-opt-antigravity")?.checked) ides.push("antigravity");
      if (document.getElementById("ide-opt-cursor")?.checked) ides.push("cursor");
      if (document.getElementById("ide-opt-windsurf")?.checked) ides.push("windsurf");
      if (document.getElementById("ide-opt-copilot")?.checked) ides.push("copilot");

      if (!opName || !agName || !wakePhrase) {
        alert("Please provide Operator Name, Agent Name, and Wake Phrase.");
        return;
      }

      const saveBtn = document.getElementById("btn-save-onboarding");
      if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.innerHTML = `<span>⏳ Locking Continuity...</span>`;
      }

      try {
        const res = await fetch("/api/v1/onboarding/setup", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            operator_name: opName,
            agent_name: agName,
            wake_phrase: wakePhrase,
            port: chosenPort,
            connected_ides: ides
          })
        });
        const data = await res.json();
        if (res.ok && data.success) {
          window.dumeUserConfig = data.config;
          updateAgentUI(data.config.agent_name, data.config.wake_phrase);
          updatePortReferences(data.config.port);

          if (statusMsg) {
            statusMsg.style.display = "block";
            statusMsg.style.background = "rgba(16, 185, 129, 0.2)";
            statusMsg.style.color = "#34d399";
            statusMsg.style.border = "1px solid rgba(16, 185, 129, 0.4)";
            statusMsg.innerHTML = `✅ <b>Continuity Locked!</b> Wake phrase <code>"${wakePhrase}"</code> active. Generated: ${data.files_scaffolded.join(", ")}`;
          }
          activeEntityId = data.config.entity_id;
          localStorage.setItem("dume_custom_entities", JSON.stringify([activeEntityId]));
          await loadEntities(activeEntityId);
          appendTerminalLine("system", `Onboarding complete: Wake phrase "${wakePhrase}" configured for entity "${activeEntityId}".`);
          setTimeout(() => {
            closeOnboardingModal();
            if (statusMsg) statusMsg.style.display = "none";
          }, 1500);
        } else {
          alert("Setup failed: " + (data.detail || JSON.stringify(data)));
        }
      } catch (err) {
        alert("Error saving onboarding configuration: " + err.message);
      } finally {
        if (saveBtn) {
          saveBtn.disabled = false;
          saveBtn.innerHTML = `<span>💾 Save & Lock Continuity</span>`;
        }
      }
    });
  }
}

// ==========================================
// The Living Cabinet & Workflows Studio Logic
// ==========================================
let cabinetWorkflows = [];
let currentCabinetFilter = "all";
let currentCabinetSearch = "";

async function loadCabinetWorkflows() {
  try {
    const res = await fetch("/api/cabinet/workflows");
    const data = await res.json();
    cabinetWorkflows = data.workflows || [];
    renderCabinetWorkflows();
  } catch (err) {
    console.error("Failed to load cabinet workflows:", err);
  }
}

async function loadCabinetHealth() {
  try {
    const res = await fetch("/api/cabinet/health");
    const data = await res.json();
    const totalEl = document.getElementById("cabinet-metric-total");
    const activeEl = document.getElementById("cabinet-metric-active");
    const staleEl = document.getElementById("cabinet-metric-stale");
    const statusEl = document.getElementById("cabinet-metric-status");
    const syncEl = document.getElementById("cabinet-metric-sync");

    if (totalEl) totalEl.textContent = data.total_count ?? 0;
    if (activeEl) activeEl.textContent = data.active_count ?? 0;
    if (staleEl) staleEl.textContent = data.stale_count ?? 0;
    if (statusEl) {
      statusEl.textContent = data.status === "healthy" ? "🟢 Healthy" : "⚠️ Advisory";
      statusEl.style.color = data.status === "healthy" ? "#34d399" : "#f59e0b";
    }
    if (syncEl) syncEl.textContent = "Live Sync";
  } catch (err) {
    console.error("Failed to load cabinet health:", err);
  }
}

function renderCabinetWorkflows() {
  const container = document.getElementById("cabinet-workflows-grid");
  if (!container) return;
  container.innerHTML = "";

  const filtered = cabinetWorkflows.filter(wf => {
    let matchesFilter = true;
    if (currentCabinetFilter === "retired") {
      matchesFilter = wf.status === "retired";
    } else if (currentCabinetFilter !== "all") {
      matchesFilter = wf.category === currentCabinetFilter && wf.status === "active";
    } else {
      matchesFilter = wf.status === "active";
    }

    let matchesSearch = true;
    if (currentCabinetSearch) {
      const q = currentCabinetSearch.toLowerCase();
      matchesSearch = (
        (wf.id && wf.id.toLowerCase().includes(q)) ||
        (wf.title && wf.title.toLowerCase().includes(q)) ||
        (wf.trigger && wf.trigger.toLowerCase().includes(q)) ||
        (wf.move && wf.move.toLowerCase().includes(q))
      );
    }
    return matchesFilter && matchesSearch;
  });

  if (filtered.length === 0) {
    container.innerHTML = `
      <div style="grid-column: 1 / -1; text-align: center; padding: 3rem 1rem; color: var(--text-muted); background: rgba(255,255,255,0.02); border: 1px dashed var(--border-color); border-radius: 12px;">
        <div style="font-size: 2rem; margin-bottom: 0.5rem;">🗄️</div>
        <div style="font-weight: 600; color: #cbd5e1; margin-bottom: 0.25rem;">No Cabinet Heuristics Match Filter</div>
        <div style="font-size: 0.82rem;">Adjust your search or click "+ Mint Workflow" to add a new operational rule.</div>
      </div>
    `;
    return;
  }

  const categoryStyles = {
    meta: { color: "#c084fc", bg: "rgba(139, 92, 246, 0.15)", border: "rgba(139, 92, 246, 0.35)", label: "Meta (M)" },
    shape: { color: "#60a5fa", bg: "rgba(59, 130, 246, 0.15)", border: "rgba(59, 130, 246, 0.35)", label: "Shape (S)" },
    speed: { color: "#34d399", bg: "rgba(16, 185, 129, 0.15)", border: "rgba(16, 185, 129, 0.35)", label: "Speed (P)" },
    self_monitoring: { color: "#fbbf24", bg: "rgba(245, 158, 11, 0.15)", border: "rgba(245, 158, 11, 0.35)", label: "Self-Monitor (X)" },
    posture: { color: "#fb7185", bg: "rgba(244, 63, 94, 0.15)", border: "rgba(244, 63, 94, 0.35)", label: "Posture (T)" },
    protocol: { color: "#38bdf8", bg: "rgba(6, 182, 212, 0.15)", border: "rgba(6, 182, 212, 0.35)", label: "Protocol (R)" },
    custom: { color: "#e879f9", bg: "rgba(232, 121, 249, 0.15)", border: "rgba(232, 121, 249, 0.35)", label: "Custom (C)" }
  };

  filtered.forEach(wf => {
    const card = document.createElement("div");
    card.style.display = "flex";
    card.style.flexDirection = "column";
    card.style.background = "rgba(15, 23, 42, 0.65)";
    card.style.border = "1px solid rgba(255, 255, 255, 0.08)";
    card.style.borderRadius = "10px";
    card.style.padding = "1rem";
    card.style.transition = "transform 0.2s ease, border-color 0.2s ease";

    const catStyle = categoryStyles[wf.category] || categoryStyles.protocol;
    const isRetired = wf.status === "retired";

    card.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem; margin-bottom: 0.6rem;">
        <div style="display: flex; align-items: center; gap: 0.45rem; flex-wrap: wrap;">
          <span style="font-size: 0.72rem; font-weight: 700; color: ${catStyle.color}; background: ${catStyle.bg}; border: 1px solid ${catStyle.border}; padding: 0.15rem 0.5rem; border-radius: 4px; font-family: var(--font-mono);">
            [${escapeHtml(wf.id)}]
          </span>
          <span style="font-size: 0.7rem; color: ${catStyle.color}; font-weight: 600;">
            ${catStyle.label}
          </span>
        </div>
        <div style="display: flex; align-items: center; gap: 0.35rem;">
          <span style="font-size: 0.68rem; color: #94a3b8; font-family: var(--font-mono); background: rgba(255,255,255,0.05); padding: 0.1rem 0.4rem; border-radius: 4px;" title="Times this workflow heuristic has fired in real sessions">
            ⚡ ${wf.fire_count ?? 1}x
          </span>
          ${isRetired ? `<span style="font-size: 0.68rem; color: #f87171; font-weight: 700; background: rgba(239,68,68,0.15); border: 1px solid rgba(239,68,68,0.3); padding: 0.1rem 0.35rem; border-radius: 4px;">RETIRED</span>` : ''}
        </div>
      </div>

      <div style="font-weight: 700; font-size: 0.95rem; color: #f8fafc; margin-bottom: 0.65rem; line-height: 1.35;">
        ${escapeHtml(wf.title)}
      </div>

      <div style="background: rgba(0, 0, 0, 0.25); border-left: 3px solid ${catStyle.color}; border-radius: 0 6px 6px 0; padding: 0.5rem 0.65rem; margin-bottom: 0.6rem;">
        <div style="font-size: 0.72rem; font-weight: 700; color: #cbd5e1; text-transform: uppercase; margin-bottom: 0.15rem; display: flex; align-items: center; gap: 0.3rem;">
          🎯 Trigger
        </div>
        <div style="font-size: 0.82rem; color: #94a3b8; line-height: 1.4;">
          ${escapeHtml(wf.trigger || 'Pattern recognition in active session')}
        </div>
      </div>

      <div style="background: rgba(0, 0, 0, 0.35); border-radius: 6px; padding: 0.6rem 0.75rem; margin-bottom: 0.6rem; flex: 1;">
        <div style="font-size: 0.72rem; font-weight: 700; color: #38bdf8; text-transform: uppercase; margin-bottom: 0.2rem; display: flex; align-items: center; gap: 0.3rem;">
          ⚡ Operational Move
        </div>
        <div style="font-size: 0.83rem; color: #e2e8f0; line-height: 1.45;">
          ${escapeHtml(wf.move || '')}
        </div>
      </div>

      ${wf.why ? `
        <div style="font-size: 0.75rem; color: #64748b; margin-bottom: 0.5rem; line-height: 1.35;">
          <b style="color: #94a3b8;">Prevents:</b> ${escapeHtml(wf.why)}
        </div>
      ` : ''}

      ${wf.source ? `
        <div style="font-size: 0.7rem; color: #475569; margin-bottom: 0.6rem; font-family: var(--font-mono);">
          <b>Source:</b> ${escapeHtml(wf.source)}
        </div>
      ` : ''}

      <div style="display: flex; gap: 0.4rem; justify-content: flex-end; align-items: center; margin-top: auto; padding-top: 0.6rem; border-top: 1px dashed rgba(255,255,255,0.08);">
        <button type="button" class="btn-fire-wf" data-wf-id="${escapeHtml(wf.id)}" style="background: rgba(56, 189, 248, 0.12); border: 1px solid rgba(56, 189, 248, 0.3); color: #38bdf8; font-size: 0.74rem; padding: 0.25rem 0.55rem; border-radius: 5px; cursor: pointer;" title="Record an operational fire for this tool">
          ⚡ Fire
        </button>
        <button type="button" class="btn-edit-wf" data-wf-id="${escapeHtml(wf.id)}" style="background: rgba(255, 255, 255, 0.05); border: 1px solid var(--border-color); color: #cbd5e1; font-size: 0.74rem; padding: 0.25rem 0.55rem; border-radius: 5px; cursor: pointer;">
          ✏️ Edit
        </button>
        ${isRetired ? `
          <button type="button" class="btn-reactivate-wf" data-wf-id="${escapeHtml(wf.id)}" style="background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.3); color: #34d399; font-size: 0.74rem; padding: 0.25rem 0.55rem; border-radius: 5px; cursor: pointer;">
            ♻️ Reactivate
          </button>
        ` : `
          <button type="button" class="btn-retire-wf" data-wf-id="${escapeHtml(wf.id)}" style="background: rgba(244, 63, 94, 0.12); border: 1px solid rgba(244, 63, 94, 0.3); color: #f87171; font-size: 0.74rem; padding: 0.25rem 0.55rem; border-radius: 5px; cursor: pointer;">
            💤 Retire
          </button>
        `}
      </div>
    `;

    const btnFire = card.querySelector(".btn-fire-wf");
    if (btnFire) {
      btnFire.addEventListener("click", async () => {
        await handleRecordFire(wf.id);
      });
    }

    const btnEdit = card.querySelector(".btn-edit-wf");
    if (btnEdit) {
      btnEdit.addEventListener("click", () => {
        openMintWorkflowModal(wf);
      });
    }

    const btnRetire = card.querySelector(".btn-retire-wf");
    if (btnRetire) {
      btnRetire.addEventListener("click", async () => {
        await handleRetireWorkflow(wf.id);
      });
    }

    const btnReactivate = card.querySelector(".btn-reactivate-wf");
    if (btnReactivate) {
      btnReactivate.addEventListener("click", async () => {
        await handleReactivateWorkflow(wf.id);
      });
    }

    container.appendChild(card);
  });
}

function setupCabinetEventListeners() {
  const searchInput = document.getElementById("input-cabinet-search");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      currentCabinetSearch = e.target.value.trim();
      renderCabinetWorkflows();
    });
  }

  document.querySelectorAll("[data-cabinet-filter]").forEach(pill => {
    pill.addEventListener("click", () => {
      document.querySelectorAll("[data-cabinet-filter]").forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      currentCabinetFilter = pill.getAttribute("data-cabinet-filter") || "all";
      renderCabinetWorkflows();
    });
  });

  const btnOpenMint = document.getElementById("btn-open-mint-workflow-modal");
  if (btnOpenMint) {
    btnOpenMint.addEventListener("click", () => {
      openMintWorkflowModal();
    });
  }

  const btnCloseModal = document.getElementById("btn-close-cabinet-wf-modal");
  const btnCancelModal = document.getElementById("btn-cancel-cabinet-wf");
  if (btnCloseModal) btnCloseModal.addEventListener("click", closeMintWorkflowModal);
  if (btnCancelModal) btnCancelModal.addEventListener("click", closeMintWorkflowModal);

  const wfModal = document.getElementById("cabinet-wf-modal-overlay");
  if (wfModal) {
    wfModal.addEventListener("click", (e) => {
      if (e.target === wfModal) closeMintWorkflowModal();
    });
  }

  const form = document.getElementById("cabinet-wf-form");
  if (form) {
    form.addEventListener("submit", handleCabinetFormSubmit);
  }

  const btnSync = document.getElementById("btn-sync-cabinet");
  if (btnSync) {
    btnSync.addEventListener("click", async () => {
      btnSync.textContent = "⏳ Syncing...";
      try {
        const res = await fetch("/api/cabinet/sync", { method: "POST" });
        const data = await res.json();
        alert(data.message || "The Cabinet synced with markdown successfully!");
        loadCabinetWorkflows();
        loadCabinetHealth();
      } catch (err) {
        alert("Sync failed: " + err.message);
      } finally {
        btnSync.textContent = "🔄 2-Way Sync";
      }
    });
  }
}

function openMintWorkflowModal(wf = null) {
  const modal = document.getElementById("cabinet-wf-modal-overlay");
  const titleEl = document.getElementById("cabinet-wf-modal-title");
  const idHidden = document.getElementById("cabinet-wf-id-hidden");
  const titleInput = document.getElementById("cabinet-wf-title");
  const catSelect = document.getElementById("cabinet-wf-category");
  const customIdInput = document.getElementById("cabinet-wf-custom-id");
  const triggerInput = document.getElementById("cabinet-wf-trigger");
  const moveInput = document.getElementById("cabinet-wf-move");
  const whyInput = document.getElementById("cabinet-wf-why");
  const sourceInput = document.getElementById("cabinet-wf-source");
  const submitBtn = document.getElementById("btn-submit-cabinet-wf");

  if (!modal) return;

  if (wf) {
    if (titleEl) titleEl.textContent = `✏️ Amend Cabinet Workflow [${wf.id}]`;
    if (idHidden) idHidden.value = wf.id;
    if (titleInput) titleInput.value = wf.title || "";
    if (catSelect) catSelect.value = wf.category || "protocol";
    if (customIdInput) {
      customIdInput.value = wf.id || "";
      customIdInput.disabled = true;
    }
    if (triggerInput) triggerInput.value = wf.trigger || "";
    if (moveInput) moveInput.value = wf.move || "";
    if (whyInput) whyInput.value = wf.why || "";
    if (sourceInput) sourceInput.value = wf.source || "";
    if (submitBtn) submitBtn.innerHTML = `<span>💾 Save Amendments</span>`;
  } else {
    if (titleEl) titleEl.textContent = `✨ Mint New Cabinet Workflow`;
    if (idHidden) idHidden.value = "";
    if (titleInput) titleInput.value = "";
    if (catSelect) catSelect.value = "protocol";
    if (customIdInput) {
      customIdInput.value = "";
      customIdInput.disabled = false;
    }
    if (triggerInput) triggerInput.value = "";
    if (moveInput) moveInput.value = "";
    if (whyInput) whyInput.value = "";
    if (sourceInput) sourceInput.value = "";
    if (submitBtn) submitBtn.innerHTML = `<span>💾 Lock Heuristic</span>`;
  }

  modal.style.display = "flex";
}

function closeMintWorkflowModal() {
  const modal = document.getElementById("cabinet-wf-modal-overlay");
  if (modal) modal.style.display = "none";
}

async function handleCabinetFormSubmit(e) {
  e.preventDefault();
  const idHidden = document.getElementById("cabinet-wf-id-hidden")?.value.trim();
  const title = document.getElementById("cabinet-wf-title")?.value.trim();
  const category = document.getElementById("cabinet-wf-category")?.value.trim();
  const customId = document.getElementById("cabinet-wf-custom-id")?.value.trim();
  const trigger = document.getElementById("cabinet-wf-trigger")?.value.trim();
  const move = document.getElementById("cabinet-wf-move")?.value.trim();
  const why = document.getElementById("cabinet-wf-why")?.value.trim();
  const source = document.getElementById("cabinet-wf-source")?.value.trim();

  if (!title || !trigger || !move) {
    alert("Please provide Title, Trigger, and Move.");
    return;
  }

  try {
    if (idHidden) {
      const res = await fetch(`/api/cabinet/workflows/${idHidden}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          category,
          trigger,
          move,
          why,
          source
        })
      });
      if (!res.ok) throw new Error("Failed to amend workflow");
    } else {
      const res = await fetch("/api/cabinet/workflows", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          category,
          custom_id: customId || null,
          trigger,
          move,
          why,
          source,
          created_by: "Operator"
        })
      });
      if (!res.ok) throw new Error("Failed to mint workflow");
    }

    closeMintWorkflowModal();
    await loadCabinetWorkflows();
    await loadCabinetHealth();
  } catch (err) {
    alert("Error saving workflow: " + err.message);
  }
}

async function handleRecordFire(wfId) {
  try {
    const res = await fetch(`/api/cabinet/workflows/${wfId}/fire`, { method: "POST" });
    if (res.ok) {
      await loadCabinetWorkflows();
    }
  } catch (err) {
    console.error("Failed to record fire:", err);
  }
}

async function handleRetireWorkflow(wfId) {
  const reason = prompt(`Retire workflow [${wfId}]?\nEnter optional reason (e.g. Superseded by newer pattern):`, "Superseded or stale");
  if (reason === null) return;

  try {
    const res = await fetch(`/api/cabinet/workflows/${wfId}/retire`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason })
    });
    if (res.ok) {
      await loadCabinetWorkflows();
      await loadCabinetHealth();
    }
  } catch (err) {
    alert("Failed to retire workflow: " + err.message);
  }
}

async function handleReactivateWorkflow(wfId) {
  try {
    const res = await fetch(`/api/cabinet/workflows/${wfId}/reactivate`, { method: "POST" });
    if (res.ok) {
      await loadCabinetWorkflows();
      await loadCabinetHealth();
    }
  } catch (err) {
    alert("Failed to reactivate workflow: " + err.message);
  }
}


