const repositoryPanel = document.querySelector("#repository-panel");
if (repositoryPanel) {
  const loadRepository = document.querySelector("#load-repository");
  const repositoryStatus = document.querySelector("#repository-status");
  const repositorySummary = document.querySelector("#repository-summary");
  const repositoryError = document.querySelector("#repository-error");
  const ownerField = document.querySelector("#github-owner");
  const repoField = document.querySelector("#github-repo");
  let referenceVersion = 0;
  let loadingRepository = false;
  const referenceChanged = () => ownerField.value.trim().toLowerCase() !== repositoryPanel.dataset.owner
    || repoField.value.trim().toLowerCase() !== repositoryPanel.dataset.repo;

  for (const field of [ownerField, repoField]) {
    field.addEventListener("input", () => {
      referenceVersion += 1;
      repositorySummary.hidden = true;
      repositorySummary.replaceChildren();
      repositoryError.hidden = true;
      repositoryStatus.textContent = referenceChanged()
        ? "Save reference changes before loading a summary." : "Repository summary has not been loaded.";
      loadRepository.textContent = "Load repository summary";
      loadRepository.disabled = loadingRepository || referenceChanged();
    });
  }

  loadRepository.addEventListener("click", async () => {
    if (loadingRepository || referenceChanged()) return;
    loadingRepository = true;
    const version = referenceVersion;
    loadRepository.disabled = true;
    repositoryStatus.textContent = "Loading repository summary…";
    repositoryError.hidden = true;
    repositorySummary.hidden = true;
    repositorySummary.replaceChildren();
    loadRepository.textContent = "Load repository summary";
    try {
      const response = await fetch(repositoryPanel.dataset.url, { cache: "no-store" });
      const payload = await response.json();
      if (version !== referenceVersion) return;
      if (!response.ok) {
        const { error } = payload;
        const correction = ["REPOSITORY_NOT_FOUND", "REPOSITORY_MOVED", "INVALID_INPUT"].includes(error.code)
          ? " Check the saved reference and try again." : "";
        const retryAfter = response.headers.get("Retry-After");
        const retry = error.code === "RATE_LIMITED" && /^\d+$/.test(retryAfter ?? "")
          ? ` Retry after ${retryAfter} seconds.` : "";
        repositoryError.textContent = error.message + correction + retry;
        repositoryError.hidden = false;
        repositoryStatus.textContent = "Repository summary could not be loaded.";
        return;
      }
      const summary = payload;
      repositorySummary.replaceChildren();
      const heading = document.createElement("h3");
      heading.textContent = `${summary.owner}/${summary.name}`;
      repositorySummary.append(heading);
      for (const text of [
        summary.description ?? "No description.",
        `Default branch: ${summary.default_branch ?? "Unavailable"}`,
        `Primary languages: ${summary.primary_languages.join(", ") || "None"}`,
        `Last push: ${summary.last_push_at ?? "Unavailable"}`,
        `Fetched: ${summary.fetched_at}`,
      ]) {
        const paragraph = document.createElement("p");
        paragraph.textContent = text;
        repositorySummary.append(paragraph);
      }
      repositorySummary.hidden = false;
      repositoryStatus.textContent = "Repository summary loaded.";
      loadRepository.textContent = "Refresh repository summary";
    } catch {
      if (version !== referenceVersion) return;
      repositoryError.textContent = "Could not load repository information. Please try again.";
      repositoryError.hidden = false;
      repositoryStatus.textContent = "Repository summary could not be loaded.";
    } finally {
      loadingRepository = false;
      loadRepository.disabled = referenceChanged();
    }
  });
}
