(() => {
  const $ = (id) => document.getElementById(id);
  const slideshow = $("slideshowView");
  const meter = $("meterView");
  const special = $("specialView");
  const audio = $("backgroundMusic");
  let photos = [];
  let photoIndex = -1;
  let lastId = null;
  let previousGirl = null;
  let previousBoy = null;
  let previousTotal = null;
  let meterUntil = 0;
  let currentMode = "auto";
  let toastTimeout;

  function showView(view) {
    slideshow.classList.toggle("hidden", view !== "slideshow");
    meter.classList.toggle("hidden", view !== "meter");
    special.classList.toggle("hidden", view !== "special");
  }

  function nextPhoto() {
    if (!photos.length) return;
    photoIndex = (photoIndex + 1) % photos.length;
    const image = $("slideshowImage");
    image.classList.remove("photo-in");
    image.onload = () => requestAnimationFrame(() => image.classList.add("photo-in"));
    image.onerror = () => {
      image.classList.add("hidden");
      $("photoPlaceholder").classList.remove("hidden");
    };
    image.src = photos[photoIndex];
    image.classList.remove("hidden");
    $("photoPlaceholder").classList.add("hidden");
  }

  function pulse(element) {
    element.classList.remove("bump");
    void element.offsetWidth;
    element.classList.add("bump");
  }

  function pulseFill(element) {
    element.classList.remove("vote-pulse");
    void element.offsetWidth;
    element.classList.add("vote-pulse");
  }

  function render(data) {
    $("girlCount").textContent = data.girl;
    $("boyCount").textContent = data.boy;
    $("totalVotes").textContent = data.total;
    $("girlPercent").textContent = `${data.girl_percent}%`;
    $("boyPercent").textContent = `${data.boy_percent}%`;
    $("girlFill").style.height = `${data.total ? Math.max(4, data.girl_percent) : 0}%`;
    $("boyFill").style.height = `${data.total ? Math.max(4, data.boy_percent) : 0}%`;
    $("specialMessage").textContent = data.special_message || "A little more love is on the way";
  }

  function selectView() {
    if (currentMode === "auto") {
      showView(Date.now() < meterUntil ? "meter" : "slideshow");
    } else {
      showView(currentMode);
    }
  }

  async function refresh() {
    try {
      const response = await fetch("/api/results", { cache: "no-store" });
      if (!response.ok) throw new Error("Results request failed");
      const data = await response.json();
      $("connectionStatus").textContent = "● LIVE";
      const girlDelta = previousGirl === null ? 0 : data.girl - previousGirl;
      const boyDelta = previousBoy === null ? 0 : data.boy - previousBoy;
      if (lastId !== null && (girlDelta > 0 || boyDelta > 0)) {
        meterUntil = Date.now() + 10000;
        const newVotes = Math.max(1, data.total - previousTotal);
        $("displayToast").textContent = `${newVotes} new prediction${newVotes === 1 ? "" : "s"} just arrived!`;
        $("displayToast").classList.add("show");
        window.clearTimeout(toastTimeout);
        toastTimeout = window.setTimeout(() => $("displayToast").classList.remove("show"), 2400);
        pulse($("totalVotes"));
        if (girlDelta > 0) pulseFill($("girlFill"));
        if (boyDelta > 0) pulseFill($("boyFill"));
      }
      lastId = data.last_id;
      previousGirl = data.girl;
      previousBoy = data.boy;
      previousTotal = data.total;
      currentMode = data.display_mode || "auto";
      render(data);
      selectView();
    } catch (error) {
      $("connectionStatus").textContent = "● RECONNECTING";
      if (currentMode === "auto" && Date.now() >= meterUntil) {
        showView("slideshow");
      }
    } finally {
      window.setTimeout(refresh, 1800);
    }
  }

  async function loadPhotos() {
    try {
      const response = await fetch("/api/photos", { cache: "no-store" });
      if (!response.ok) throw new Error("Could not load local photo list.");
      const data = await response.json();
      photos = data.photos;
      if (photos.length) nextPhoto();
    } catch (error) {
      $("photoPlaceholder").querySelector("p").textContent =
        "The photo list could not be loaded. The live prediction display will continue to work.";
    }
  }

  $("startDisplayButton").addEventListener("click", async () => {
    audio.src = "/static/music/instrumental.mp3";
    try {
      await audio.play();
      $("audioStatus").textContent = "Display started. Music is playing.";
      $("startDisplayButton").textContent = "Music enabled";
    } catch (error) {
      $("audioStatus").textContent =
        "The slideshow is running, but music is unavailable. Add an approved instrumental.mp3 file to static/music.";
      $("startDisplayButton").textContent = "Display started · music unavailable";
    }
  });

  loadPhotos();
  window.setInterval(nextPhoto, 6000);
  refresh();
})();
