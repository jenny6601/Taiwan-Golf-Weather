
(() => {
  if (!("serviceWorker" in navigator)) {
    return;
  }

  window.addEventListener("load", async () => {
    try {
      const registration =
        await navigator.serviceWorker.register(
          "../sw.js",
          { scope: "../" }
        );

      console.log(
        "Golf Weather PWA registered:",
        registration.scope
      );

    } catch (error) {
      console.error(
        "PWA registration failed:",
        error
      );
    }
  });
})();
