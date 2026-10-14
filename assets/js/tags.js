// Blog list filter. Tag buttons toggle; a post shows when it carries every selected tag.
// The selection lives in the hash (#tag=a,b), so post pages can link to a pre-filtered list.
(() => {
  const items = document.querySelectorAll(".post-list li[data-tags]");
  const buttons = document.querySelectorAll(".tag-bar [data-tag]");
  const reset = document.querySelector(".tag-reset");
  const status = document.querySelector(".tag-status");

  const selected = () => {
    const m = /^#tag=([^&]*)$/.exec(location.hash);
    return m ? decodeURIComponent(m[1]).split(",").filter(Boolean) : [];
  };
  const select = (tags) => history.replaceState(null, "", tags.length ? "#tag=" + tags.join(",") : location.pathname + location.search);

  const apply = () => {
    const sel = selected();
    let shown = 0;
    for (const li of items) {
      const tags = li.dataset.tags.split(" ");
      li.hidden = !sel.every((t) => tags.includes(t));
      if (!li.hidden) shown++;
    }
    for (const b of buttons) b.setAttribute("aria-pressed", sel.includes(b.dataset.tag));
    reset.disabled = !sel.length;
    status.textContent = !sel.length ? "" : shown ? `Showing ${shown} of ${items.length} posts` : "No post has all of these tags";
  };

  for (const b of buttons) b.addEventListener("click", () => {
    const sel = selected(), t = b.dataset.tag;
    select(sel.includes(t) ? sel.filter((x) => x !== t) : [...sel, t]);
    apply();
  });
  reset.addEventListener("click", () => { select([]); apply(); });
  addEventListener("hashchange", apply);
  apply();
})();
