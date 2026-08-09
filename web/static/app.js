const els = {
  form: document.getElementById("invoice-form"),
  rows: document.getElementById("patient-rows"),
  addPatient: document.getElementById("add-patient"),
  headed: document.getElementById("headed"),
  submit: document.getElementById("submit"),
  log: document.getElementById("log"),
  pill: document.getElementById("status-pill"),
  result: document.getElementById("result"),
  metaCount: document.getElementById("meta-count"),
  metaUser: document.getElementById("meta-user"),
  missingPanel: document.getElementById("missing-panel"),
  missingTableBody: document.querySelector("#missing-table tbody"),
};

/** @type {{value: string, text: string}[]} */
let clinicOptions = [];
/** @type {Map<string, {value: string, text: string}[]>} */
const servicesCache = new Map();
let rowSeq = 0;

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function setPill(text, kind = "") {
  els.pill.textContent = text;
  els.pill.className = `pill ${kind}`.trim();
}

function clearLog() {
  els.log.innerHTML = "";
}

function log(message, kind = "") {
  const li = document.createElement("li");
  if (kind) li.classList.add(kind);
  li.textContent = message;
  els.log.appendChild(li);
  els.log.scrollTop = els.log.scrollHeight;
}

function fillSelect(select, items, placeholder) {
  select.innerHTML = "";
  const first = document.createElement("option");
  first.value = "";
  first.textContent = placeholder;
  select.appendChild(first);
  for (const item of items) {
    const opt = document.createElement("option");
    opt.value = item.value;
    opt.textContent = item.text;
    select.appendChild(opt);
  }
}

function clinicLabel(value) {
  return clinicOptions.find((c) => c.value === value)?.text || value || "—";
}

function serviceLabel(select, value) {
  if (!select || !value) return value || "—";
  const opt = Array.from(select.options).find((o) => o.value === value);
  return opt?.textContent || value;
}

function rowElements() {
  return Array.from(els.rows.querySelectorAll(".patient-row"));
}

function syncMetaCount() {
  const count = rowElements().length;
  els.metaCount.textContent = count === 1 ? "1 patient" : `${count} patients`;
}

function syncSubmitEnabled() {
  const rows = rowElements();
  if (!rows.length) {
    els.submit.disabled = true;
    return;
  }
  const allValid = rows.every((row) => {
    const nationalId = row.querySelector('[data-field="national_id"]').value.trim();
    const clinic = row.querySelector('[data-field="clinic"]').value;
    const service = row.querySelector('[data-field="service"]').value;
    const amount = row.querySelector('[data-field="amount"]').value;
    const date = row.querySelector('[data-field="date"]').value;
    return nationalId.length >= 5 && clinic && service && amount !== "" && date;
  });
  els.submit.disabled = !allValid;
}

function collectItems() {
  return rowElements().map((row) => ({
    national_id: row.querySelector('[data-field="national_id"]').value.trim(),
    clinic: row.querySelector('[data-field="clinic"]').value,
    service: row.querySelector('[data-field="service"]').value,
    amount: String(row.querySelector('[data-field="amount"]').value),
    date: row.querySelector('[data-field="date"]').value,
    clinic_label: clinicLabel(row.querySelector('[data-field="clinic"]').value),
    service_label: serviceLabel(
      row.querySelector('[data-field="service"]'),
      row.querySelector('[data-field="service"]').value
    ),
  }));
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    const message = Array.isArray(detail)
      ? detail.map((d) => d.msg || JSON.stringify(d)).join("; ")
      : detail || `Request failed (${res.status})`;
    throw new Error(message);
  }
  return data;
}

async function loadMeta() {
  const meta = await api("/api/meta");
  els.metaUser.textContent = meta.username
    ? `Signed in as ${meta.username}`
    : "Signed in as —";
}

async function loadClinics() {
  setPill("Loading", "loading");
  log("Signing in and loading clinics…");
  const data = await api("/api/clinics");
  clinicOptions = data.items || [];
  setPill("Ready", "ok");
  log(`Loaded ${clinicOptions.length} clinics.`, "ok");
  for (const row of rowElements()) {
    const clinicSelect = row.querySelector('[data-field="clinic"]');
    const previous = clinicSelect.value;
    fillSelect(clinicSelect, clinicOptions, "Choose clinic");
    if (previous) clinicSelect.value = previous;
    clinicSelect.disabled = false;
  }
  syncSubmitEnabled();
}

