# Synaptosome Classifier Retrainer — Version 13b

`SynaptosomeClassifierRetrainer_Version13b.py` rebuilds and audits the AutoROI logistic classifier from manually reviewed training archives.

## Easiest use
Run the script with **no arguments** (for example, press **Run** in Spyder). A GUI opens. Add the redacted corpus folder or archive ZIPs, choose an output folder, and click **Retrain classifier**.

For exact Version 13b reproduction, keep the defaults:
- geometry: `historical_classifier`
- quantification size: `24`
- **Exclude hard-invalid ROIs from fitting:** off

## Command line
```bash
python SynaptosomeClassifierRetrainer_Version13b.py \
  "/path/to/redacted_training_corpus/redacted_archives" \
  --output-dir "/path/to/classifier_retrain_output"
```

## Output
The retrainer exports the ROI-level training/audit tables, acquisition summary, archive-held-out validation, out-of-fold predictions, fitted coefficients, `model.json`, and the ImageJ-ready classifier equation.

**Dependencies:** `numpy`, `pandas`, `tifffile`, `scipy`, and `scikit-learn`. Fiji is not required.
