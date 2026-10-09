# Project Guidelines & Authoritative Manuscript Rules

The manuscript is an IEEE conference paper (`IEEEtran`, `[conference]` option)
for the TSYP14 CabinGuard-ADI challenge. The challenge spec book sets the page
limits and the section list; IEEE editorial style sets the mechanics; the house
rules below sit on top of both and win wherever IEEE leaves a choice open.

Run `python tools/check_manuscript.py IEEE_Research_Paper_CabinGuard.tex` after
every edit. It checks the mechanical rules; the rest are listed under "What the
checker cannot see".

## Challenge constraints

- Phase 1 paper: at most 5 pages including references. Phase 2: at most 6.
- Phase 1 review is anonymous: the author block stays "Anonymous Authors",
  with no names, affiliations, e-mail addresses or PDF author metadata.
- Section order follows the spec book's IEEE structure, merging only where the
  spec says "as applicable": Abstract, Introduction and Motivation, Related
  Work, Problem Definition, System Architecture, Detection Methodology, Safety
  and Fault Handling, Cybersecurity and Threat Model, Evaluation Methodology,
  Results, Conclusion, References.
- Every quantitative claim names its evidence class: synthetic simulation,
  public dataset (named), or literature value (cited). Nothing synthetic is
  reported as clinical or vehicle performance.

## Manuscript style rules

| # | Rule |
|---|------|
| 1 | No `---` or `—`. `--` only for numeric and label ranges. |
| 2 | No `\emph{}` or `\textbf{}` in running paragraphs. Italic = maths mode only. Reference list and float internals are exempt. |
| 3 | No invented multi-hyphen compounds. |
| 4 | No forward references, to sections or equations. No roadmap paragraph. |
| 5 | Whatever Section N uses must already be defined by Section N. |
| 6 | No punctuation in a displayed equation, closing it **or separating two of them** (house style; IEEE permits it). |
| 7 | Equations on their own line, never inline in a paragraph. Inline maths is for symbols and short values only. |
| 8 | Cross-references by `\eqref`, `\ref`, never a typed number. IEEE form: `Equation~\eqref{}` / `Fig.~\ref{}` / `Table~\ref{}` / `Algorithm~\ref{}`; at the start of a sentence write `Figure`, not `Fig.` |
| 9 | Cite the source of every borrowed or standard equation. |
| 10 | Define every symbol immediately after its equation. |
| 11 | One notation per quantity, across the whole paper. |
| 12 | No "This work" row in a related-work table. |
| 13 | Label sub-panels (a), (b), (c) inside the figure. |
| 14 | A legend on every panel that has more than one curve. |
| 15 | Black / red / blue / green. Never red beside amber. Vary line style too, so the figure survives grayscale printing. |
| 16 | Zoom inset wherever the curves of interest overlap at full scale. |
| 17 | Figure labels in real LaTeX maths; prefer TikZ or PGFPlots over an exported bitmap. |
| 18 | Float immediately after the paragraph that discusses it, in the source, with `[!t]` placement (IEEE top-of-column)... |
| 18b | ...and typeset in that section or on the page where it is first cited. Check the `.aux` on a built PDF. `figure*`/`table*` only when a single column cannot hold it. |
| 19 | Introduction and Related Work are separate sections, as the spec book lists them. No subsection with a single paragraph that could be the section itself. |
| 20 | Scenario definitions live with the experiments. |
| 21 | References numbered in order of first citation, IEEE format: initials before surname, abbreviated venue in italics, `vol.`, `no.`, `pp.`, year, DOI where one exists. `et al.` only above six authors. |
| 22 | One-sentence captions. Name the float and list its panels, nothing more. Table captions above the table, figure captions below. |
| 23 | Two panels too small to read are two figures, not one. |
| 24 | No full stop before a closing parenthesis. |
| 25 | No prose forward pointers either: "below", "later in this section". |
| 26 | IEEEtran table pattern: `\caption` then `\label` above the tabular, `\centering`, booktabs rules, no `\resizebox` or `\scalebox` (it scales the font below the template size); use `\footnotesize` and shorter headers instead. |
| 27 | Don't present a searched parameter as computed, or single two out of a set. |
| 28 | No "guarantees" for a closed-loop property. Measure it and quote the margin. |
| 29 | Cite borrowed design choices, not only borrowed equations. |
| 30 | A citation must support the sentence it is attached to. Read before citing. |
| 31 | Cite the origin of a technique, not a paper that happens to use it. |
| 32 | Abstract: one paragraph, at most 250 words, no citations, no displayed maths, every acronym spelled out. Keywords go in `IEEEkeywords` as Index Terms. |
| 33 | Acronyms spelled out at first use in the body as well as in the abstract, then used consistently. |
| 34 | SI units with a thin space (`3.2\,m/s$^2$`, `100\,ms`), the same unit for the same quantity throughout. |
| 35 | Regulations and standards are design targets unless certified: write "aligned with" or "targets", never "compliant" or "certified". |

