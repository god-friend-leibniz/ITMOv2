const assignmentForm = document.querySelector("#assignment-form");
const assignmentButtons = assignmentForm.querySelectorAll("button");
const assignmentError = document.querySelector("#assignment-error");
const assignmentSuccess = document.querySelector("#assignment-success");
let assignmentList = document.querySelector("#course-assignment-list");
const refreshStatus = document.querySelector("#assignment-refresh-status");
const staleNote = document.querySelector("#assignment-list-stale-note");
const refreshError = document.querySelector("#assignment-refresh-error");
const refreshRetry = document.querySelector("#assignment-refresh-retry");
let lastCreated = null;
let assignmentPending = false;

async function refreshAssignmentList() {
  const { courseId, completion } = assignmentList.dataset;
  const url = `/courses/${courseId}${completion === "all" ? "" : `?completion=${completion}`}`;
  assignmentList.setAttribute("aria-busy", "true");
  assignmentList.setAttribute("aria-describedby", "assignment-list-stale-note");
  assignmentList.classList.add("assignment-list-stale");
  staleNote.hidden = false;
  refreshStatus.hidden = false;
  try {
    const response = await fetch(url, { headers: { Accept: "text/html" }, cache: "no-store" });
    const mediaType = (response.headers.get("Content-Type") || "").split(";")[0].trim().toLowerCase();
    if (response.status !== 200 || mediaType !== "text/html") throw new Error("Unexpected assignment list response");
    const page = new DOMParser().parseFromString(await response.text(), "text/html");
    const results = page.querySelectorAll("#course-assignment-list");
    if (results.length !== 1) throw new Error("Expected one assignment list");
    const result = results[0];
    if (result.querySelector("form, script")) throw new Error("Unexpected form or script in assignment list");
    if (result.dataset.courseId !== courseId || result.dataset.completion !== completion) {
      throw new Error("Assignment list belongs to another course or mode");
    }
    if (!["true", "false"].includes(result.dataset.hasAssignments)) throw new Error("Invalid assignment presence marker");
    const cards = [...result.querySelectorAll("article.course")];
    const ids = cards.map((card) => card.dataset.assignmentId);
    if (ids.length !== result.querySelectorAll("[data-assignment-id]").length
        || ids.some((id) => !/^[1-9]\d*$/.test(id || "")) || new Set(ids).size !== ids.length) {
      throw new Error("Invalid assignment card IDs");
    }
    const emptyCount = result.querySelectorAll("#assignments-empty").length;
    if ((cards.length === 0 ? emptyCount !== 1 : emptyCount !== 0)
        || (cards.length > 0 && result.dataset.hasAssignments !== "true")) {
      throw new Error("Inconsistent empty assignment list");
    }
    const nextList = document.importNode(result, true);
    assignmentList.replaceWith(nextList);
    assignmentList = nextList;
    assignmentForm.dataset.completion = assignmentList.dataset.completion;
    staleNote.hidden = true;
    refreshError.hidden = true;
    refreshRetry.hidden = true;
    const visible = [...assignmentList.querySelectorAll("[data-assignment-id]")]
      .some((card) => card.dataset.assignmentId === String(lastCreated.id));
    assignmentSuccess.querySelector("span").textContent = `Assignment “${lastCreated.title}” created.${visible ? "" : " It is hidden by the current filter. Select"}`;
    document.querySelector("#assignment-hidden-confirmation").hidden = visible;
    assignmentSuccess.hidden = false;
  } catch {
    assignmentList.setAttribute("aria-busy", "false");
    refreshError.hidden = false;
    refreshRetry.hidden = false;
  } finally {
    refreshStatus.hidden = true;
  }
}

assignmentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (assignmentPending) return;
  assignmentPending = true;
  assignmentButtons.forEach((button) => { button.disabled = true; });
  assignmentError.hidden = true;
  if (assignmentSuccess) assignmentSuccess.hidden = true;
  try {
    const owner = assignmentForm.elements.github_owner.value.trim();
    const repo = assignmentForm.elements.github_repo.value.trim();
    const response = await fetch(assignmentForm.dataset.url, {
      method: assignmentForm.dataset.method || "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: assignmentForm.elements.title.value,
        description: assignmentForm.elements.description.value,
        due_date: assignmentForm.elements.due_date.value || null,
        repository: owner || repo ? { owner, repo } : null,
      }),
    });
    if (!response.ok) {
      const { error } = await response.json();
      assignmentError.textContent = Object.values(error.fields || {}).join(" ") || error.message;
      assignmentError.hidden = false;
      return;
    }
    if (assignmentList) {
      lastCreated = await response.json();
      assignmentForm.reset();
      await refreshAssignmentList();
      return;
    }
    window.location.reload();
  } catch {
    assignmentError.textContent = "Could not save the assignment. Please try again.";
    assignmentError.hidden = false;
  } finally {
    assignmentPending = false;
    assignmentButtons.forEach((button) => { button.disabled = false; });
  }
});

if (refreshRetry) {
  refreshRetry.addEventListener("click", async () => {
    if (assignmentPending || !lastCreated) return;
    const hadFocus = document.activeElement === refreshRetry;
    assignmentPending = true;
    assignmentButtons.forEach((button) => { button.disabled = true; });
    try {
      await refreshAssignmentList();
    } finally {
      assignmentPending = false;
      assignmentButtons.forEach((button) => { button.disabled = false; });
      if (hadFocus && (document.activeElement === document.body || document.activeElement === refreshRetry)) {
        const target = refreshRetry.hidden ? assignmentForm.querySelector('button[type="submit"]') : refreshRetry;
        target.focus();
      }
    }
  });
}

const deleteAssignmentButton = document.querySelector("#delete-assignment");
if (deleteAssignmentButton) {
  deleteAssignmentButton.addEventListener("click", async () => {
    if (assignmentPending) return;
    const title = document.querySelector("#assignment-heading").textContent;
    if (!window.confirm(`Delete “${title}” and all its tasks? This cannot be undone.`)) return;
    assignmentPending = true;
    assignmentButtons.forEach((button) => { button.disabled = true; });
    assignmentError.hidden = true;
    try {
      const response = await fetch(assignmentForm.dataset.url, { method: "DELETE" });
      if (!response.ok) {
        const { error } = await response.json();
        assignmentError.textContent = error.message;
        assignmentError.hidden = false;
        return;
      }
      window.location.assign(assignmentForm.dataset.courseUrl);
    } catch {
      assignmentError.textContent = "Could not delete the assignment. Please try again.";
      assignmentError.hidden = false;
    } finally {
      assignmentPending = false;
      assignmentButtons.forEach((button) => { button.disabled = false; });
    }
  });
}
