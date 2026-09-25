# Version 13b classifier reproducibility test report

**Status: PASS**

The bundled classifier retrainer was executed in this environment on both the identifying source training corpus and the independently generated redacted training corpus.

## Default historical-classifier mode

Both executions returned:

```text
archives=6
acquisitions=52
rows=6341 keep=5618 discard=723
hard_invalid_v13b=300
coefficients=-1.4169522023,-0.4050302588,42.6003834983
archive_holdout_pooled_auc=0.9600094933
```

The refitted equation is therefore

$$
z
=
-1.4169522023
-0.4050302588\,\mathrm{maxLocalSNR}
+42.6003834983\,\mathrm{meanBackgroundCV},
$$

which rounds to the Version 13b macro equation

$$
z
=
-1.4169522
-0.4050303\,\mathrm{maxLocalSNR}
+42.6003835\,\mathrm{meanBackgroundCV}.
$$

After deterministic neutral-ID substitution, every exported per-ROI numeric/statistical value and manual label was identical between the source and redacted runs. Archive-held-out score differences were at machine precision only; maximum absolute difference was

$$
4.44\times10^{-16}.
$$

## Runtime-geometry sensitivity mode

The script was also executed with `--geometry imagej_runtime` on both forms of the corpus. Both executions returned the same sensitivity-fit result:

```text
archives=6
acquisitions=52
rows=6341 keep=5618 discard=723
hard_invalid_v13b=300
coefficients=-1.4019333136,-0.4009464551,41.9102997209
archive_holdout_pooled_auc=0.9596766371
```

This second model is an audit only. It is not substituted into Version 13b because the repository release intentionally freezes the historically fitted coefficients. See `FEATURE_GEOMETRY_PARITY_AUDIT.md`.

## Data-preservation checks

Redaction also passed direct payload comparison:

- 52/52 Gallery TIFF payloads identical;
- 6,341/6,341 ImageJ ROI binary payloads identical;
- 52/52 Results-table numeric/body payloads identical after header replacement.

The public package contains no original-to-redacted mapping.