## Citations chosen from titles

The recurring failure is picking a reference by the words in its title rather
than by what it says. Typical shapes: a paper on a neighbouring technique cited
for the one actually used; a method credited to an application paper instead
of its origin; a list of works under one property that only some of them have;
a bibliography entry whose authors, venue or year do not match any real
publication.

Rules that prevent all of them: cite the origin of a technique rather than a
user of it; when a sentence lists several works under one property, check that
property holds for each of them individually; verify every entry exists with
those authors, venue, volume and year before keeping it; and if the source is
paywalled and you cannot read it, do not cite it for a specific equation or
number, cite something you can read that states the same thing. Where
verification failed, say so in the hand-back rather than leaving it silent.

## The two that keep coming back

**Equations are written about, not deposited.** Every one needs a sentence
introducing it *and* a sentence after it that names it through `\eqref`. The
failure mode is a run of equations where each is introduced by "which gives"
and none is ever named again, so the reader walks from (6) to (7) to (8) with
nothing tying them together. The checker lists every equation label no
`\eqref` names; that list should always be empty.

**Punctuation is not part of maths.** Not at the end, and not between two
equations in the same display. `a=b,\qquad c=d` becomes `a=b\qquad c=d`; a
comma before `\\` inside `aligned` goes too. Commas inside a list or an
interval are not separators and stay.

## What the checker cannot see

These rules need a human or a rendered-PDF check, so verify them by eye and
say in the hand-back that you did:

- **Rules 9, 10, 11** are semantic. Read each equation and ask: where did this
  come from, is every new symbol defined below it, and is this the same letter
  the rest of the paper uses?
- **Rules 13 to 17** need the rendered figure. Open the PDF, look at every
  figure, and check panel letters, legends and colour separation.
- **Rule 25** (prose forward pointers) has no `\ref` to follow; the checker
  greps for `below|later|remainder of the paper`, but read the hits.
- **Rules 27 to 29 and 35** are about what the text claims, not how it is
  written. For 28 in particular: if the manuscript says a bound is never
  approached, find the script that could measure it, run it, and put the
  measured worst case in the sentence.
- **Every number in the Results section** must be produced by a script in
  `prototype/` whose output file is committed. Re-run it before quoting it.

A block diagram is held to the same standard as the equations. Every signal it
draws must exist in the text under the same name, every block input must be
something the corresponding equation or module actually takes, and no line may
cross another. Draw it in TikZ and read it back against the equations and the
code one arrow at a time.

Rule 22 is checked mechanically (one sentence, 160 characters), but the fix is
editorial: whatever the caption was explaining has to reappear in the paragraph
that discusses the float, or it is simply lost. Move it, do not delete it.

A figure with two panels that are each too small to read is two figures, not
one. Splitting means a new file from the plotting script, a second `figure`
environment, and a second `\ref` in the paragraph, and the split panels must
each drop their `(a)`/`(b)` label, since rule 13 applies to sub-panels only.

## Code and repository

- Heavy compute runs in the user's Google Colab notebook
  (`prototype/experiments/colab/CabinGuard_Colab.ipynb`), never in the Claude
  session: no training, evaluation, feature extraction or dataset download
  here. Follow `.claude/skills/colab-compute/SKILL.md`.

- `prototype/` is the only Python package root. Scripts that produce paper
  numbers live in `prototype/experiments/` and write to `prototype/results/`.
- Raw datasets are never committed. Loaders download them into
  `data/` (git-ignored) from the official source.
- `python -m pytest prototype/tests` must pass before every push.
