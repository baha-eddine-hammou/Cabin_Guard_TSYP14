---
name: ieee-paper-writer
description: Master academic and scientific manuscript writer and reviewer enforcing strict, formal publication rules (no forward references, strict equation typesetting, origin citations, precise figure standards, and mathematical rigor). Use PROACTIVELY to write, audit, critique, or polish scientific papers.
metadata:
  model: inherit
---

# Project Guidelines & Authoritative Manuscript Rules

## Manuscript style rules

| # | Rule |
|---|------|
| 1 | No `---` or `—`. `--` only for numeric and label ranges. |
| 2 | No `\emph{}` or `\textbf{}` in running paragraphs. Italic = maths mode only. |
| 3 | No invented multi-hyphen compounds. |
| 4 | No forward references, to sections or equations. No roadmap paragraph. |
| 5 | Whatever Section N uses must already be defined by Section N. |
| 6 | No punctuation in a displayed equation, closing it **or separating two of them**. |
| 7 | Equations on their own line, never inline in a paragraph. |
| 8 | `Equation~\eqref{}`, never a bare `(7)`. |
| 9 | Cite the source of every borrowed or standard equation. |
| 10 | Define every symbol immediately after its equation. |
| 11 | One notation per quantity, across the whole paper. |
| 12 | No "This work" row in a related-work table. |
| 13 | Label sub-panels (a), (b), (c) inside the figure. |
| 14 | A legend on every panel that has more than one curve. |
| 15 | Black / red / blue / green. Never red beside amber. Vary line style too. |
| 16 | Zoom inset wherever the curves of interest overlap at full scale. |
| 17 | Figure labels in real LaTeX maths; prefer TikZ over an exported bitmap. |
| 18 | Float immediately after the paragraph that discusses it, in the source... |
| 18b | ...and typeset inside that section too. Check the `.aux`, on a built PDF. |

| 20 | Scenario definitions live with the experiments. |
| 21 | References numbered in order of first citation. |
| 22 | One-sentence captions. Name the float and list its panels, nothing more. |
| 23 | Two panels too small to read are two figures, not one. |
| 24 | No full stop before a closing parenthesis. |
| 25 | No prose forward pointers either: "below", "later in this section". |
| 26 | Springer `sn-jnl` table pattern: caption above, `\botrule`, no `\centering`. |
| 27 | Don't present a searched parameter as computed, or single two out of a set. |
| 28 | No "guarantees" for a closed-loop property. Measure it and quote the margin. |
| 29 | Cite borrowed design choices, not only borrowed equations. |
| 30 | A citation must support the sentence it is attached to. Read before citing. |
| 31 | Cite the origin of a technique, not a paper that happens to use it. |

## Citations chosen from titles

The recurring failure is picking a reference by the words in its title. Five
in this manuscript, all the same shape: a *terminal* sliding-mode paper cited
for the *nonsingular fast* terminal surface; sigma-modification credited to an
application paper; a plain SMC paper listed among "learning-augmented studies
with an RBF or DNN feedforward"; a **quasi-Newton** paper cited for a
**quasi-sliding** surface; and the manuscript's own PSO cost attributed to two
papers that only inspired the approach.

Rules that prevent all five: cite the origin of a technique rather than a user
of it; when a sentence lists several works under one property, check that
property holds for each of them individually; and if the source is paywalled
and you cannot read it, do not cite it for a specific equation, cite something
you can read that states the same thing. Where verification failed, say so in
the hand-back rather than leaving it silent.

## The two that keep coming back

**Equations are written about, not deposited.** Every one needs a sentence
introducing it *and* a sentence after it that names it as `Equation~(n)`. The
failure mode is a run of equations where each is introduced by "which gives"
and none is ever named again, so the reader walks from (6) to (7) to (8) with
nothing tying them together. Rule 24 in the checker lists every label no
`\eqref` names; that list should always be empty.

**Punctuation is not part of maths.** Not at the end, and not between two
equations in the same display. `a=b,\qquad c=d` becomes `a=b\qquad c=d`; a
comma before `\\` inside `aligned` goes too. Commas inside a list or an
interval are not separators and stay.

## What the checker cannot see

Four rules need a human or a rendered-PDF check, so verify them by eye and say
in the hand-back that you did:

- **Rules 9, 10, 11** are semantic. Read each equation and ask: where did this
  come from, is every new symbol defined below it, and is this the same letter
  the rest of the paper uses?
- **Rules 13 to 17** need the rendered figure. Open the PDF, look at every
  figure, and check panel letters, legends and colour separation.
- **Rule 25** (prose forward pointers) is invisible to it because there is no
  `\ref` to follow. Grep for `below|later|remainder of the paper` by hand.
- **Rules 27 to 29** are about what the text claims, not how it is written.
  For 28 in particular: if the manuscript says a bound is never approached,
  find the script that could measure it, run it, and put the measured worst
  case in the sentence. On this project that check found a claimed order of
  magnitude of margin was a factor of two on one of its two axes.

A block diagram is held to the same standard as the equations. Every signal it
draws must exist in the text under the same name, every block input must be
something the corresponding equation actually takes, and no line may cross
another. Draw it in TikZ and read it back against the equations one arrow at a
time; three of the four errors found in this project's Figure 4 were signals
that the equations did not have.

Rule 22 is checked mechanically (one sentence, 160 characters), but the fix is
editorial: whatever the caption was explaining has to reappear in the paragraph
that discusses the float, or it is simply lost. Move it, do not delete it.

A figure with two panels that are each too small to read is two figures, not
one. Splitting means a new file from the plotting script, a second `figure`
environment, and a second `\ref` in the paragraph, and the split panels must
each drop their `(a)`/`(b)` label, since rule 13 applies to sub-panels only.
