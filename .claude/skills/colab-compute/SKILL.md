---
name: colab-compute
description: Required whenever work on this repository would train a model, run an evaluation or experiment script, extract features from a dataset, or download a dataset. Heavy compute never runs in the Claude cloud session (it spends the user's session credits); it runs in the user's Google Colab notebook. Use before running anything under prototype/experiments/, any training, any data download, or any job longer than about two minutes.
---

# Heavy compute runs in Google Colab, never in the Claude session

The user pays for the cloud session's compute. Training, evaluation and data
work run in their Google Colab notebook,
`prototype/experiments/colab/CabinGuard_Colab.ipynb`, not here. This is a
standing requirement, not a preference to weigh.

## Never run in the Claude session

- Any training: `train_branches.py`, `train_motion_real.py`, or any `fit` on real data.
- Any evaluation or experiment that produces paper numbers: `evaluate_fusion.py`,
  `fault_matrix.py`, `external_checks.py`.
- Any extraction or download of datasets: `physionet_fetch`, `extract_cardiac.py`,
  `extract_motion.py`, `extract_seizeit2.py`, Kaggle/UCI/OpenNeuro/UEA loaders.
- Any other command expected to take more than about two minutes of CPU, or to
  download more than a few megabytes.

If such a job is already running when this applies, stop it.

## Allowed in the Claude session

- Reading and editing code, the paper, the notebook and docs.
- `python -m pytest prototype/tests` (fixture data only), the manuscript checker,
  and building the PDF.
- Reading a few kilobytes from a remote source to design a loader: an HTTP
  header, a directory listing, one small annotation file.
- `export_paper_numbers.py` and the paper build, once the user has brought
  Colab results into the repository.

## Workflow when results are needed

1. Make the code change, and add or update the matching cell in the Colab
   notebook so one "Run all" reproduces every result and downloads the outputs.
2. Run the unit tests and the checker, commit and push to the working branch.
3. Tell the user, step by step, which notebook cells to run (or "Runtime > Run
   all"), roughly how long each takes, and how to bring the outputs back: unzip
   `cabinguard_outputs.zip` into the repository root, then commit and push, or
   attach the result JSON files to the chat.
4. When the results arrive, regenerate `paper_numbers*.tex` with
   `export_paper_numbers.py`, update the paper, and verify it (checker, page
   count, rendered tables).

Never quote a number in the paper that was not produced by the Colab run and
committed to `prototype/results/`.
