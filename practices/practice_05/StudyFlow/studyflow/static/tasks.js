const taskForm = document.querySelector("#task-form");
let taskPending = false;

function setTaskPending(pending) {
  taskPending = pending;
  document.querySelectorAll("#task-form button, #checklist button, #checklist input[type=checkbox]")
    .forEach((control) => { control.disabled = pending; });
}

function showTaskError(alert, error) {
  alert.textContent = Object.values(error.fields || {}).join(" ") || error.message;
  alert.hidden = false;
}

taskForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (taskPending) return;
  setTaskPending(true);
  const alert = document.querySelector("#task-error");
  alert.hidden = true;
  try {
    const response = await fetch(taskForm.dataset.url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: taskForm.elements.title.value }),
    });
    if (response.ok) window.location.reload();
    else showTaskError(alert, (await response.json()).error);
  } catch {
    showTaskError(alert, { message: "Could not save the task. Please try again." });
  } finally {
    setTaskPending(false);
  }
});

document.querySelectorAll("#checklist input[type=checkbox]").forEach((checkbox) => {
  checkbox.addEventListener("change", async () => {
    const completed = checkbox.checked;
    if (taskPending) {
      checkbox.checked = !completed;
      return;
    }
    setTaskPending(true);
    const alert = checkbox.closest("li").querySelector(".task-error");
    alert.hidden = true;
    try {
      const response = await fetch(checkbox.dataset.url, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_completed: completed }),
      });
      if (response.ok) window.location.reload();
      else {
        checkbox.checked = !completed;
        showTaskError(alert, (await response.json()).error);
      }
    } catch {
      checkbox.checked = !completed;
      showTaskError(alert, { message: "Could not save the task. Please try again." });
    } finally {
      setTaskPending(false);
    }
  });
});

document.querySelectorAll(".task-edit").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (taskPending) return;
    setTaskPending(true);
    const alert = form.querySelector(".task-error");
    alert.hidden = true;
    try {
      const response = await fetch(form.dataset.url, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: form.elements.title.value }),
      });
      if (response.ok) window.location.reload();
      else showTaskError(alert, (await response.json()).error);
    } catch {
      showTaskError(alert, { message: "Could not save the task. Please try again." });
    } finally {
      setTaskPending(false);
    }
  });
});

document.querySelectorAll(".task-delete").forEach((button) => {
  button.addEventListener("click", async () => {
    if (taskPending) return;
    if (!window.confirm(`Delete “${button.dataset.title}”? This cannot be undone.`)) return;
    setTaskPending(true);
    const alert = button.form.querySelector(".task-error");
    alert.hidden = true;
    try {
      const response = await fetch(button.form.dataset.url, { method: "DELETE" });
      if (response.ok) window.location.reload();
      else showTaskError(alert, (await response.json()).error);
    } catch {
      showTaskError(alert, { message: "Could not delete the task. Please try again." });
    } finally {
      setTaskPending(false);
    }
  });
});
