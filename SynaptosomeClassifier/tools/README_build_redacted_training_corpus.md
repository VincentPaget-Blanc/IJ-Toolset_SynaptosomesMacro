# Redacted Training Corpus Builder

`build_redacted_training_corpus.py` prepares manually reviewed analyses for classifier retraining while removing source-specific names.

## Easiest use
Run the script with **no arguments** (for example, press **Run** in Spyder). A GUI opens. Add a parent folder or analysis ZIP files, choose an output folder, then click **Build redacted corpus**.

Parent folders are searched recursively for complete `___Gallery.zip` / `___RoiSet.zip` / `___Results.csv` triplets and for whole-analysis ZIPs containing those triplets.

## Command line
```bash
python build_redacted_training_corpus.py "/path/to/manual_analyses" \
  --output-dir "/path/to/redacted_training_corpus"
```

Use `--overwrite` only when intentionally replacing existing `Archive_*.zip` outputs.

## Output
The tool writes neutral `Archive_###` / `Acquisition_###` identifiers, a redaction manifest, SHA-256 checksums, and a redaction audit. TIFF payloads, ROI binary payloads/manual states, and numeric Results rows are verified during the build. No original-to-redacted name map is written.

**Dependencies:** Python standard library only. Fiji is not required.
