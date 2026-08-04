"use strict";

const state = {
  config: null,
  idToken: null,
  reviewerEmail: null,
};

const $ = (id) => document.getElementById(id);

function toast(message, isBad) {
  const node = $("toast");
  node.textContent = message;
  node.classList.toggle("is-bad", Boolean(isBad));
  node.classList.remove("is-hidden");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.add("is-hidden"), 4200);
}

async function api(path, parameters) {
  const url = new URL(path, window.location.origin);
  Object.entries(parameters || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, value);
    }
  });
  const response = await fetch(url, { headers: { accept: "application/json" } });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.message || `request failed (${response.status})`);
  }
  return body;
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function renderEmpty(container, message, isError) {
  container.replaceChildren(
    element("div", isError ? "empty error" : "empty", message),
  );
}

function keyValues(pairs) {
  const list = element("dl", "kv");
  pairs
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .forEach(([key, value]) => {
      list.append(element("dt", null, key), element("dd", null, String(value)));
    });
  return list;
}

function metadataPairs(metadata) {
  return Object.entries(metadata || {})
    .filter(([key]) => !key.startsWith("x-amz-agentcore-memory-"))
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, value]) => [`metadata.${key}`, value]);
}

function recordCard(record, options) {
  const card = element("div", "card");
  const head = element("div", "card-head");
  head.append(element("span", "record-id", record.memory_record_id || "(no id)"));
  if (options && options.showScore) {
    const score =
      typeof record.score === "number" ? record.score.toFixed(4) : "n/a";
    head.append(element("span", "tag score", `score ${score}`));
  }
  card.append(head);
  card.append(element("p", "card-text", record.text || "(empty content)"));
  card.append(
    keyValues([
      ["namespace", (record.namespaces || []).join(", ")],
      ["strategy ID", record.memory_strategy_id || "(direct record)"],
      ["created at", record.created_at],
      ...metadataPairs(record.metadata),
    ]),
  );
  return card;
}

function renderRecords(container, counter, records, options) {
  if (counter) counter.textContent = String(records.length);
  if (!records.length) {
    renderEmpty(container, "No records found.");
    return;
  }
  container.replaceChildren(
    ...records.map((record) => recordCard(record, options)),
  );
}

/* ---------- Personal Memory ---------- */

async function loadActors() {
  const select = $("actor-select");
  try {
    const { actors } = await api("/api/personal/actors");
    if (!actors.length) {
      select.replaceChildren(element("option", null, "(no actors)"));
      return;
    }
    select.replaceChildren(
      ...actors.map((actor) => {
        const option = element("option", null, actor.actorId);
        option.value = actor.actorId;
        return option;
      }),
    );
    await loadSessions();
  } catch (error) {
    toast(`Failed to list actors: ${error.message}`, true);
  }
}

async function loadSessions() {
  const actorId = $("actor-select").value;
  const select = $("session-select");
  if (!actorId) return;
  try {
    const { sessions } = await api("/api/personal/sessions", {
      actor_id: actorId,
    });
    if (!sessions.length) {
      select.replaceChildren(element("option", null, "(no sessions)"));
      return;
    }
    select.replaceChildren(
      ...sessions.map((session) => {
        const option = element("option", null, session.sessionId);
        option.value = session.sessionId;
        return option;
      }),
    );
  } catch (error) {
    toast(`Failed to list sessions: ${error.message}`, true);
  }
}

function turnCard(event) {
  const card = element("div", "card");
  const head = element("div", "card-head");
  head.append(element("span", "record-id", event.event_id));
  head.append(element("span", "tag", String(event.event_timestamp)));
  card.append(head);
  event.turns.forEach((turn) => {
    const row = element("div", "card-head");
    row.append(
      element("span", `tag role-${String(turn.role).toLowerCase()}`, turn.role),
    );
    card.append(row);
    card.append(element("p", "card-text", turn.text));
  });
  return card;
}

