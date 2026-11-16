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
  patientModal: document.getElementById("patient-modal"),
  missingForms: document.getElementById("missing-forms"),
  createFiles: document.getElementById("create-files"),
  cancelFiles: document.getElementById("cancel-files"),
  modalStatus: document.getElementById("modal-status"),
};

/** @type {{value: string, text: string}[]} */
let clinicOptions = [];
/** @type {Map<string, {value: string, text: string}[]>} */
const servicesCache = new Map();
let rowSeq = 0;
let fileSubmitInFlight = false;

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

function setModalStatus(message, kind = "") {
  els.modalStatus.textContent = message || "";
  els.modalStatus.className = `modal-status ${kind}`.trim();
}

function hideMissing() {
  els.missingForms.innerHTML = "";
  els.createFiles.disabled = true;
  setModalStatus("");
  if (els.patientModal.open) els.patientModal.close();
}

function registrationError(item) {
  if (!/^\d{10}$/.test(item.national_id)) {
    return "رقم الهوية أو الإقامة يجب أن يتكون من 10 أرقام.";
  }
  if ((item.name || "").trim().length < 2) return "الاسم بالكامل مطلوب.";
  if (!item.birth_date) return "تاريخ الميلاد مطلوب.";
  const phoneDigits = (item.phone || "").replace(/\D/g, "");
  if (phoneDigits.length < 9 || phoneDigits.length > 15) return "رقم الجوال غير صالح.";
  if (!item.gender) return "الجنس مطلوب.";
  if (!item.nationality) return "الجنسية مطلوبة.";
  return "";
}

function syncFileButton() {
  const cards = Array.from(els.missingForms.querySelectorAll(".file-card"));
  const ready = cards.length > 0 && cards.every((card) => {
    const nationalId = card.querySelector('[data-file="national_id"]').value.trim();
    const name = card.querySelector('[data-file="name"]').value.trim();
    const birthDate = card.querySelector('[data-file="birth_date"]').value;
    const phone = card.querySelector('[data-file="phone"]').value.trim();
    const gender = card.querySelector('[data-file="gender"]').value;
    const nationality = card.querySelector('[data-file="nationality"]').value;
    return nationalId.length === 10 && name && birthDate && phone && gender && nationality;
  });
  els.createFiles.disabled = !ready;
}

function showMissing(rows) {
  els.missingForms.innerHTML = "";
  if (!rows.length) {
    hideMissing();
    return;
  }

  rows.forEach((item, index) => {
    const card = document.createElement("article");
    card.className = "file-card";
    card.dataset.clinic = item.clinic || "";
    card.dataset.service = item.service || "";
    card.dataset.amount = item.amount || "";
    card.dataset.date = item.date || "";
    card.dataset.clinicLabel = item.clinic_label || "";
    card.dataset.serviceLabel = item.service_label || "";
    card.innerHTML = `
      <div class="row-top">
        <span class="row-number">${index + 1}</span>
        <span class="row-title">${escapeHtml(item.clinic_label || item.clinic || "Invoice")} · ${escapeHtml(item.service_label || item.service || "service")} · ${escapeHtml(item.amount || "")}</span>
      </div>
      <div class="file-grid">
        <label class="field">
          <span>رقم الهوية / الإقامة</span>
          <input data-file="national_id" type="text" inputmode="numeric" maxlength="10" value="${escapeHtml(item.national_id || "")}" required />
        </label>
        <label class="field">
          <span>الاسم بالكامل</span>
          <input data-file="name" type="text" value="${escapeHtml(item.name || "")}" required />
        </label>
        <label class="field">
          <span>تاريخ الميلاد</span>
          <input data-file="birth_date" type="date" value="${escapeHtml(item.birth_date || "")}" required />
        </label>
        <label class="field">
          <span>رقم الجوال</span>
          <input data-file="phone" type="tel" value="${escapeHtml(item.phone || "")}" placeholder="05xxxxxxxx" required />
        </label>
        <label class="field">
          <span>الجنس</span>
          <select data-file="gender" required>
            <option value="">اختر</option>
            <option value="1">ذكر</option>
            <option value="2">أنثى</option>
          </select>
        </label>
        <label class="field">
          <span>الجنسية</span>
          <select data-file="nationality" required>
            <option value="1">Saudi</option>
            <option value="27">Other</option>
          </select>
        </label>
      </div>
    `;
    card.querySelectorAll("input, select").forEach((el) => {
      el.addEventListener("input", syncFileButton);
      el.addEventListener("change", syncFileButton);
    });
    const gender = card.querySelector('[data-file="gender"]');
    const nationality = card.querySelector('[data-file="nationality"]');
    if (item.gender) gender.value = item.gender;
    if (item.nationality) nationality.value = item.nationality;
    els.missingForms.appendChild(card);
  });
  syncFileButton();
  if (!els.patientModal.open) els.patientModal.showModal();
  const firstName = els.missingForms.querySelector('[data-file="name"]');
  if (firstName) firstName.focus();
}

