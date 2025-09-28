const TOAST_DURATION_MS = 4000;

let container: HTMLDivElement | null = null;

export function initNotifications(): void {
  if (!container) {
    container = document.createElement("div");
    container.className = "toast-container";
    document.body.appendChild(container);
  }
}

export function notifyError(message: string): void {
  if (!container) {
    initNotifications();
  }
  if (!container) {
    return;
  }

  const toast = document.createElement("div");
  toast.className = "toast toast--error";
  toast.textContent = message;
  container.appendChild(toast);

  requestAnimationFrame(() => {
    toast.classList.add("is-visible");
  });

  setTimeout(() => {
    toast.classList.remove("is-visible");
    setTimeout(() => toast.remove(), 250);
  }, TOAST_DURATION_MS);
}
