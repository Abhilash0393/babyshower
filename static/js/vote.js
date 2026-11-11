(() => {
  const mode = document.body.dataset.mode || "qr";
  const voteCard = document.getElementById("voteCard");
  const thankyouCard = document.getElementById("thankyouCard");
  const status = document.getElementById("voteStatus");
  const chosen = document.getElementById("chosenText");
  const again = document.getElementById("againButton");
  const buttons = [...document.querySelectorAll(".choice")];
  const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
  let busy = false;

  function animateSelection(button) {
    buttons.forEach((choice) => {
      choice.classList.toggle("is-selecting", choice === button);
      choice.classList.toggle("is-muted", choice !== button);
    });
    button.classList.add("is-selecting");
    const duration = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 1400;
    return new Promise((resolve) => {
      window.setTimeout(() => {
        buttons.forEach((choice) => {
          choice.classList.remove("is-selecting", "is-muted");
        });
        resolve();
      }, duration);
    });
  }

  function showConfirmation(choice, note = "") {
    chosen.textContent = `You chose ${choice === "girl" ? "Baby Girl" : "Baby Boy"}`;
    voteCard.classList.add("hidden");
    thankyouCard.classList.remove("hidden");
    again.textContent = mode === "booth" ? "Cast My Vote Again" : "Done";
    document.getElementById("thankyouStatus").textContent = note;
    again.focus();
  }

  async function cast(choice, button) {
    if (busy) return;
    busy = true;
    status.textContent = "Saving your prediction…";
    buttons.forEach((button) => { button.disabled = true; });
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
      thankyouCard.classList.add("hidden");
      voteCard.classList.remove("hidden");
      status.textContent = "";
      buttons.forEach((button) => { button.disabled = false; });
      buttons[0].focus();
      return;
    }
    document.getElementById("thankyouStatus").textContent =
      "Thank you for joining the prediction!";
  });
})();
