(() => {
  const $ = (id) => document.getElementById(id);
  const status = $("adminStatus");
  const csrfToken = document.querySelector('meta[name="csrf-token"]').content;

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
    if (!response.ok) {
      throw new Error(result.error || "Request failed.");
    }
    return result;
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
  }

  async function refresh() {
    try {
      const response = await fetch("/api/admin", { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Could not load event status.");
      }
      render(data);
    } catch (error) {
      status.textContent = error.message;
    }
  }

  async function runAction(data, successMessage) {
    try {
      render(await post(data));
      status.textContent = successMessage;
    } catch (error) {
      status.textContent = error.message;
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

  refresh();
  window.setInterval(refresh, 3000);
})();