async function loadPersonal() {
  const actorId = $("actor-select").value;
  const sessionId = $("session-select").value;
  if (!actorId || !sessionId) {
    toast("Select an actor and session first.", true);
    return;
  }
  $("personal-scope-note").textContent =
    `Personal memory ${state.config.personal_memory_id} · actor ${actorId} · session ${sessionId}`;

  const eventsBox = $("stm-list");
  const prefBox = $("pref-list");
  const summaryBox = $("summary-list");
  renderEmpty(eventsBox, "Loading…");
  renderEmpty(prefBox, "Loading…");
  renderEmpty(summaryBox, "Loading…");

  const [events, preferences, summary] = await Promise.allSettled([
    api("/api/personal/events", { actor_id: actorId, session_id: sessionId }),
    api("/api/personal/preferences", { actor_id: actorId }),
    api("/api/personal/summary", { actor_id: actorId, session_id: sessionId }),
  ]);

  if (events.status === "fulfilled") {
    const list = events.value.events;
    $("stm-count").textContent = String(list.length);
    if (list.length) {
      eventsBox.replaceChildren(...list.map(turnCard));
    } else {
      renderEmpty(eventsBox, "No short-term events in this session.");
    }
  } else {
    renderEmpty(eventsBox, events.reason.message, true);
  }

  if (preferences.status === "fulfilled") {
    $("pref-namespace").textContent = preferences.value.namespace;
    renderRecords($("pref-list"), $("pref-count"), preferences.value.records);
  } else {
    renderEmpty(prefBox, preferences.reason.message, true);
  }

  if (summary.status === "fulfilled") {
    $("summary-namespace").textContent = summary.value.namespace;
    renderRecords($("summary-list"), $("summary-count"), summary.value.records);
  } else {
    renderEmpty(summaryBox, summary.reason.message, true);
  }
}

/* ---------- Shared Memory ---------- */

async function loadInventory() {
  const container = $("inventory-list");
  renderEmpty(container, "Loading…");
  try {
    const result = await api("/api/shared/inventory");
    renderRecords(container, $("inventory-count"), result.records);
  } catch (error) {
    renderEmpty(container, error.message, true);
  }
}

async function runSearch() {
  const container = $("search-list");
  renderEmpty(container, "Searching…");
  try {
    const result = await api("/api/shared/search", {
      q: $("search-query").value,
      top_k: $("search-topk").value,
    });
    renderRecords(container, $("search-count"), result.records, {
      showScore: true,
    });
  } catch (error) {
    renderEmpty(container, error.message, true);
  }
}

/* ---------- Review Queue ---------- */

async function cognito(action, body) {
  const response = await fetch(
    `https://cognito-idp.${state.config.region}.amazonaws.com/`,
    {
      method: "POST",
      headers: {
        "content-type": "application/x-amz-json-1.1",
        "x-amz-target": `AWSCognitoIdentityProviderService.${action}`,
      },
      body: JSON.stringify(body),
    },
  );
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.message || `Cognito ${action} failed`);
  }
  return payload;
}

async function signIn() {
  const email = $("reviewer-email").value.trim();
  const password = $("reviewer-password").value;
  if (!email || !password) {
    toast("Email and password are required.", true);
    return;
  }
  try {
    const result = await cognito("InitiateAuth", {
      ClientId: state.config.reviewer_client_id,
      AuthFlow: "USER_PASSWORD_AUTH",
      AuthParameters: { USERNAME: email, PASSWORD: password },
    });
    if (!result.AuthenticationResult) {
      throw new Error(
        `sign-in requires an additional challenge: ${result.ChallengeName}`,
      );
    }
    state.idToken = result.AuthenticationResult.IdToken;
    state.reviewerEmail = email;
    $("reviewer-password").value = "";
    updateReviewerStatus();
    toast("Signed in as reviewer.");
    await loadCandidates();
  } catch (error) {
    toast(`Sign-in failed: ${error.message}`, true);
  }
}

function signOut() {
  state.idToken = null;
  state.reviewerEmail = null;
  updateReviewerStatus();
  renderEmpty($("review-list"), "Sign in to load the review queue.");
  $("review-count").textContent = "0";
}