function collectFileItems() {
  return Array.from(els.missingForms.querySelectorAll(".file-card")).map((card) => ({
    national_id: card.querySelector('[data-file="national_id"]').value.trim(),
    name: card.querySelector('[data-file="name"]').value.trim(),
    birth_date: card.querySelector('[data-file="birth_date"]').value,
    phone: card.querySelector('[data-file="phone"]').value.trim(),
    gender: card.querySelector('[data-file="gender"]').value,
    nationality: card.querySelector('[data-file="nationality"]').value,
    clinic: card.dataset.clinic,
    service: card.dataset.service,
    amount: card.dataset.amount,
    date: card.dataset.date,
    clinic_label: card.dataset.clinicLabel || "",
    service_label: card.dataset.serviceLabel || "",
  }));
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
      const fileNote = item.file_created ? " · file created" : "";
      const link = item.list_url || item.invoice_url;
      return `<li>${escapeHtml((ids || "Invoice created") + fileNote)}${
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
        `${result.missing_count} patient(s) have no file — complete the registration window.`,
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

els.cancelFiles.addEventListener("click", () => {
  if (fileSubmitInFlight) return;
  hideMissing();
  log("Registration cancelled. Invoice rows were kept.");
});

els.patientModal.addEventListener("cancel", (event) => {
  event.preventDefault();
  if (fileSubmitInFlight) return;
  hideMissing();
});

els.createFiles.addEventListener("click", async () => {
  if (fileSubmitInFlight) return;
  const items = collectFileItems();
  const problem = items.map(registrationError).find(Boolean);
  if (problem) {
    setModalStatus(problem, "err");
    return;
  }
  if (!items.length || els.createFiles.disabled) return;

  fileSubmitInFlight = true;
  els.createFiles.disabled = true;
  els.createFiles.classList.add("busy");
  els.createFiles.textContent = "Creating…";
  els.cancelFiles.disabled = true;
  els.submit.disabled = true;
  els.addPatient.disabled = true;
  setModalStatus("جارٍ إنشاء الملف في إمداد ثم متابعة الفاتورة…", "loading");
  setPill("Running", "loading");
  log(`Creating ${items.length} patient file${items.length === 1 ? "" : "s"}, then the invoice${items.length === 1 ? "" : "s"}…`);

  try {
    const result = await api("/api/invoices/batch", {
      method: "POST",
      body: JSON.stringify({
        items: items.map(({ national_id, clinic, service, amount, date, name, birth_date, phone, gender, nationality }) => ({
          national_id,
          clinic,
          service,
          amount,
          date,
          name,
          birth_date,
          phone,
          gender,
          nationality,
        })),
        headed: els.headed.checked,
      }),
    });

    const labelByNid = new Map(
      items.map((item) => [
        item.national_id,
        { clinic_label: item.clinic_label, service_label: item.service_label },
      ])
    );
    const drafts = new Map(items.map((item) => [item.national_id, item]));
    const missing = (result.missing_files || []).map((row) => ({
      ...(drafts.get(row.national_id) || {}),
      ...row,
      ...(labelByNid.get(row.national_id) || {}),
    }));
    const failed = (result.errors || []).map((row) => ({
      ...(drafts.get(row.national_id) || {}),
      ...row,
      ...(labelByNid.get(row.national_id) || {}),
    }));
    const filesCreated = (result.created || []).filter((item) => item.file_created).length;

    setPill(result.error_count ? "Error" : "Done", result.error_count ? "err" : "ok");
    if (filesCreated) log(`Created ${filesCreated} patient file(s) in IMDAD.`, "ok");
    log(
      `Created ${result.created_count || 0} invoice(s).`,
      result.created_count ? "ok" : ""
    );
    if (result.error_count) log(`${result.error_count} row(s) failed with errors.`, "err");
    showResult({ ...result, missing_files: missing });
    if (failed.length) {
      showMissing(failed);
      setModalStatus(failed[0].error || "تعذر إنشاء الملف. راجع البيانات وأعد المحاولة.", "err");
    } else if (missing.length) {
      showMissing(missing);
      setModalStatus("أكمل بيانات المرضى غير المسجلين.", "err");
    } else {
      hideMissing();
      setPill("Done", "ok");
    }
  } catch (err) {
    setPill("Error", "err");
    const message = err.message || "تعذر الاتصال بنظام إمداد. أعد المحاولة.";
    log(message, "err");
    setModalStatus(message, "err");
    syncFileButton();
  } finally {
    fileSubmitInFlight = false;
    els.createFiles.classList.remove("busy");
    els.createFiles.textContent = "Create Patient & Continue";
    els.cancelFiles.disabled = false;
    els.addPatient.disabled = false;
    syncSubmitEnabled();
    syncFileButton();
  }
});

export { showMissing, registrationError };

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