async function loadServicesForRow(row, clinicId) {
  const serviceSelect = row.querySelector('[data-field="service"]');
  if (!clinicId) {
    fillSelect(serviceSelect, [], "Select a clinic first");
    serviceSelect.disabled = true;
    syncSubmitEnabled();
    return;
  }

  serviceSelect.disabled = true;
  fillSelect(serviceSelect, [], "Loading services…");
  syncSubmitEnabled();

  let items = servicesCache.get(clinicId);
  if (!items) {
    const data = await api(`/api/services?clinic_id=${encodeURIComponent(clinicId)}`);
    items = data.items || [];
    servicesCache.set(clinicId, items);
  }

  fillSelect(serviceSelect, items, "Choose service");
  serviceSelect.disabled = false;
  syncSubmitEnabled();
}

function renumberRows() {
  rowElements().forEach((row, index) => {
    row.querySelector(".row-number").textContent = String(index + 1);
  });
  syncMetaCount();
}

function addPatientRow(prefill = {}) {
  rowSeq += 1;
  const id = `row-${rowSeq}`;
  const row = document.createElement("article");
  row.className = "patient-row";
  row.dataset.rowId = id;
  row.innerHTML = `
    <div class="row-top">
      <span class="row-number">1</span>
      <span class="row-title">Patient</span>
      <button type="button" class="ghost-danger remove-row" aria-label="Remove patient">
        Remove
      </button>
    </div>
    <div class="row-grid">
      <label class="field">
        <span>National ID</span>
        <input
          data-field="national_id"
          type="text"
          inputmode="numeric"
          placeholder="e.g. 2576425918"
          required
        />
      </label>
      <label class="field">
        <span>Clinic</span>
        <select data-field="clinic" required disabled>
          <option value="">${clinicOptions.length ? "Choose clinic" : "Loading clinics…"}</option>
        </select>
      </label>
      <label class="field">
        <span>Service</span>
        <select data-field="service" required disabled>
          <option value="">Select a clinic first</option>
        </select>
      </label>
      <label class="field">
        <span>Price</span>
        <input
          data-field="amount"
          type="number"
          min="0"
          step="0.01"
          placeholder="0.00"
          required
        />
      </label>
      <label class="field">
        <span>Invoice date</span>
        <input data-field="date" type="date" required />
      </label>
    </div>
  `;

  const nationalId = row.querySelector('[data-field="national_id"]');
  const clinic = row.querySelector('[data-field="clinic"]');
  const service = row.querySelector('[data-field="service"]');
  const amount = row.querySelector('[data-field="amount"]');
  const date = row.querySelector('[data-field="date"]');
  const removeBtn = row.querySelector(".remove-row");

  fillSelect(clinic, clinicOptions, clinicOptions.length ? "Choose clinic" : "Loading clinics…");
  clinic.disabled = !clinicOptions.length;
  date.value = prefill.date || todayIso();
  if (prefill.national_id) nationalId.value = prefill.national_id;
  if (prefill.amount != null) amount.value = prefill.amount;

  [nationalId, amount, date, service].forEach((el) => {
    el.addEventListener("input", syncSubmitEnabled);
    el.addEventListener("change", syncSubmitEnabled);
  });

  clinic.addEventListener("change", async () => {
    try {
      await loadServicesForRow(row, clinic.value);
    } catch (err) {
      setPill("Error", "err");
      log(err.message || String(err), "err");
    }
  });

  removeBtn.addEventListener("click", () => {
    row.remove();
    renumberRows();
    syncSubmitEnabled();
    if (!rowElements().length) {
      hideMissing();
      els.result.classList.add("hidden");
    }
  });

  els.rows.appendChild(row);
  renumberRows();
  syncSubmitEnabled();
  nationalId.focus();
  return row;
}

function hideMissing() {
  els.missingPanel.classList.add("hidden");
  els.missingTableBody.innerHTML = "";
}

