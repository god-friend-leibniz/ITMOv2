const assignmentForm = document.querySelector("#assignment-form");
const assignmentButtons = assignmentForm.querySelectorAll("button");
const assignmentError = document.querySelector("#assignment-error");
let assignmentPending = false;

assignmentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (assignmentPending) return;
  assignmentPending = true;
  assignmentButtons.forEach((button) => { button.disabled = true; });
  assignmentError.hidden = true;
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
    window.location.reload();
  } catch {
    assignmentError.textContent = "Could not save the assignment. Please try again.";
    assignmentError.hidden = false;
  } finally {
    assignmentPending = false;
    assignmentButtons.forEach((button) => { button.disabled = false; });
  }
});

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
