const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const cardsContainer = document.getElementById("cards");
const cardTemplate = document.getElementById("card-template");
const sectionTemplate = document.getElementById("section-template");
const optionsToggle = document.getElementById("options-toggle");
const optionsForm = document.getElementById("options-form");

const SECTION_LABELS = {
  BPA: "Balanço Patrimonial Ativo (BPA)",
  BPP: "Balanço Patrimonial Passivo (BPP)",
  DRE: "Demonstração do Resultado (DRE)",
  DRA: "Demonstração do Resultado Abrangente (DRA)",
  DFC: "Demonstração do Fluxo de Caixa (DFC)",
  DMPL: "Demonstração das Mutações do Patrimônio Líquido (DMPL)",
  DVA: "Demonstração do Valor Adicionado (DVA)",
};

const ICONS = {
  file: `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
      <path d="M7 3h6l5 5v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z" />
      <path d="M13 3v5h5" />
    </svg>
  `,
  success: `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <path d="M20 11a8 8 0 1 1-16 0 8 8 0 0 1 16 0z" />
      <path d="m9.5 11.5 2 2 3.5-3.5" />
    </svg>
  `,
  warning: `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 3 2 19h20L12 3z" />
      <path d="M12 9v4" />
      <path d="M12 17h.01" />
    </svg>
  `,
  download: `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 5v10" />
      <path d="m7 10 5 5 5-5" />
      <path d="M4 19h16" />
    </svg>
  `,
};

const renderIcon = (name, variant) =>
  `<span class="icon${variant ? ` icon-${variant}` : ""}" aria-hidden="true">${ICONS[name]}</span>`;

const ENGINE_LABELS = {
  auto: "Automático",
  pdfplumber: "pdfplumber",
  camelot: "camelot",
};

const FORMAT_LABELS = {
  csv: "CSV",
  parquet: "Parquet",
};

const DEFAULT_OPTIONS = {
  engine: "auto",
  stitch: true,
  normalizeSchema: true,
  downloadFormat: "csv",
  includeReport: true,
};

const formatDownloadLabel = (format) => {
  const key = (format || "").toLowerCase();
  return FORMAT_LABELS[key] || key.toUpperCase() || "CSV";
};

const resolveEngineLabel = (engine) => {
  const key = (engine || "").toLowerCase();
  return ENGINE_LABELS[key] || engine || ENGINE_LABELS.auto;
};

const getCurrentOptions = () => {
  if (!optionsForm) return { ...DEFAULT_OPTIONS };
  return {
    engine: (optionsForm.elements.engine?.value || DEFAULT_OPTIONS.engine).toLowerCase(),
    stitch: optionsForm.elements.stitch?.checked ?? DEFAULT_OPTIONS.stitch,
    normalizeSchema:
      optionsForm.elements.normalize_schema?.checked ?? DEFAULT_OPTIONS.normalizeSchema,
    downloadFormat:
      (optionsForm.elements.download_format?.value || DEFAULT_OPTIONS.downloadFormat).toLowerCase(),
    includeReport:
      optionsForm.elements.include_report?.checked ?? DEFAULT_OPTIONS.includeReport,
  };
};

const optionsAreDefault = (options) =>
  options.engine === DEFAULT_OPTIONS.engine &&
  options.stitch === DEFAULT_OPTIONS.stitch &&
  options.normalizeSchema === DEFAULT_OPTIONS.normalizeSchema &&
  options.downloadFormat === DEFAULT_OPTIONS.downloadFormat &&
  options.includeReport === DEFAULT_OPTIONS.includeReport;

const setOptionsPanelState = (open) => {
  if (!optionsToggle || !optionsForm) return;
  optionsToggle.setAttribute("aria-expanded", String(open));
  optionsForm.setAttribute("aria-hidden", String(!open));
  optionsForm.classList.toggle("open", open);
};

const clearCardBanner = (card) => {
  const banner = card.querySelector(".card-banner");
  if (!banner) return;
  banner.hidden = true;
  banner.classList.remove("error", "info");
  banner.innerHTML = "";
};

const showCardBanner = (card, message, hint, variant = "error") => {
  const banner = card.querySelector(".card-banner");
  if (!banner) return;
  banner.hidden = false;
  banner.classList.remove("error", "info");
  banner.classList.add(variant);
  banner.innerHTML = `
    <span class="banner-message">${message}</span>
    ${hint ? `<span class="banner-hint">${hint}</span>` : ""}
  `;
};

