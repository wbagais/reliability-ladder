# Archived versions

Byte-identical snapshots of documents whose canonical copy gets rewritten in
place, kept so an older version stays readable without git archaeology.

Convention: before a major rewrite of a living document, copy the current
version here as `<name>-vN-<YYYY-MM-DD>.md|html` (the date is the version's
last day as canonical, i.e. the rewrite date). Never edit an archived copy —
it exists to show exactly what the document looked like.

| file | what it is |
|---|---|
| `article-iterations-v1-2026-08-22.md` | The article raw-material doc as it stood before the 2026-08-26 full-ladder rewrite — the deterministic-gate era ("model-facing rungs not yet characterised"; cost curve "still to come"). |
| `article-build-log-v1-2026-08-22.html` | The typeset build log matching it, same era, before the same rewrite. |
| `article-longform-2026-08-28.md` | The LONGFORM build report as it stood on 2026-08-28 (NOT the submission - that is docs/article-v2.md, a different document) — the visibility-question rewrite, before the 2026-08-30 revision added the three-draw re-test of our own arms, the judge arm, the FiNER recall decomposition, the refusal, and the context-menu rejection. |
| `article-v2-submitted-2026-08-30.docx` | The BUILT `.docx` of `docs/article-v2.md` exactly as submitted on 2026-08-30, moved here 2026-08-31 from `docs/` where it sat under its export filename as though it were a living document. Kept although it is a build output: the source `.md` says what was written, this says what was actually sent. Never regenerate it in place — a rebuild from a later `article-v2.md` would no longer be the submitted artifact. |
| `infoq-article-draft-2026-08-24.md` | The FIRST InfoQ draft, written 2026-08-24, moved here 2026-08-31 from `docs/infoq-article-draft.md` where it had been sitting as if current. It is the ancestor of `docs/article-v2.md` (the 3,579-word submission), which superseded it; the live draft is `docs/article-v3.md`. |
| `article-build-log-v2-2026-08-28.html` | The typeset BUILD LOG as it stood when the published artifact stopped being a build log. On 2026-08-30 the artifact URL was re-pointed at `docs/article.html` — the article itself, framed around the visibility question — so this is the last version of the ladder-framed page that was ever live. |

The canonical copies are `docs/article-iterations.md` (the build-log prose,
still maintained) and `docs/article.html` (the typeset ARTICLE, which is what
the published artifact now serves). `docs/article-build-log.html` no longer
exists as a living document: the artifact it fed was re-pointed at the article
on 2026-08-30 and its last live version is archived here as v2.
