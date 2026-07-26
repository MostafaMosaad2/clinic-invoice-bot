const els = {
  form: document.getElementById("invoice-form"),
  nationalId: document.getElementById("national-id"),
  findPatient: document.getElementById("find-patient"),
  clinic: document.getElementById("clinic"),
  service: document.getElementById("service"),
  amount: document.getElementById("amount"),
  date: document.getElementById("date"),
  headed: document.getElementById("headed"),
  submit: document.getElementById("submit"),
  log: document.getElementById("log"),
  pill: document.getElementById("status-pill"),
  result: document.getElementById("result"),
  metaPatient: document.getElementById("meta-patient"),
  metaUser: document.getElementById("meta-user"),
};

let selectedPatient = null;

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

function syncSubmitEnabled() {
  els.submit.disabled = !(
    selectedPatient &&
    els.clinic.value &&
    els.service.value &&
    els.amount.value &&
    els.date.value
  );
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
  els.clinic.disabled = true;
  els.service.disabled = true;
  syncSubmitEnabled();

  const data = await api("/api/clinics");
  fillSelect(els.clinic, data.items || [], "Choose clinic");
  els.clinic.disabled = false;
  fillSelect(els.service, [], "Select a clinic first");
  setPill("Ready", "ok");
  log(`Loaded ${data.items?.length || 0} clinics.`, "ok");
  syncSubmitEnabled();
}

async function loadServices(clinicId) {
  if (!clinicId) {
    fillSelect(els.service, [], "Select a clinic first");
    els.service.disabled = true;
    syncSubmitEnabled();
    return;
  }

  setPill("Loading", "loading");
  log("Loading services for selected clinic…");
  els.service.disabled = true;
  syncSubmitEnabled();

  const data = await api(`/api/services?clinic_id=${encodeURIComponent(clinicId)}`);
  fillSelect(els.service, data.items || [], "Choose service");
  els.service.disabled = false;
  setPill("Ready", "ok");
  log(`Loaded ${data.items?.length || 0} services.`, "ok");
  syncSubmitEnabled();
}

async function findPatient() {
  const nationalId = els.nationalId.value.trim();
  if (!nationalId) {
    throw new Error("Enter a national ID first.");
  }

  selectedPatient = null;
  els.metaPatient.textContent = "Patient —";
  syncSubmitEnabled();

  setPill("Loading", "loading");
  log(`Searching patient by national ID ${nationalId}…`);
  els.findPatient.disabled = true;

  try {
    const data = await api(
      `/api/patients?national_id=${encodeURIComponent(nationalId)}`
    );
    const items = data.items || [];
    if (!items.length) {
      throw new Error(`No patient found for national ID ${nationalId}`);
    }
    selectedPatient = items[0];
    if (items.length > 1) {
      log(`Found ${items.length} matches; using the first one.`, "ok");
    }
    els.metaPatient.textContent = `${selectedPatient.name} · ${selectedPatient.st_id}`;
    log(
      `Patient found: ${selectedPatient.name} (st_id=${selectedPatient.st_id}` +
        (selectedPatient.phone ? `, phone=${selectedPatient.phone}` : "") +
        ")",
      "ok"
    );
    setPill("Ready", "ok");
    syncSubmitEnabled();
  } finally {
    els.findPatient.disabled = false;
  }
}

function showResult(payload) {
  els.result.classList.remove("hidden");
  const editNote = payload.date_updated_on_edit
    ? "Date changed after create from the patient invoices page."
    : "Date was not changed on the edit page.";
  const ids = [
    payload.patient_name ? payload.patient_name : null,
    payload.national_id ? `NID ${payload.national_id}` : null,
    payload.st_id ? `st_id ${payload.st_id}` : null,
    payload.rec_id ? `rec_id ${payload.rec_id}` : null,
    payload.serial ? `serial ${payload.serial}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  els.result.innerHTML = `
    <h3>Invoice created</h3>
    <p>Amount: ${payload.amount} · Date: ${payload.date}</p>
    <p>${ids || ""}</p>
    <p>${editNote}</p>
    <p><a href="${payload.list_url || payload.invoice_url}" target="_blank" rel="noopener">Open patient invoices</a></p>
  `;
}

els.findPatient.addEventListener("click", async () => {
  try {
    await findPatient();
  } catch (err) {
    setPill("Error", "err");
    log(err.message || String(err), "err");
  }
});

els.nationalId.addEventListener("keydown", async (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    try {
      await findPatient();
    } catch (err) {
      setPill("Error", "err");
      log(err.message || String(err), "err");
    }
  }
});

els.clinic.addEventListener("change", async () => {
  try {
    await loadServices(els.clinic.value);
  } catch (err) {
    setPill("Error", "err");
    log(err.message || String(err), "err");
  }
});

[els.amount, els.date, els.service, els.nationalId].forEach((el) => {
  el.addEventListener("input", syncSubmitEnabled);
  el.addEventListener("change", syncSubmitEnabled);
});

els.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedPatient) {
    try {
      await findPatient();
    } catch (err) {
      setPill("Error", "err");
      log(err.message || String(err), "err");
      return;
    }
  }

  els.result.classList.add("hidden");
  els.submit.disabled = true;
  els.submit.classList.add("busy");
  els.submit.textContent = "Creating…";
  setPill("Running", "loading");
  log(`Using patient ${selectedPatient.name} (${selectedPatient.st_id})…`);
  log("Selecting clinic and service…");
  log("Clicking إضافة : Add, then finalizing the invoice…");
  log("After create: reopen patient → search G+invoice → change date…");

  try {
    const payload = {
      national_id: els.nationalId.value.trim(),
      clinic: els.clinic.value,
      service: els.service.value,
      amount: String(els.amount.value),
      date: els.date.value,
      headed: els.headed.checked,
    };
    const result = await api("/api/invoices", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setPill("Done", "ok");
    log("Invoice created, then date updated from the patient invoices page.", "ok");
    showResult(result);
  } catch (err) {
    setPill("Error", "err");
    log(err.message || String(err), "err");
  } finally {
    els.submit.disabled = false;
    els.submit.classList.remove("busy");
    els.submit.textContent = "Create invoice";
    syncSubmitEnabled();
  }
});

(async function boot() {
  const today = new Date();
  els.date.value = today.toISOString().slice(0, 10);
  try {
    await loadMeta();
    await loadClinics();
  } catch (err) {
    setPill("Error", "err");
    clearLog();
    log(err.message || String(err), "err");
  }
})();