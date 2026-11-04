(() => {
  const $ = (id) => document.getElementById(id);
  const status = $("adminStatus");
  const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
  let slides = [];
  let currentSlideId = "";
  let isPaused = false;
  let musicAvailable = false;

  async function post(data) {
    const response = await fetch("/api/admin", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify(data),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Request failed.");
    return result;
  }

  function showPreview(slide) {
    const previewImage = $("previewImage");
    if (!slide) {
      previewImage.classList.add("hidden");
      $("previewCaption").textContent = "No slide selected";
      $("previewCategory").textContent = "";
      return;
    }
    previewImage.src = slide.image;
    previewImage.alt = slide.caption || slide.category || "Slideshow photo preview";
    previewImage.classList.remove("hidden");
    $("previewCaption").textContent = slide.caption || "No caption";
    $("previewCategory").textContent = slide.category || "";
  }

  function renderSlideList() {
    const list = $("slideList");
    list.replaceChildren();
    if (!slides.length) {
      const empty = document.createElement("li");
      empty.textContent = "No valid slides yet. Add local images and captions to the manifest.";
      list.append(empty);
      showPreview(null);
      return;
    }
    slides.forEach((slide) => {
      const item = document.createElement("li");
      item.textContent = [
        slide.category,
        slide.caption || slide.image.split("/").pop(),
        slide.author ? `— ${slide.author}` : "",
      ].filter(Boolean).join(" · ");
      list.append(item);
    });
    showPreview(slides.find((slide) => slide.id === currentSlideId) || null);
  }

  async function loadSlides() {
    const response = await fetch("/api/admin/slides", { cache: "no-store" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not load slideshow photos.");
    slides = Array.isArray(result.slides) ? result.slides : [];
    renderSlideList();
  }

  function render(data) {
    ["total", "girl", "boy", "qr", "booth"].forEach((key) => {
      $(key).textContent = data[key];
    });
    $("votingState").textContent = data.voting_open ? "Voting is OPEN" : "Voting is CLOSED";
    if (document.activeElement !== $("displayMode")) {
      $("displayMode").value = data.display_mode;
    }
    if (document.activeElement !== $("specialMessageInput")) {
      $("specialMessageInput").value = data.special_message || "";
    }
    if (document.activeElement !== $("slideDuration")) {
      $("slideDuration").value = data.slide_duration || 15;
    }
    currentSlideId = data.current_slide_id || "";
    isPaused = Boolean(data.slideshow_paused);
    $("pauseSlideshow").textContent = isPaused ? "Resume slideshow" : "Pause slideshow";
    musicAvailable = Boolean(data.music_url);
    $("musicEnabled").checked = Boolean(data.music_enabled);
    $("musicEnabled").disabled = !musicAvailable;
    $("musicAvailability").textContent = musicAvailable
      ? "A local music file is configured. Playback may still require a tap on the display."
      : "No licensed music file is configured; the display remains silent.";
    renderSlideList();
  }

  async function refresh() {
    try {
      const response = await fetch("/api/admin", { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not load event status.");
      render(data);
    } catch (error) {
      status.textContent = error.message;
    } finally {
      window.setTimeout(refresh, 5000);
    }
  }

  async function runAction(data, successMessage) {
    try {
      render(await post(data));
      status.textContent = successMessage;
      return true;
    } catch (error) {
      status.textContent = error.message;
      return false;
    }
  }

  $("openVoting").addEventListener("click", () => runAction(
    { action: "open" }, "Voting opened."
  ));
  $("closeVoting").addEventListener("click", () => runAction(
    { action: "close" }, "Voting closed."
  ));
  $("saveDisplay").addEventListener("click", () => runAction({
    action: "display",
    mode: $("displayMode").value,
    special_message: $("specialMessageInput").value,
  }, "Display settings saved."));
  $("saveSlideDuration").addEventListener("click", () => {
    const duration = Number($("slideDuration").value);
    runAction({ action: "slideshow", duration }, "Slide duration saved.");
  });
  $("pauseSlideshow").addEventListener("click", () => runAction({
    action: "slideshow",
    paused: !isPaused,
  }, isPaused ? "Slideshow resumed." : "Slideshow paused."));
  $("nextSlide").addEventListener("click", () => runAction(
    { action: "slideshow", command: "next" }, "Next slide requested."
  ));
  $("previousSlide").addEventListener("click", () => runAction(
    { action: "slideshow", command: "previous" }, "Previous slide requested."
  ));
  $("musicEnabled").addEventListener("change", () => runAction({
    action: "slideshow",
    music_enabled: $("musicEnabled").checked,
  }, $("musicEnabled").checked ? "Music enabled for the display." : "Music disabled."));
  $("previewSlide").addEventListener("click", () => {
    showPreview(slides.find((slide) => slide.id === currentSlideId) || null);
  });
  $("reloadManifest").addEventListener("click", async () => {
    const saved = await runAction(
      { action: "slideshow", command: "reload" },
      "Manifest reload requested. The display will update shortly."
    );
    if (saved) {
      try {
        await loadSlides();
      } catch (error) {
        status.textContent = error.message;
      }
    }
  });
  $("resetVotes").addEventListener("click", async () => {
    if (!window.confirm("This permanently deletes every vote. Only reset before the event starts. Continue?")) {
      return;
    }
    if (window.prompt('Type RESET to permanently delete all votes.') !== "RESET") {
      status.textContent = "Reset cancelled. No votes were deleted.";
      return;
    }
    await runAction({ action: "reset", confirm: true }, "Test votes cleared.");
  });
  $("logoutAdmin").addEventListener("click", async () => {
    try {
      await post({ action: "logout" });
      window.location.assign("/admin");
    } catch (error) {
      status.textContent = error.message;
    }
  });

  loadSlides().catch((error) => {
    $("slideList").textContent = error.message;
  });
  refresh();
})();
