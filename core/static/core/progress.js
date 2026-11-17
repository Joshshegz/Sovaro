(() => {
  const overlay = document.getElementById("work-progress");
  if (!overlay) return;

  const title = document.getElementById("progress-title");
  const description = document.getElementById("progress-description");
  const tip = document.getElementById("progress-tip");
  const source = document.getElementById("progress-source");
  const time = document.getElementById("progress-time");
  let active = false;
  let secondsTimer;
  let tipsTimer;

  const expertTips = [
    { text: "Review your existing posts before setting new social media goals.", author: "Kirsti Lang · Buffer", url: "https://buffer.com/resources/social-media-marketing-strategy/" },
    { text: "Focus on one or two platforms you can manage well before expanding.", author: "Kirsti Lang · Buffer", url: "https://buffer.com/resources/social-media-marketing-strategy/" },
    { text: "Choose a few recurring content themes so you do not start from scratch every week.", author: "Kirsti Lang · Buffer", url: "https://buffer.com/resources/social-media-marketing-strategy/" },
    { text: "Repurpose posts that performed well and are still relevant to your audience.", author: "Rochi Zalani · Buffer", url: "https://buffer.com/resources/repurposing-content-guide/" },
    { text: "Think about ways to reuse an idea while you are creating the original piece.", author: "Rochi Zalani · Buffer", url: "https://buffer.com/resources/repurposing-content-guide/" },
    { text: "Connect social media targets to business goals such as enquiries or sales.", author: "Sam Kendall · Sprout Social", url: "https://sproutsocial.com/insights/social-media-content-strategy/" },
    { text: "Check which posts helped your goal, then update the next month's plan.", author: "Sam Kendall · Sprout Social", url: "https://sproutsocial.com/insights/social-media-content-strategy/" },
  ];

  const content = {
    strategy: {
      title: "Putting your strategy together",
      description: "Sovaro is building your plan. Please keep this tab open.",
    },
    scan: {
      title: "Reading your website",
      description: "Sovaro is drafting your brand details. Please keep this tab open.",
    },
    repurpose: {
      title: "Rebuilding your content",
      description: "Sovaro is extracting the strongest ideas, testing hooks, and writing native drafts for each platform.",
    },
    caption: {
      title: "Reading the writing choices",
      description: "Sovaro is reviewing the hook, structure, credibility, platform fit, and next action.",
    },
    profile: {
      title: "Optimizing your profile",
      description: "Sovaro is reviewing clarity, search language, credibility, audience fit, and the next action.",
    },
  };

  function showTip(index) {
    const item = expertTips[index];
    tip.textContent = item.text;
    source.textContent = item.author;
    source.href = item.url;
  }

  function reset() {
    clearInterval(secondsTimer);
    clearInterval(tipsTimer);
    overlay.hidden = true;
    document.body.classList.remove("progress-open");
    document.querySelectorAll("form[data-progress-mode] button[type=submit], form[data-progress-mode] button:not([type])")
      .forEach((button) => { button.disabled = false; });
    active = false;
  }

  document.querySelectorAll("form[data-progress-mode]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (active) return;
      active = true;

      const details = content[form.dataset.progressMode] || content.strategy;
      title.textContent = details.title;
      description.textContent = details.description;
      showTip(0);
      time.textContent = "Time elapsed: 0 seconds";
      overlay.hidden = false;
      document.body.classList.add("progress-open");
      form.querySelectorAll("button").forEach((button) => { button.disabled = true; });
      title.focus();

      const startedAt = Date.now();
      let tipIndex = 0;
      secondsTimer = setInterval(() => {
        const seconds = Math.floor((Date.now() - startedAt) / 1000);
        time.textContent = `Time elapsed: ${seconds} ${seconds === 1 ? "second" : "seconds"}`;
        if (seconds >= 30) {
          description.textContent = "Still working. Please keep this tab open while Sovaro finishes.";
        }
      }, 1000);
      tipsTimer = setInterval(() => {
        tipIndex = (tipIndex + 1) % expertTips.length;
        showTip(tipIndex);
      }, 7000);

      // Give the browser a frame to display the overlay before native navigation.
      setTimeout(() => HTMLFormElement.prototype.submit.call(form), 80);
    });
  });

  // A restored page should never retain a stale loading overlay.
  window.addEventListener("pageshow", reset);
})();