function showMissing(rows) {
  els.missingTableBody.innerHTML = "";
  if (!rows.length) {
    hideMissing();
    return;
  }

  rows.forEach((item, index) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${index + 1}</td>
      <td>${escapeHtml(item.national_id || "—")}</td>
      <td>${escapeHtml(item.clinic_label || item.clinic || "—")}</td>
      <td>${escapeHtml(item.service_label || item.service || "—")}</td>
      <td>${escapeHtml(item.amount || "—")}</td>
      <td>${escapeHtml(item.date || "—")}</td>
      <td>${escapeHtml(item.reason || "No patient file found")}</td>
    `;
    els.missingTableBody.appendChild(tr);
  });
  els.missingPanel.classList.remove("hidden");
  els.missingPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function showResult(payload) {
  els.result.classList.remove("hidden");
  const created = payload.created || [];
  const missing = payload.missing_files || [];
  const errors = payload.errors || [];

  const createdLines = created
    .map((item) => {
      const ids = [
        item.patient_name || null,
        item.national_id ? `NID ${item.national_id}` : null,
        item.serial ? `serial ${item.serial}` : null,
        item.rec_id ? `rec_id ${item.rec_id}` : null,
      ]
        .filter(Boolean)
        .join(" · ");
      const link = item.list_url || item.invoice_url;
      return `<li>${escapeHtml(ids || "Invoice created")}${
        link
          ? ` — <a href="${escapeHtml(link)}" target="_blank" rel="noopener">open</a>`
          : ""
      }</li>`;
    })
    .join("");

  const errorLines = errors
    .map(
      (item) =>
        `<li class="err-line">${escapeHtml(item.national_id || "Row")}: ${escapeHtml(
          item.error || "Failed"
        )}</li>`
    )
    .join("");

  els.result.innerHTML = `
    <h3>Batch complete</h3>
    <p>Created: ${created.length} · Without file: ${missing.length} · Errors: ${errors.length}</p>
    ${created.length ? `<ul class="result-list">${createdLines}</ul>` : "<p>No invoices were created.</p>"}
    ${errors.length ? `<ul class="result-list">${errorLines}</ul>` : ""}
  `;
}

els.addPatient.addEventListener("click", () => {
  addPatientRow();
  log("Added a patient row.", "ok");
});

els.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const items = collectItems();
  if (!items.length) {
    setPill("Error", "err");
    log("Add at least one patient first.", "err");
    return;
  }

  hideMissing();
  els.result.classList.add("hidden");
  els.submit.disabled = true;
  els.addPatient.disabled = true;
  els.submit.classList.add("busy");
  els.submit.textContent = "Creating…";
  setPill("Running", "loading");
  clearLog();
  log(`Processing ${items.length} patient${items.length === 1 ? "" : "s"}…`);
  log("Checking each national ID for a patient file…");
  log("Creating invoices for patients that have a file…");

  try {
    const result = await api("/api/invoices/batch", {
      method: "POST",
      body: JSON.stringify({
        items: items.map(({ national_id, clinic, service, amount, date }) => ({
          national_id,
          clinic,
          service,
          amount,
          date,
        })),
        headed: els.headed.checked,
      }),
    });

    const labelByNid = new Map(
      items.map((item) => [
        item.national_id,
        {
          clinic_label: item.clinic_label,
          service_label: item.service_label,
        },
      ])
    );

    const missing = (result.missing_files || []).map((row) => ({
      ...row,
      ...(labelByNid.get(row.national_id) || {}),
    }));

    setPill("Done", "ok");
    log(
      `Created ${result.created_count || 0} invoice(s).`,
      result.created_count ? "ok" : ""
    );
    if (result.missing_count) {
      log(
        `${result.missing_count} patient(s) have no file — see the table below.`,
        "err"
      );
    }
    if (result.error_count) {
      log(`${result.error_count} row(s) failed with errors.`, "err");
    }
    showResult({ ...result, missing_files: missing });
    showMissing(missing);
  } catch (err) {
    setPill("Error", "err");
    log(err.message || String(err), "err");
  } finally {
    els.submit.classList.remove("busy");
    els.submit.textContent = "Create invoice";
    els.addPatient.disabled = false;
    syncSubmitEnabled();
  }
});

(async function boot() {
  addPatientRow();
  try {
    await loadMeta();
    await loadClinics();
  } catch (err) {
    setPill("Error", "err");
    clearLog();
    log(err.message || String(err), "err");
  }
})();
