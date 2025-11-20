// ----------------------------
// Scroll-Animation für SVG-Spinner
// ----------------------------

// Warten, bis DOM geladen ist
document.addEventListener("DOMContentLoaded", () => {
  const spinner = document.getElementById("scroll-spinner");
  if (!spinner) return;

  let lastScrollY = 0;
  let rotation = 0;

  function updateRotation() {
    const currentScroll = window.scrollY;
    const delta = currentScroll - lastScrollY;

    // Dreht proportional zur Scrollbewegung
    rotation += delta * 0.5; // Stärke anpassen (0.3–1.0 wirkt gut)
    spinner.style.transform = `rotate(${rotation}deg)`;

    lastScrollY = currentScroll;
    requestAnimationFrame(updateRotation);
  }

  // Starte kontinuierliche Aktualisierung
  requestAnimationFrame(updateRotation);
});
