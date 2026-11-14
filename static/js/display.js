(() => {
  const $ = (id) => document.getElementById(id);
  const slideshow = $("slideshowView");
  const meter = $("meterView");
  const special = $("specialView");
  const audio = $("backgroundMusic");
  const image = $("slideshowImage");
  const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
  const captionOverlays = {
    none: "none",
    "left-light": "linear-gradient(90deg, #fff8e9b8, #fff8e966 70%, transparent)",
    "right-light": "linear-gradient(270deg, #fff8e9b8, #fff8e966 70%, transparent)",
    "top-light": "linear-gradient(180deg, #fff8e9b8, #fff8e966 70%, transparent)",
    "bottom-light": "linear-gradient(0deg, #fff8e9b8, #fff8e966 70%, transparent)",
    "left-dark": "linear-gradient(90deg, #20140dcc, #20140d66 70%, transparent)",
    "right-dark": "linear-gradient(270deg, #20140dcc, #20140d66 70%, transparent)",
    "top-dark": "linear-gradient(180deg, #20140dcc, #20140d66 70%, transparent)",
    "bottom-dark": "linear-gradient(0deg, #20140dcc, #20140d66 70%, transparent)",
  };
  let slides = [];
  let queue = [];
  let history = [];
  let historyCursor = -1;
  let currentSlide = null;
  let previousVoteSequence = null;
  let previousGirl = null;
  let previousBoy = null;
  let meterUntil = 0;
  let currentMode = "auto";
  let slideDuration = 15;
  let slideshowPaused = false;
  let musicAllowed = false;
  let musicReady = false;
  let userPausedMusic = false;
  let lastCommandVersion = null;
  let lastControlVersion = null;
  let slideTimer = null;
  let toastTimeout = null;

  function showView(view) {
    slideshow.classList.toggle("hidden", view !== "slideshow");
    meter.classList.toggle("hidden", view !== "meter");
    special.classList.toggle("hidden", view !== "special");
  }

  function selectView() {
    if (currentMode === "auto") {
      showView(Date.now() < meterUntil ? "meter" : "slideshow");
    } else {
      showView(currentMode);
    }
  }

  function shuffleQueue() {
    queue = slides
      .filter((slide) => slides.length === 1 || !currentSlide || slide.id !== currentSlide.id)
      .map((slide) => slide.id);
    for (let index = queue.length - 1; index > 0; index -= 1) {
      const randomIndex = Math.floor(Math.random() * (index + 1));
      [queue[index], queue[randomIndex]] = [queue[randomIndex], queue[index]];
    }
  }

  function preloadNext() {
    if (!queue.length && slides.length) shuffleQueue();
    if (!queue.length) return;
    const next = slides.find((slide) => slide.id === queue[0]);
    if (next) {
      const nextImage = new Image();
      nextImage.src = next.image;
    }
  }

  async function reportCurrentSlide(slide) {
    try {
      await fetch("/api/display-state", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
        },
        body: JSON.stringify({ slide_id: slide.id }),
      });
    } catch (error) {
      $("audioStatus").textContent = "The display is running; slide preview may be out of date.";
    }
  }

  function showSlide(slide) {
    if (!slide) return;
    currentSlide = slide;
    image.classList.remove("photo-in");
    image.onload = () => requestAnimationFrame(() => {
      image.classList.add("photo-in");
      positionCaption(slide.text_layout);
    });
    image.onerror = () => {
      slides = slides.filter((item) => item.id !== slide.id);
      history = history.filter((id) => id !== slide.id);
      historyCursor = history.length - 1;
      $("photoPlaceholder").classList.remove("hidden");
      image.classList.add("hidden");
      $("photoCaption").classList.add("hidden");
      $("photoPlaceholder").querySelector("p").textContent =
        "A photo could not be loaded. Add valid local images to the manifest.";
      shuffleQueue();
      if (slides.length) advanceSlide();
    };
    image.alt = slide.caption || "Family photograph";
    image.style.objectPosition = slide.text_layout?.objectPosition || "center center";
    image.src = slide.image;
    image.classList.remove("hidden");
    $("photoPlaceholder").classList.add("hidden");
    $("captionText").textContent = slide.caption || "";
    const caption = $("photoCaption");
    const layout = slide.text_layout || {};
    caption.classList.toggle("hidden", !slide.caption);
    caption.dataset.position = layout.position || "center";
    caption.dataset.alignment = layout.alignment || "center";
    caption.dataset.shadow = layout.shadow || "dark";
    caption.dataset.overlay = layout.overlay || "none";
    caption.dataset.subjectArea = JSON.stringify(layout.subjectArea || {});
    applyResponsiveCaptionSettings(layout);
    caption.style.setProperty("--caption-font-min", `${layout.minFontPx || 20}px`);
    caption.style.setProperty("--caption-font-preferred", `${layout.preferredFontVw || 3.2}vw`);
    caption.style.setProperty("--caption-font-max", `${layout.maxFontPx || 54}px`);
    caption.style.setProperty("--caption-color", layout.color || "#fffaf0");
    caption.style.setProperty("--caption-align", layout.alignment || "center");
    caption.style.setProperty("--caption-line-height", layout.lineHeight || 1.15);
    caption.style.setProperty("--caption-padding", `${layout.paddingPx || 0}px`);
    caption.style.setProperty("--caption-weight", layout.fontWeight || 600);
    caption.style.setProperty(
      "--caption-font-family",
      layout.fontFamily === "sans" ? '"Segoe UI", Arial, sans-serif' : 'Georgia, "Times New Roman", serif'
    );
    caption.style.setProperty("--caption-overlay", captionOverlays[layout.overlay] || "none");
    positionCaption(layout);
    reportCurrentSlide(slide);
    preloadNext();
  }

  function applyResponsiveCaptionSettings(layout) {
    const caption = $("photoCaption");
    const isMobile = window.matchMedia("(max-width: 600px)").matches;
    const maxWidth = isMobile
      ? layout.mobileMaxWidthPct || layout.maxWidthPct || 48
      : layout.maxWidthPct || 48;
    const insetY = isMobile
      ? layout.mobileInsetYVh || layout.insetYVh || 5
      : layout.insetYVh || 5;
    caption.style.setProperty("--caption-max-width", `${maxWidth}%`);
    caption.style.setProperty("--caption-inset-x", `clamp(14px, ${layout.insetXVw || 5}vw, 72px)`);
    caption.style.setProperty("--caption-inset-y", `clamp(14px, ${insetY}vh, 72px)`);
  }

  function getSubjectBounds(layout) {
    if (!image.naturalWidth || !image.naturalHeight) return null;
    const area = layout.subjectArea;
    if (!area) return null;
    const frame = image.getBoundingClientRect();
    const scale = Math.max(
      frame.width / image.naturalWidth,
      frame.height / image.naturalHeight
    );
    const renderedWidth = image.naturalWidth * scale;
    const renderedHeight = image.naturalHeight * scale;
    const [horizontal = "center", vertical = "center"] = layout.objectPosition.split(" ");
    const alignments = { left: 0, center: 0.5, right: 1 };
    const imageLeft = frame.left + (frame.width - renderedWidth) * alignments[horizontal];
    const imageTop = frame.top + (frame.height - renderedHeight) * alignments[vertical];
    return {
      left: Math.max(frame.left, imageLeft + renderedWidth * area.left / 100),
      top: Math.max(frame.top, imageTop + renderedHeight * area.top / 100),
      right: Math.min(frame.right, imageLeft + renderedWidth * area.right / 100),
      bottom: Math.min(frame.bottom, imageTop + renderedHeight * area.bottom / 100),
    };
  }

  function positionCaption(layout) {
    const caption = $("photoCaption");
    if (!layout || caption.classList.contains("hidden")) return;
    const preferred = layout.position || "center";
    const positions = [
      preferred,
      "top-left", "top-right", "center-left", "center-right",
      "bottom-left", "bottom-right", "center",
    ].filter((position, index, list) => list.indexOf(position) === index);
    const subject = getSubjectBounds(layout);
    if (!subject) {
      caption.dataset.position = preferred;
      fitCaption();
      return;
    }

    const frame = caption.parentElement.getBoundingClientRect();
    let bestPosition = preferred;
    let bestScore = Number.POSITIVE_INFINITY;
    for (const position of positions) {
      caption.dataset.position = position;
      fitCaption();
      const bounds = caption.getBoundingClientRect();
      const overlapWidth = Math.max(
        0,
        Math.min(bounds.right, subject.right) - Math.max(bounds.left, subject.left)
      );
      const overlapHeight = Math.max(
        0,
        Math.min(bounds.bottom, subject.bottom) - Math.max(bounds.top, subject.top)
      );
      const outside = Math.max(0, frame.left - bounds.left)
        + Math.max(0, frame.top - bounds.top)
        + Math.max(0, bounds.right - frame.right)
        + Math.max(0, bounds.bottom - frame.bottom);
      const score = overlapWidth * overlapHeight + outside * frame.width * 4;
      if (score < bestScore) {
        bestScore = score;
        bestPosition = position;
      }
      if (score === 0) break;
    }
    caption.dataset.position = bestPosition;
    fitCaption();
  }

  function fitCaption() {
    const caption = $("photoCaption");
    if (caption.classList.contains("hidden")) return;
    caption.style.fontSize = "";
    const minimumSize = parseFloat(
      getComputedStyle(caption).getPropertyValue("--caption-font-min")
    ) || 12;
    for (let attempt = 0; attempt < 3 && caption.scrollHeight > caption.clientHeight; attempt += 1) {
      const currentSize = parseFloat(getComputedStyle(caption).fontSize);
      const fittedSize = currentSize * caption.clientHeight / caption.scrollHeight;
      const nextSize = Math.max(minimumSize, Math.min(currentSize, fittedSize));
      caption.style.fontSize = `${nextSize}px`;
      if (nextSize === minimumSize) break;
    }
  }

  function advanceSlide() {
    if (!slides.length) return;
    if (historyCursor < history.length - 1) {
      historyCursor += 1;
      const priorSlide = slides.find((slide) => slide.id === history[historyCursor]);
      if (priorSlide) showSlide(priorSlide);
      return;
    }
    if (!queue.length) shuffleQueue();
    const nextId = queue.shift();
    const nextSlide = slides.find((slide) => slide.id === nextId);
    if (!nextSlide) {
      advanceSlide();
      return;
    }
    history.push(nextId);
    if (history.length > 80) history.shift();
    historyCursor = history.length - 1;
    showSlide(nextSlide);
    preloadNext();
  }

  function previousSlide() {
    if (historyCursor <= 0) return;
    historyCursor -= 1;
    const previous = slides.find((slide) => slide.id === history[historyCursor]);
    if (previous) showSlide(previous);
  }

  async function loadSlides(keepCurrent = false) {
    try {
      const response = await fetch("/api/slides", { cache: "no-store" });
      if (!response.ok) throw new Error("Could not load the slideshow manifest.");
      const data = await response.json();
      if (!Array.isArray(data.slides)) throw new Error("Invalid slideshow manifest response.");
      slides = data.slides.filter(
        (slide) => slide && typeof slide.id === "string" && typeof slide.image === "string"
      );
      const savedSlide = keepCurrent && currentSlide
        ? slides.find((slide) => slide.id === currentSlide.id)
        : null;
      queue = [];
      history = [];
      historyCursor = -1;
      if (savedSlide) {
        history.push(savedSlide.id);
        historyCursor = 0;
        showSlide(savedSlide);
      } else if (slides.length) {
        shuffleQueue();
        advanceSlide();
      } else {
        currentSlide = null;
        image.classList.add("hidden");
        $("photoCaption").classList.add("hidden");
        $("photoPlaceholder").classList.remove("hidden");
        $("photoPlaceholder").querySelector("p").textContent =
          "Add approved photographs and matching thoughts to static/photos/manifest.json.";
      }
    } catch (error) {
      $("photoPlaceholder").classList.remove("hidden");
      $("photoPlaceholder").querySelector("p").textContent =
        "The slideshow manifest could not be loaded. Live predictions will continue to work.";
      $("connectionStatus").textContent = "● RECONNECTING";
    }
  }

  function scheduleSlide() {
    window.clearTimeout(slideTimer);
    if (slideshowPaused || !slides.length || currentMode === "meter" || currentMode === "special") {
      return;
    }

    slideTimer = window.setTimeout(() => {
      advanceSlide();
      scheduleSlide();
    }, slideDuration * 1000);
  }

  window.addEventListener("resize", () => {
    if (!currentSlide) return;
    const layout = currentSlide.text_layout || {};
    applyResponsiveCaptionSettings(layout);
    positionCaption(layout);
  });

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

  function renderResults(data) {
    $("girlCount").textContent = data.girl;
    $("boyCount").textContent = data.boy;
    $("totalVotes").textContent = data.total;
    const girlShare = data.total ? data.girl_percent : 50;
    const boyShare = data.total ? data.boy_percent : 50;
    $("girlPercent").textContent = `${girlShare}%`;
    $("boyPercent").textContent = `${boyShare}%`;
    $("meterSubtitle").textContent = data.total
      ? "Live share of guest predictions."
      : "An even split to start; the first prediction will set the pace.";
    $("girlFill").style.height = `${girlShare}%`;
    $("boyFill").style.height = `${boyShare}%`;
    $("specialMessage").textContent = data.special_message || "A little more love is on the way";
  }

  function updateMusic(data) {
    const button = $("toggleMusicButton");
    const available = Boolean(data.music_url);
    musicAllowed = Boolean(data.music_enabled && available);
    if ((audio.getAttribute("src") || "") !== (data.music_url || "")) {
      audio.pause();
      audio.src = data.music_url || "";
    }
    button.disabled = !available || !musicAllowed;
    button.setAttribute("aria-label", audio.paused ? "Enable music" : "Pause music");
    button.title = audio.paused ? "Enable music" : "Pause music";
    if (!available) {
      $("audioStatus").textContent = "Optional music is not configured.";
    } else if (!musicAllowed) {
      audio.pause();
      $("audioStatus").textContent = "Music is disabled in the admin controls.";
    } else if (!musicReady) {
      $("audioStatus").textContent = "Music is ready. Use the bottom music control to start playback.";
    } else if (audio.paused && !userPausedMusic) {
      audio.play().catch(() => {
        $("audioStatus").textContent = "Use the bottom music control to allow audio playback.";
      });
    }
  }

  async function processCommand(data) {
    if (lastCommandVersion === null) {
      lastCommandVersion = data.command_version;
      return;
    }
    if (data.command_version === lastCommandVersion) return;
    lastCommandVersion = data.command_version;
    if (data.display_command === "next") advanceSlide();
    if (data.display_command === "previous") previousSlide();
    if (data.display_command === "reload") await loadSlides(true);
    scheduleSlide();
  }

  async function refresh() {
    try {
      const response = await fetch("/api/results", { cache: "no-store" });
      if (!response.ok) throw new Error("Results request failed.");
      const data = await response.json();
      $("connectionStatus").textContent = "● LIVE";
      const girlDelta = previousGirl === null ? 0 : data.girl - previousGirl;
      const boyDelta = previousBoy === null ? 0 : data.boy - previousBoy;
      if (
        previousVoteSequence !== null
        && data.vote_sequence > previousVoteSequence
      ) {
        meterUntil = Date.now() + 10000;
        const newVotes = data.vote_sequence - previousVoteSequence;
        $("displayToast").textContent =
          `${newVotes} new prediction${newVotes === 1 ? "" : "s"} just arrived!`;
        $("displayToast").classList.add("show");
        window.clearTimeout(toastTimeout);
        toastTimeout = window.setTimeout(
          () => $("displayToast").classList.remove("show"), 2400
        );
        pulse($("totalVotes"));
        if (girlDelta > 0) pulseFill($("girlFill"));
        if (boyDelta > 0) pulseFill($("boyFill"));
      }
      previousGirl = data.girl;
      previousBoy = data.boy;
      previousVoteSequence = data.vote_sequence;
      currentMode = data.display_mode || "auto";
      slideDuration = Number.isInteger(data.slide_duration)
        ? Math.min(120, Math.max(5, data.slide_duration))
        : 15;
      slideshowPaused = Boolean(data.slideshow_paused);
      $("slideshowState").textContent = slideshowPaused
        ? "Slideshow paused"
        : `Next slide in about ${slideDuration} seconds`;
      renderResults(data);
      updateMusic(data);
      selectView();
      if (lastControlVersion !== data.control_version) {
        lastControlVersion = data.control_version;
        scheduleSlide();
      }
      await processCommand(data);
    } catch (error) {
      $("connectionStatus").textContent = "● RECONNECTING";
      if (currentMode === "auto" && Date.now() >= meterUntil) showView("slideshow");
    } finally {
      window.setTimeout(refresh, 5000);
    }
  }

  $("toggleMusicButton").addEventListener("click", async () => {
    if (!musicAllowed) return;
    if (audio.paused) {
      musicReady = true;
      userPausedMusic = false;
      try {
        await audio.play();
        $("audioStatus").textContent = "Music is playing.";
        $("toggleMusicButton").setAttribute("aria-label", "Pause music");
        $("toggleMusicButton").title = "Pause music";
      } catch (error) {
        $("audioStatus").textContent = "Music could not start. Check the configured audio file.";
      }
    } else {
      audio.pause();
      userPausedMusic = true;
      $("toggleMusicButton").setAttribute("aria-label", "Enable music");
      $("toggleMusicButton").title = "Enable music";
      $("audioStatus").textContent = "Music is paused on this display.";
    }
  });

  audio.addEventListener("error", () => {
    $("audioStatus").textContent = "Optional music could not be loaded; the display continues without audio.";
  });

  loadSlides().then(scheduleSlide);
  refresh();
})();
