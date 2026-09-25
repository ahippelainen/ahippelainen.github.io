# hippe.fi

Personal site of Antti Hippeläinen. Hugo (extended, version pinned in `.github/workflows/deploy.yml`), custom layouts, no theme dependency. This repo is public; everything in it is visible to anyone. The owner's manual is `GUIDE.md`, local and gitignored; keep it in step with any change to content structure, front matter, config or the publish flow.

## Structure
- `hugo.yaml` — site config, nav, external links, math delimiters, comments ids.
- `content/_index.md` — front page bio. `content/research/_index.md` — intro of the research page; the paper list comes from `data/publications.yaml` (newest first, `note` = commentary under each paper, optional `image` under `assets/` shown beside it).
- `content/blog/<slug>/index.md` — posts (page bundles, images next to the text). `content/projects/<slug>.md` — things built, with optional `repo`, `link`, `tags`, and a `cover.jpg` thumbnail when the project is a folder. `content/ideas/<slug>.md` — open ideas, with an optional `status: open|taken|done` tag. `data/reading.yaml` — the "to read and watch" list at the bottom of the Ideas page, in sections (empty sections are skipped), items with optional `image`. Section list pages take their list heading from `list_title` in `_index.md`.
- `layouts/` — templates. `assets/css/main.css` — all styling. `assets/images/portrait.jpg` — front-page photo, shown if present.
- `static/fonts/` — self-hosted Source Serif 4 + Inter (OFL, licence files alongside). `static/katex/` — self-hosted KaTeX CSS + fonts (MIT), loaded only on pages with math.
- Math is rendered at build time (`layouts/_markup/render-passthrough.html`). Raw HTML in Markdown is dropped (`unsafe: false`).
- Other files in a post folder (PDFs, code, archives, subfolders included) are published next to the post whether linked or not; link them relatively.
- Images in posts: `![alt](photo.jpg "Caption")` with the file next to `index.md`. `layouts/_markup/render-image.html` resizes to 800/1600 px, emits a `srcset`, and turns the title into a caption.
- Tables: `layouts/_markup/render-table.html` wraps every Markdown table in `div.table-wrap`, which scrolls sideways when the table is wider than the column; cells do not wrap except in the first column (`main.css`).
- Thumbnails: every list (blog, projects, ideas, front page) shows a square thumbnail for a page whose folder holds a `cover.*` image, else the first image in the folder (`layouts/_partials/thumb.html`). The same image is the page's `og:image` for link previews. A page needs to be a folder (`<slug>/index.md`) for this; a bare `<slug>.md` has no images.
- Colour theme is light by default; the header toggle switches to dark, remembers the choice in localStorage, and tells the giscus iframe to follow. Each section has its own accent (`--accent-*` tokens, applied via `body.section-<name>`; light-mode values are the dark-mode hues darkened to at least 4.5:1 against the page); the top-of-page wash is warm orange in light and teal in dark (`--wash-*`).
- JavaScript on the site: the theme toggle, the giscus widget, and `assets/js/bg.js`, a fixed background canvas visible only through a lens around the pointer and masked out of the content column (side margins only, nothing on phones). Dark, small lens: a grid warped by a hidden geometry (gentle Zel'dovich cosmic web plus gravity wells in the embedding-diagram convention, voids, spinning lens, black hole, cosmic strings, gravitational-wave packet, an inspiralling and merging binary on a 90 s clock cycle, tidal shear; a star orbits the black hole), seeded per browser tab in sidebar slots; a click perturbs it in one of four physical ways. Light, large lens: a faint flat grid; a click draws a labelled bubble-chamber reaction from a particle/reaction table (decay chains, Feynman line codes), whose tracks fade piece by piece. Off under `prefers-reduced-motion`.
- Front page: `assets/images/portrait.jpg` (square, ≥ 800 px) becomes the circular portrait; `params.now` in `hugo.yaml` is an optional "Currently …" line.

## Commands
- After cloning, once: `git config core.hooksPath .githooks`.
- Preview with drafts: `hugo server -D` → http://localhost:1313/
- Build check: `hugo --gc --quiet` (a bad math snippet fails the build and says where).
- Import a finished post from the blogposts repo (`~/Git/blogposts`): `/import-post <path>`.
- Propose pictures for papers, list items, ideas and projects that have none: `/illustrate` (fetches sources, shows the pick, the user approves).
- Go live: `/publish`. It includes a mandatory claims review by the `claims-referee` agent whenever content changed: the blog is personal and scientific, and nothing overstated or unsupported goes out under his name. Never push directly. A git pre-push hook (`.githooks/pre-push`, in this repo) refuses commits that `/publish` has not reviewed.
- The skills (`/publish`, `/import-post`, `/illustrate`), the agents (`claims-referee`, `blog-editor`) and the Claude Code hook that blocks push commands live in the owner's private dotfiles, not here; this repo carries no `.claude/` directory. That hook matches command text, so a file that mentions pushing is written with the Write tool, not a heredoc.

## Deployment
Pushing to `main` runs the workflow, which builds the site and publishes it to GitHub Pages (Pages source = GitHub Actions; actions pinned to commit SHAs, Dependabot proposes updates). GitHub repo: `ahippelainen/ahippelainen.github.io`. The custom domain is configured in the repo's Pages settings, not by a CNAME file (ignored for Actions deploys). The first publish, in order (details in `/publish`): verify the domain at account level (TXT record), create the repo, deploy and check on github.io, attach the domain, switch DNS, enforce HTTPS.

DNS at OVH (values from GitHub's docs). Delete the existing apex A/AAAA and `www` A records first; keep the TXT record permanently:

```
A     @    185.199.108.153 / 185.199.109.153 / 185.199.110.153 / 185.199.111.153
AAAA  @    2606:50c0:8000::153 / 2606:50c0:8001::153 / 2606:50c0:8002::153 / 2606:50c0:8003::153
CNAME www  ahippelainen.github.io.
TXT   _github-pages-challenge-ahippelainen   (value from GitHub → Settings → Pages → Add a domain)
```

## Comments
giscus (GitHub Discussions in this repo, category `Announcements`). Rendered on blog posts only, and only once `params.comments.repoId` and `categoryId` are set in `hugo.yaml`. A post opts out with `comments: false`. `giscus.json` limits which sites may embed the widget. Setup steps are in `/publish` under "First publish".

## Conventions
- `draft: true` keeps a page out of the built site. Sample content ships as drafts; delete it once real content exists.
- Front matter: `title`, `date`, `description` (one sentence, used in lists, link previews and the RSS feed).
- Keep it simple: one CSS file, no build-time dependencies beyond Hugo, no third-party requests except giscus.
- Commit messages: `feat|fix|content|chore: ...`, no attribution trailers.
