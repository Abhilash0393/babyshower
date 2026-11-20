(() => {
  const mode = document.body.dataset.mode || "qr";
  const voteCard = document.getElementById("voteCard");
  const thankyouCard = document.getElementById("thankyouCard");
  const status = document.getElementById("voteStatus");
  const chosen = document.getElementById("chosenText");
  const again = document.getElementById("againButton");
  const announcement = document.getElementById("choiceAnnouncement");
  const buttons = [...document.querySelectorAll(".choice")];
  const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
  const motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");
  let audioContext = null;
  let boothResetTimeout = null;
  let boothCountdownInterval = null;
  let busy = false;

  function applyMotionPreference() {
    document.body.classList.toggle("reduce-motion", motionPreference.matches);
  }

  applyMotionPreference();
  if (motionPreference.addEventListener) {
    motionPreference.addEventListener("change", applyMotionPreference);
  } else {
    motionPreference.addListener(applyMotionPreference);
  }

  function playSelectionChime() {
    try {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) return;
      if (!audioContext) audioContext = new AudioContextClass();
      if (audioContext.state === "suspended") {
        audioContext.resume().catch((error) => console.warn("Could not play selection chime.", error));
      }

      [784, 1047].forEach((frequency, index) => {
        const start = audioContext.currentTime + index * 0.13;
        const oscillator = audioContext.createOscillator();
        const volume = audioContext.createGain();
        oscillator.type = "sine";
        oscillator.frequency.setValueAtTime(frequency, start);
        volume.gain.setValueAtTime(0.0001, start);
        volume.gain.exponentialRampToValueAtTime(0.12, start + 0.02);
        volume.gain.exponentialRampToValueAtTime(0.0001, start + 0.3);
        oscillator.connect(volume);
        volume.connect(audioContext.destination);
        oscillator.start(start);
        oscillator.stop(start + 0.31);
      });
    } catch (error) {
      console.warn("Could not play selection chime.", error);
    }
  }

  function animateSelection(button) {
    buttons.forEach((choice) => {
      choice.classList.toggle("is-selecting", choice === button);
      choice.classList.toggle("is-muted", choice !== button);
    });
    const choice = button.dataset.choice;
    announcement.textContent = `You chose ${choice === "girl" ? "Baby Girl" : "Baby Boy"}!`;
    announcement.classList.add("is-visible");
    const duration = motionPreference.matches ? 800 : 1400;
    return new Promise((resolve) => {
      window.setTimeout(() => {
        buttons.forEach((choice) => {
          choice.classList.remove("is-selecting", "is-muted");
        });
        announcement.classList.remove("is-visible");
        announcement.textContent = "";
        resolve();
      }, duration);
    });
  }

  function showConfirmation(choice, note = "") {
    chosen.textContent = `You chose ${choice === "girl" ? "Baby Girl" : "Baby Boy"}`;
    voteCard.classList.add("hidden");
    thankyouCard.classList.remove("hidden");
    again.textContent = mode === "booth" ? "Click to Vote Again" : "Done";
    document.getElementById("thankyouStatus").textContent = note;
    again.focus();
    startBoothReset();
  }

  function resetBoothVoting() {
    window.clearTimeout(boothResetTimeout);
    window.clearInterval(boothCountdownInterval);
    boothResetTimeout = null;
    boothCountdownInterval = null;
    thankyouCard.classList.add("hidden");
    voteCard.classList.remove("hidden");
    status.textContent = "";
    buttons.forEach((button) => { button.disabled = false; });
    buttons[0].focus();
  }

  function startBoothReset() {
    if (mode !== "booth") return;
    window.clearTimeout(boothResetTimeout);
    window.clearInterval(boothCountdownInterval);
    const thankyouStatus = document.getElementById("thankyouStatus");
    let secondsRemaining = 5;
    thankyouStatus.textContent = `Returning to voting in ${secondsRemaining} seconds.`;
    boothCountdownInterval = window.setInterval(() => {
      secondsRemaining -= 1;
      if (secondsRemaining > 0) {
        thankyouStatus.textContent = `Returning to voting in ${secondsRemaining} seconds.`;
      }
    }, 1000);
    boothResetTimeout = window.setTimeout(resetBoothVoting, 5000);
  }

  async function cast(choice, button) {
    if (busy) return;
    busy = true;
    status.textContent = `You chose ${choice === "girl" ? "Baby Girl" : "Baby Boy"}! Saving your prediction…`;
    buttons.forEach((button) => { button.disabled = true; });
    playSelectionChime();
    const selectionAnimation = animateSelection(button);

    try {
      const response = await fetch("/api/vote", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
        },
        body: JSON.stringify({ choice, source: mode }),
      });
      const data = await response.json();
      if (response.ok && data.accepted === true) {
        await selectionAnimation;
        showConfirmation(choice);
        return;
      }
      if (
        response.status === 409
        && data.already_voted === true
        && (data.recorded_choice === "girl" || data.recorded_choice === "boy")
      ) {
        await selectionAnimation;
        showConfirmation(data.recorded_choice, "Your earlier prediction is already recorded.");
        return;
      }
      await selectionAnimation;
      status.textContent = data.error || "Could not record your prediction. Please try again.";
    } catch (error) {
      await selectionAnimation;
      status.textContent = "Connection issue. Your vote was not confirmed; please try again.";
    } finally {
      if (voteCard.classList.contains("hidden") === false) {
        buttons.forEach((button) => { button.disabled = false; });
      }
      busy = false;
    }
  }

  buttons.forEach((button) => {
    button.addEventListener("click", () => cast(button.dataset.choice, button));
  });

  again.addEventListener("click", () => {
    if (mode === "booth") {
      resetBoothVoting();
      return;
    }
    document.getElementById("thankyouStatus").textContent =
      "Thank you for joining the prediction!";
  });
})();