function tokenGroups() {
  if (!state.idToken) return [];
  try {
    const payload = JSON.parse(
      atob(state.idToken.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")),
    );
    return payload["cognito:groups"] || [];
  } catch (error) {
    return [];
  }
}

function updateReviewerStatus() {
  const node = $("reviewer-status");
  $("reviewer-signout").disabled = !state.idToken;
  if (!state.idToken) {
    node.textContent = "Not signed in.";
    return;
  }
  const groups = tokenGroups();
  const inGroup = groups.includes(state.config.reviewer_group_name);
  node.textContent =
    `Signed in as ${state.reviewerEmail} · groups: ${groups.join(", ") || "(none)"} · ` +
    (inGroup
      ? `member of ${state.config.reviewer_group_name}`
      : `NOT in ${state.config.reviewer_group_name} — API will return 403`);
}

async function reviewApi(path, options) {
  if (!state.idToken) throw new Error("reviewer sign-in is required");
  const response = await fetch(`${state.config.review_api_url}${path}`, {
    method: (options && options.method) || "GET",
    headers: {
      authorization: state.idToken,
      "content-type": "application/json",
    },
    body: options && options.body ? JSON.stringify(options.body) : undefined,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.message || `Review API returned ${response.status}`);
  }
  return payload;
}

function candidateCard(candidate) {
  const card = element("div", "card");
  const head = element("div", "card-head");
  head.append(element("span", "record-id", candidate.candidate_id));
  head.append(
    element("span", `tag status-${candidate.status}`, candidate.status),
  );
  card.append(head);
  card.append(element("p", "card-text", candidate.statement || "(no statement)"));

  const confidence = candidate.confidence_basis_points;
  card.append(
    keyValues([
      ["project ID", candidate.project_id],
      ["category", candidate.category],
      ["proposer", candidate.proposer_actor_id],
      ["evidence ref", candidate.evidence_ref],
      ["privacy", candidate.privacy_classification],
      [
        "confidence",
        confidence !== undefined ? `${Number(confidence) / 100}%` : "",
      ],
      ["promotion hint", candidate.promotion_hint],
      ["shared record ID", candidate.shared_memory_record_id],
      ["reviewer ID", candidate.reviewer_id],
      ["review reason", candidate.status_reason],
      ["created at", candidate.created_at],
      ["updated at", candidate.updated_at],
      ["workflow execution", candidate.workflow_execution_id],
    ]),
  );

  if (candidate.status === "PENDING_REVIEW") {
    const actions = element("div", "card-actions");
    const approve = element("button", "approve", "Approve");
    const reject = element("button", "reject", "Reject");
    approve.onclick = () => decide(candidate.candidate_id, "APPROVED", actions);
    reject.onclick = () => decide(candidate.candidate_id, "REJECTED", actions);
    actions.append(approve, reject);
    card.append(actions);
  }
  return card;
}

async function decide(candidateId, decision, actions) {
  // The API requires a rationale, so ask for it here rather than letting the request
  // fail: the reason is what the audit record needs in order to explain the decision.
  const reason = (
    window.prompt(
      `Reason for ${decision.toLowerCase()} (10-500 characters, stored on the audit record):`,
      "",
    ) || ""
  ).trim();
  if (reason.length < 10) {
    toast("A reason of at least 10 characters is required.", true);
    return;
  }
  actions
    .querySelectorAll("button")
    .forEach((button) => (button.disabled = true));
  try {
    await reviewApi(`/reviews/${encodeURIComponent(candidateId)}`, {
      method: "POST",
      body: { decision, status_reason: reason },
    });
    toast(`${candidateId} ${decision.toLowerCase()} — workflow resumed.`);
    setTimeout(loadCandidates, 3500);
  } catch (error) {
    toast(`Decision failed: ${error.message}`, true);
    actions
      .querySelectorAll("button")
      .forEach((button) => (button.disabled = false));
  }
}

async function loadCandidates() {
  const container = $("review-list");
  if (!state.idToken) {
    renderEmpty(container, "Sign in to load the review queue.");
    return;
  }
  renderEmpty(container, "Loading…");
  const status = $("review-status-filter").value;
  try {
    const query = status ? `?status=${encodeURIComponent(status)}` : "";
    const result = await reviewApi(`/reviews${query}`);
    const candidates = result.candidates || [];
    $("review-count").textContent = String(candidates.length);
    if (!candidates.length) {
      renderEmpty(container, "No candidates matched.");
      return;
    }
    container.replaceChildren(...candidates.map(candidateCard));
  } catch (error) {
    renderEmpty(container, error.message, true);
  }
}

/* ---------- Bootstrap ---------- */

function switchView(view) {
  document
    .querySelectorAll(".tab")
    .forEach((tab) => tab.classList.toggle("is-active", tab.dataset.view === view));
  ["personal", "shared", "review"].forEach((name) => {
    $(`view-${name}`).classList.toggle("is-hidden", name !== view);
  });
}

async function main() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.onclick = () => switchView(tab.dataset.view);
  });
  $("personal-refresh").onclick = loadPersonal;
  $("actor-select").onchange = loadSessions;
  $("inventory-refresh").onclick = loadInventory;
  $("search-run").onclick = runSearch;
  $("reviewer-signin").onclick = signIn;
  $("reviewer-signout").onclick = signOut;
  $("review-refresh").onclick = loadCandidates;
  $("reviewer-password").onkeydown = (event) => {
    if (event.key === "Enter") signIn();
  };

  renderEmpty($("stm-list"), "Select an actor and session, then press Load.");
  renderEmpty($("pref-list"), "No records loaded.");
  renderEmpty($("summary-list"), "No records loaded.");
  renderEmpty($("inventory-list"), "Press “Browse namespace”.");
  renderEmpty($("search-list"), "Run a semantic search.");
  renderEmpty($("review-list"), "Sign in to load the review queue.");

  try {
    state.config = await api("/api/config");
  } catch (error) {
    $("deployment-line").textContent = `config unavailable: ${error.message}`;
    return;
  }
  $("deployment-line").textContent =
    `project ${state.config.project_id} · ${state.config.region} · personal ${state.config.personal_memory_id} · shared ${state.config.shared_memory_id}`;
  $("shared-namespace").textContent = state.config.shared_namespace;
  updateReviewerStatus();
  await loadActors();
}

main();