const parseErrorDetail = (payload) => {
  if (!payload) {
    return { message: "Não foi possível processar este arquivo." };
  }

  if (typeof payload === "string") {
    return { message: payload };
  }

  if (payload.detail) {
    return parseErrorDetail(payload.detail);
  }

  return {
    message: payload.message || "Não foi possível processar este arquivo.",
    hint: payload.hint || payload.suggestion || null,
  };
};

if (optionsToggle && optionsForm) {
  setOptionsPanelState(false);
  optionsToggle.addEventListener("click", () => {
    const expanded = optionsToggle.getAttribute("aria-expanded") === "true";
    setOptionsPanelState(!expanded);
  });
}

const formatBytes = (bytes) => {
  if (!Number.isFinite(bytes)) return "";
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** exponent;
  return `${value.toFixed(value >= 10 || exponent === 0 ? 0 : 1)} ${units[exponent]}`;
};

const formatTime = (ms) => {
  if (!Number.isFinite(ms)) return "";
  if (ms < 1000) return `${ms.toFixed(0)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
};

const parseFileName = (header, fallback) => {
  if (!header) return fallback;
  const match = header.match(/filename\*?=([^;]+)/i);
  if (!match) return fallback;
  let filename = match[1].trim();
  filename = filename.replace(/^UTF-8''/, "");
  return decodeURIComponent(filename.replace(/"/g, "")) || fallback;
};

const downloadWithName = async (url, fallbackName) => {
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error("Falha no download");
    const blob = await response.blob();
    const disposition = response.headers.get("Content-Disposition");
    const filename = parseFileName(disposition, fallbackName || "download");
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    setTimeout(() => {
      URL.revokeObjectURL(link.href);
      link.remove();
    }, 1000);
  } catch (error) {
    console.error(error);
    alert("Não foi possível baixar o arquivo agora.");
  }
};

const createCard = (file, optionsSnapshot) => {
  const fragment = cardTemplate.content.cloneNode(true);
  const card = fragment.querySelector(".card");
  const fileNameEl = card.querySelector(".file-name .file-label");
  const fileIcon = card.querySelector(".file-name .icon");
  const fileMetaEl = card.querySelector(".file-meta");
  const progressBar = card.querySelector(".progress-bar");
  const cardBody = card.querySelector(".card-body");

  fileIcon.innerHTML = ICONS.file;
  fileNameEl.textContent = file.name || "documento.pdf";
  fileMetaEl.textContent = formatBytes(file.size);

  card.classList.add("loading");
  cardsContainer.prepend(card);

  const options = optionsSnapshot || getCurrentOptions();
  card.dataset.requestedEngine = options.engine;
  card.dataset.downloadFormat = options.downloadFormat;

  uploadFile(
    file,
    {
      card,
      fileIcon,
      fileMetaEl,
      progressBar,
      cardBody,
    },
    options
  );
};

const buildSectionRow = (section, formatLabelText) => {
  const fragment = sectionTemplate.content.cloneNode(true);
  const container = fragment.querySelector(".section");
  const chip = fragment.querySelector(".section-chip");
  const meta = fragment.querySelector(".section-meta");
  const actions = fragment.querySelector(".section-actions");
  const previewHost = fragment.querySelector(".section-preview");
  const content = fragment.querySelector(".section-content");

  const label = SECTION_LABELS[section.key] || section.key;
  const contentId = `section-${section.key}-${Math.random().toString(36).slice(2)}`;
  content.id = contentId;
  chip.setAttribute("aria-controls", contentId);
  container.dataset.section = section.key;

  const status = document.createElement("span");
  status.className = "status";

  if (!section.present) {
    chip.innerHTML = `<span>${renderIcon("warning", "warning")}${label}</span>`;
    status.textContent = "Seção ausente";
    chip.appendChild(status);
    chip.disabled = true;
    chip.setAttribute("aria-disabled", "true");
    chip.setAttribute("aria-expanded", "false");
    container.classList.add("missing");
    meta.textContent = "Nenhum cabeçalho correspondente encontrado neste PDF.";
    return container;
  }

  chip.innerHTML = `<span>${renderIcon("success", "success")}${label}</span>`;
  status.textContent = `${section.table_count} tabela(s)`;
  chip.appendChild(status);

  const pages = section.pages ? `${section.pages[0]}–${section.pages[1]}` : "?";
  meta.textContent = `Páginas ${pages} • ${section.table_count} tabela(s)`;

  const badges = document.createElement("div");
  badges.className = "section-badges";

  if (section.engine) {
    const engineBadge = document.createElement("span");
    engineBadge.className = "section-badge";
    engineBadge.textContent = `Motor: ${resolveEngineLabel(section.engine)}`;
    badges.appendChild(engineBadge);
  }

  if (section.stitched === false) {
    const stitchBadge = document.createElement("span");
    stitchBadge.className = "section-badge";
    stitchBadge.textContent = "Stitch OFF";
    badges.appendChild(stitchBadge);
  }

  if (section.schema_normalized === false) {
    const schemaBadge = document.createElement("span");
    schemaBadge.className = "section-badge";
    schemaBadge.textContent = "Schema original";
    badges.appendChild(schemaBadge);
  }

  if (badges.children.length) {
    meta.appendChild(badges);
  }

  if (section.alerts && section.alerts.length) {
    const alertsBox = document.createElement("div");
    alertsBox.className = "alerts";
    section.alerts.forEach((alert) => {
      const alertEl = document.createElement("div");
      alertEl.className = "alert";
      const pageInfo = alert.page ? `p${alert.page}` : "página ?";
      const warnings = Array.isArray(alert.warnings)
        ? alert.warnings.join(", ")
        : "Irregularidade detectada na tabela.";
      alertEl.textContent = `${pageInfo}: ${warnings}`;
      alertsBox.appendChild(alertEl);
    });
    meta.appendChild(alertsBox);
  }

  if (section.download_url) {
    const button = document.createElement("button");
    button.className = "button secondary";
    button.type = "button";
    button.innerHTML = `${renderIcon("download")}Baixar ${formatLabelText} da seção`;
    button.addEventListener("click", () =>
      downloadWithName(section.download_url, section.download_name)
    );
    actions.appendChild(button);
  } else {
    const placeholder = document.createElement("div");
    placeholder.className = "empty-state";
    placeholder.textContent = "Nenhum conteúdo exportável para esta seção.";
    actions.appendChild(placeholder);
  }

  if (section.preview && section.preview.headers.length) {
    const table = document.createElement("table");
    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    section.preview.headers.forEach((header) => {
      const th = document.createElement("th");
      th.textContent = header;
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    section.preview.rows.forEach((row) => {
      const tr = document.createElement("tr");
      row.forEach((cell) => {
        const td = document.createElement("td");
        td.textContent = cell ?? "";
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);

    previewHost.appendChild(table);
  } else {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "Pré-visualização indisponível para esta seção.";
    previewHost.appendChild(empty);
  }

  chip.addEventListener("click", () => {
    const willOpen = !container.classList.contains("open");
    container.classList.toggle("open", willOpen);
    chip.setAttribute("aria-expanded", String(willOpen));
  });

  chip.setAttribute("aria-expanded", "false");

  return container;
};

const renderResult = (elements, data, requestedOptions = {}) => {
  const { card, fileIcon, fileMetaEl, progressBar, cardBody } = elements;
  progressBar.style.width = "100%";
  card.classList.remove("loading");
  card.classList.remove("error");
  card.classList.add("ready");
  const progressWrapper = card.querySelector(".progress-wrapper");
  if (progressWrapper) {
    progressWrapper.style.opacity = "0";
    setTimeout(() => {
      progressWrapper.style.display = "none";
    }, 400);
  }

  if (fileIcon) {
    fileIcon.innerHTML = ICONS.success;
    fileIcon.classList.add("icon-success");
  }

  if (fileMetaEl) {
    const current = fileMetaEl.textContent || "";
    fileMetaEl.textContent = current ? `${current} • pronto` : "Processamento concluído";
  }

  const summary = document.createElement("div");
  summary.className = "file-summary";
  summary.textContent = `Processado em ${formatTime(data.pdf.processing_time_ms)} • ${data.pdf.total_tables} tabela(s)`;

  const actions = document.createElement("div");
  actions.className = "card-actions";

  const serverOptions = data.options || {};
  const appliedOptions = {
    engine: serverOptions.engine || requestedOptions.engine || DEFAULT_OPTIONS.engine,
    effectiveEngines: serverOptions.effective_engines || [],
    stitch:
      serverOptions.stitch_tables ??
      (typeof requestedOptions.stitch === "boolean"
        ? requestedOptions.stitch
        : DEFAULT_OPTIONS.stitch),
    normalizeSchema:
      serverOptions.normalize_schema ??
      (typeof requestedOptions.normalizeSchema === "boolean"
        ? requestedOptions.normalizeSchema
        : DEFAULT_OPTIONS.normalizeSchema),
    downloadFormat:
      serverOptions.download_format ||
      requestedOptions.downloadFormat ||
      DEFAULT_OPTIONS.downloadFormat,
    includeReport:
      serverOptions.include_report ??
      (typeof requestedOptions.includeReport === "boolean"
        ? requestedOptions.includeReport
        : DEFAULT_OPTIONS.includeReport),
  };

  const formatLabelText = formatDownloadLabel(
    data.downloads?.format || appliedOptions.downloadFormat
  );

  if (data.downloads.zip) {
    const button = document.createElement("button");
    button.className = "button";
    button.type = "button";
    button.innerHTML = `${renderIcon("download")}Baixar ZIP (${formatLabelText})`;
    button.addEventListener("click", () =>
      downloadWithName(data.downloads.zip, data.downloads.zip_name)
    );
    actions.appendChild(button);
  }

  const cardGrid = document.createElement("div");
  cardGrid.className = "card-grid";

  const infoColumn = document.createElement("div");
  infoColumn.className = "card-info";
  infoColumn.appendChild(summary);
  if (actions.children.length) {
    infoColumn.appendChild(actions);
  }

  const enginesDisplay = appliedOptions.effectiveEngines.length
    ? appliedOptions.effectiveEngines.map(resolveEngineLabel).join(" / ")
    : resolveEngineLabel(appliedOptions.engine);

  const shouldShowOptions =
    !optionsAreDefault(appliedOptions) ||
    (appliedOptions.effectiveEngines.length > 0 &&
      (appliedOptions.effectiveEngines.length > 1 ||
        appliedOptions.effectiveEngines[0] !== appliedOptions.engine));

  if (shouldShowOptions) {
    const optionsSummary = document.createElement("div");
    optionsSummary.className = "options-summary";
    optionsSummary.textContent = `Motor: ${enginesDisplay} • Stitch ${
      appliedOptions.stitch ? "ON" : "OFF"
    } • Schema ${appliedOptions.normalizeSchema ? "normalizado" : "original"} • Formato ${
      formatLabelText
    }${appliedOptions.includeReport ? " • Relatório no ZIP" : ""}`;
    infoColumn.appendChild(optionsSummary);
  }

  const chipCollection = document.createElement("div");
  chipCollection.className = "chip-collection";
  const chipTitle = document.createElement("div");
  chipTitle.className = "file-summary";
  chipTitle.textContent = `Seções detectadas: ${Object.keys(data.pdf.spans).length}`;
  chipCollection.appendChild(chipTitle);

  const chipGroup = document.createElement("div");
  chipGroup.className = "chip-group";

  const sectionList = document.createElement("div");
  sectionList.className = "section-list";

  data.pdf.sections.forEach((section) => {
    const sectionNode = buildSectionRow(
      section,
      formatDownloadLabel(section.download_format || formatLabelText)
    );
    sectionList.appendChild(sectionNode);

    if (section.present) {
      const chipButton = document.createElement("button");
      chipButton.type = "button";
      chipButton.className = "chip-button";
      chipButton.innerHTML = `<span class="chip present">${renderIcon("success", "success")}${
        SECTION_LABELS[section.key] || section.key
      }</span>`;
      chipButton.setAttribute(
        "aria-label",
        `Mostrar prévia de ${SECTION_LABELS[section.key] || section.key}`
      );
      chipButton.addEventListener("click", () => {
        sectionList.querySelectorAll(".section.open").forEach((openSection) => {
          if (openSection.dataset.section !== section.key) {
            openSection.classList.remove("open");
            const toggle = openSection.querySelector(".section-chip");
            toggle?.setAttribute("aria-expanded", "false");
          }
        });
        const target = sectionList.querySelector(`[data-section="${section.key}"]`);
        if (target) {
          target.classList.add("open");
          const toggle = target.querySelector(".section-chip");
          toggle?.setAttribute("aria-expanded", "true");
          target.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
      chipGroup.appendChild(chipButton);
    } else {
      const chip = document.createElement("span");
      chip.className = "chip missing";
      chip.innerHTML = `${renderIcon("warning", "warning")}${SECTION_LABELS[section.key] || section.key}`;
      chipGroup.appendChild(chip);
    }
  });

  if (chipGroup.children.length) {
    chipCollection.appendChild(chipGroup);
  }

  if (!sectionList.children.length) {
    const placeholder = document.createElement("div");
    placeholder.className = "empty-state";
    placeholder.textContent = "Nenhuma seção consolidada encontrada neste PDF.";
    sectionList.appendChild(placeholder);
  }

  cardGrid.appendChild(infoColumn);
  cardGrid.appendChild(chipCollection);

  cardBody.innerHTML = "";
  const skeleton = card.querySelector(".card-skeleton");
  if (skeleton) skeleton.remove();
  cardBody.appendChild(cardGrid);

  const firstAvailable = sectionList.querySelector(".section:not(.missing)");
  if (firstAvailable) {
    firstAvailable.classList.add("open");
    const toggle = firstAvailable.querySelector(".section-chip");
    toggle?.setAttribute("aria-expanded", "true");
  }

  cardBody.appendChild(sectionList);
};

const uploadFile = (file, elements, options) => {
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/process");

  xhr.upload.onprogress = (event) => {
    if (!event.lengthComputable) return;
    const progress = Math.round((event.loaded / event.total) * 80);
    elements.progressBar.style.width = `${progress}%`;
  };

  xhr.onreadystatechange = () => {
    if (xhr.readyState !== XMLHttpRequest.DONE) return;

    if (xhr.status >= 200 && xhr.status < 300) {
      try {
        const data = JSON.parse(xhr.responseText);
        clearCardBanner(elements.card);
        renderResult(elements, data, options);
      } catch (error) {
        console.error(error);
        elements.card.classList.add("error");
        elements.card.classList.remove("loading");
        if (elements.fileIcon) {
          elements.fileIcon.innerHTML = ICONS.warning;
          elements.fileIcon.classList.add("icon-warning");
        }
        showCardBanner(
          elements.card,
          "Falha ao processar a resposta do servidor.",
          "Tente reenviar ou ajustar as opções avançadas.",
          "error"
        );
      }
    } else {
      elements.card.classList.add("error");
      elements.card.classList.remove("loading");
      elements.progressBar.style.width = "0%";
      if (elements.fileIcon) {
        elements.fileIcon.innerHTML = ICONS.warning;
        elements.fileIcon.classList.add("icon-warning");
      }
      let message = "Não foi possível processar este arquivo.";
      let hint;
      try {
        const parsed = JSON.parse(xhr.responseText);
        const detail = parseErrorDetail(parsed);
        message = detail.message || message;
        hint = detail.hint;
      } catch (parseError) {
        const detail = parseErrorDetail();
        message = detail.message;
      }
      showCardBanner(elements.card, message, hint, "error");
      const body = elements.card.querySelector(".card-body");
      body.textContent = message;
      body.classList.add("empty-state");
    }
  };

  const formData = new FormData();
  formData.append("file", file);
  const settings = { ...DEFAULT_OPTIONS, ...(options || {}) };
  formData.append("engine", settings.engine);
  formData.append("stitch", settings.stitch ? "true" : "false");
  formData.append("normalize_schema", settings.normalizeSchema ? "true" : "false");
  formData.append("download_format", settings.downloadFormat);
  formData.append("include_report", settings.includeReport ? "true" : "false");
  xhr.send(formData);
};

const handleFiles = (fileList) => {
  const files = Array.from(fileList || []);
  if (!files.length) return;
  const optionsSnapshot = getCurrentOptions();
  files.forEach((file) => {
    if (file.type && file.type !== "application/pdf") {
      alert(`Arquivo ignorado: ${file.name}`);
      return;
    }
    createCard(file, optionsSnapshot);
  });
};

fileInput.addEventListener("change", (event) => {
  handleFiles(event.target.files);
  fileInput.value = "";
});

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    fileInput.click();
  }
});

dropzone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropzone.classList.add("dragover");
});

dropzone.addEventListener("dragleave", () => {
  dropzone.classList.remove("dragover");
});

dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropzone.classList.remove("dragover");
  handleFiles(event.dataTransfer.files);
});
