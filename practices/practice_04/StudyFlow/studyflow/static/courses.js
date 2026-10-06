const form = document.querySelector("#course-form");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = form.querySelector('button[type="submit"]');
  if (submit.disabled) return;
  submit.disabled = true;
  const errorMessage = document.querySelector("#form-error");
  errorMessage.hidden = true;
  try {
    const response = await fetch("/api/courses", {
      method: "POST",
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
  }
});
