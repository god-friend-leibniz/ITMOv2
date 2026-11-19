const form = document.querySelector("#course-form");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = form.querySelector('button[type="submit"]');
  if (submit.disabled) return;
  submit.disabled = true;
  if (deleteButton) deleteButton.disabled = true;
  const errorMessage = document.querySelector("#form-error");
  errorMessage.hidden = true;
  try {
    const response = await fetch(form.dataset.url || "/api/courses", {
      method: form.dataset.method || "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: form.elements.name.value, description: form.elements.description.value }),
    });
    if (response.ok) {
      window.location.reload();
      return;
    }
    const { error } = await response.json();
    errorMessage.textContent = Object.values(error.fields).join(" ") || error.message;
    errorMessage.hidden = false;
  } catch {
    errorMessage.textContent = "Could not save the course. Please try again.";
    errorMessage.hidden = false;
  } finally {
    submit.disabled = false;
    if (deleteButton) deleteButton.disabled = false;
  }
});

const deleteButton = document.querySelector("#delete-course");
if (deleteButton) {
  deleteButton.addEventListener("click", async () => {
    if (deleteButton.disabled) return;
    const name = document.querySelector("#course-heading").textContent;
    if (!window.confirm(`Delete “${name}” and all its assignments and tasks? This cannot be undone.`)) return;
    const submit = form.querySelector('button[type="submit"]');
    deleteButton.disabled = true;
    submit.disabled = true;
    const errorMessage = document.querySelector("#form-error");
    errorMessage.hidden = true;
    try {
      const response = await fetch(form.dataset.url, { method: "DELETE" });
      if (response.ok) {
        window.location.assign("/");
        return;
      }
      const { error } = await response.json();
      errorMessage.textContent = error.message;
      errorMessage.hidden = false;
    } catch {
      errorMessage.textContent = "Could not delete the course. Please try again.";
      errorMessage.hidden = false;
    } finally {
      deleteButton.disabled = false;
      submit.disabled = false;
    }
  });
}
