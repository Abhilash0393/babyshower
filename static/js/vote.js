(() => {
  const mode = document.body.dataset.mode || "qr";
  const voteCard = document.getElementById("voteCard");
  const thankyouCard = document.getElementById("thankyouCard");
  const status = document.getElementById("voteStatus");
  const chosen = document.getElementById("chosenText");
  const again = document.getElementById("againButton");
  const celebration = document.getElementById("voteCelebration");
  const celebrationLabel = document.getElementById("celebrationLabel");
  const celebrationIcons = {
    girl: document.getElementById("girlCelebrationIcon"),
    boy: document.getElementById("boyCelebrationIcon"),
  };
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

  async function showVoteCelebration(choice) {
    Object.entries(celebrationIcons).forEach(([name, icon]) => {
      icon.classList.toggle("hidden", name !== choice);
    });
    celebrationLabel.textContent = choice === "girl" ? "Baby Girl!" : "Baby Boy!";
    celebration.classList.remove("hidden");
    await new Promise((resolve) => window.requestAnimationFrame(resolve));
    celebration.classList.add("is-visible");
    await new Promise((resolve) => window.setTimeout(
      resolve, motionPreference.matches ? 450 : 1150
    ));
    celebration.classList.remove("is-visible");
    celebration.classList.add("hidden");
    Object.values(celebrationIcons).forEach((icon) => icon.classList.add("hidden"));
  }

  async function confirmVote(choice, note = "") {
    try {
      await showVoteCelebration(choice);
    } catch (error) {
      console.error("The vote was confirmed, but its celebration could not be displayed.", error);
    }
    showConfirmation(choice, note);
  }

  function showConfirmation(choice, note = "") {
    chosen.textContent = `You chose ${choice === "girl" ? "Baby Girl" : "Baby Boy"}`;
    voteCard.classList.add("hidden");
    thankyouCard.classList.remove("hidden");
    thankyouCard.classList.remove("is-entering");
    void thankyouCard.offsetWidth;
    thankyouCard.classList.add("is-entering");
    window.setTimeout(() => thankyouCard.classList.remove("is-entering"), 450);
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

  async function cast(choice) {
    if (busy) return;
    busy = true;
    status.textContent = `You chose ${choice === "girl" ? "Baby Girl" : "Baby Boy"}! Saving your prediction…`;
    buttons.forEach((button) => { button.disabled = true; });
    playSelectionChime();

    try {
      let response;
      try {
        response = await fetch("/api/vote", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": csrfToken,
          },
          body: JSON.stringify({ choice, source: mode }),
        });
      } catch (error) {
        console.warn("Could not reach the voting service.", error);
        status.textContent = "Could not reach the voting service. Check your connection and try again.";
        return;
      }

      let data;
      try {
        data = await response.json();
      } catch (error) {
        console.error(`Voting service returned an unreadable response (HTTP ${response.status}).`, error);
        status.textContent = response.ok
          ? "Your vote may have been recorded, but confirmation was unreadable. Please check before voting again."
          : `Voting service returned an unreadable response (HTTP ${response.status}). Please reload or ask event staff for help.`;
        return;
      }

      if (!data || typeof data !== "object" || Array.isArray(data)) {
        console.error(`Voting service returned an invalid response body (HTTP ${response.status}).`);
        status.textContent = response.ok
          ? "Your vote may have been recorded, but confirmation was invalid. Please check before voting again."
          : `Voting service returned an invalid response (HTTP ${response.status}). Please reload or ask event staff for help.`;
        return;
      }

      if (response.ok && data.accepted === true) {
        await confirmVote(choice);
        return;
      }
      if (
        response.status === 409
        && data.already_voted === true
        && (data.recorded_choice === "girl" || data.recorded_choice === "boy")
      ) {
        await confirmVote(data.recorded_choice, "Your earlier prediction is already recorded.");
        return;
      }
      status.textContent = data.error || "Could not record your prediction. Please try again.";
    } finally {
      if (voteCard.classList.contains("hidden") === false) {
        buttons.forEach((button) => { button.disabled = false; });
      }
      busy = false;
    }
  }

  buttons.forEach((button) => {
    button.addEventListener("click", () => cast(button.dataset.choice));
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
