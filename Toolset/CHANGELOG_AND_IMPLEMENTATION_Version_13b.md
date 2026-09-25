# SynaptosomesMacro AutoROI - Version 13b

**Repository-facing version:** `13b`  
**Documentation date:** 25/09/2026  
**Versioning note:** `13a` was the first AutoROI iteration. The intermediate `v1.x` labels used during local development are retained only in historical diff filenames for audit provenance and are not the repository-facing release name.

## 1. Scope

Version 13b preserves the upstream `SynaptosomesMacro_Randomization.ijm` detection, normalization, quantification, plotting, export, and Monte-Carlo/randomization logic. The AutoROI extension is intentionally narrow: it adds technical ROI validity checks, a statistical ROI discard score, review/automation modes, dataset-level threshold preflight, provenance logging, and a small number of Fiji UI/table synchronization safeguards.

The ROI decision path is deliberately separated into three layers:

1. **Hard validity rejection** - deterministic technical QC. Invalid crop/measurement data are rejected regardless of classifier score.
2. **Statistical discard classifier** - technically valid ROIs receive a continuous discard score.
3. **Operating threshold** - the continuous score is converted into keep/discard according to the selected workflow.

This separation is important because the classifier coefficients and the operating threshold solve different problems.

## 2. Version 13b changelog

### 2.1 25/09/2026 surgical progress-window hotfix

The dedicated threshold-preflight processing window introduced during the final internal `v1.10.2` development step had a window-lifecycle bug. Its first call attempted to send an update command to a named ImageJ Text Window before that window had been created. The same helper also used a single source backslash for the special update command rather than the escaped `\\Update:` form used by ImageJ's own macro examples.

The fix is deliberately limited to UI window handling:

```ijm
progressWindow="["+thresholdProgressWindowTitle+"]";
if(!isOpen(thresholdProgressWindowTitle))
    run("Text Window...", "name="+progressWindow+" width=52 height=7 monospaced");
print(progressWindow, "\\Update:"+text);
```

Closure is likewise guarded and uses the Text Window command directly:

```ijm
if(isOpen(thresholdProgressWindowTitle))
    print("["+thresholdProgressWindowTitle+"]", "\\Close");
```

The ROI Manager close is also guarded with `isOpen("ROI Manager")`. No detection, preprocessing, hard-invalid rule, classifier feature, coefficient, threshold rule, quantification, export, or randomization code was changed by this hotfix.

The documentation was also checked for repository Markdown math rendering. Display equations now use `$$ ... $$` and inline equations use `$ ... $` instead of the previous `\[ ... \]` / `\( ... \)` delimiter style. This is a presentation-only correction; the equations themselves are unchanged.

This bug is confirmed to have been introduced when the dedicated processing window was added: the retained `HISTORICAL_INTERNAL_v1.10.1_to_v1.10.2.diff` contains the first addition of `updateThresholdProgressWindow()` and its first preflight call, whereas internal `v1.10.1` had only the existing ImageJ status/progress reporting.

### 2.2 25/09/2026 surgical edge-padding selection hotfix

A second runtime regression appeared during dataset threshold preflight:

```text
No selection
Roi.getContainedPoints(xPoints, yPoints)
```

This was **not** caused by the progress Text Window. It was introduced by the geometric edge-padding validity extension added in the same final internal `v1.10.2` development step. The retained `HISTORICAL_INTERNAL_v1.10.1_to_v1.10.2.diff` shows the exact introduction:

```ijm
isInvalid=tileHasInvalidEdgePadding(tileX, tileY, boxSize, channels);
if(!isInvalid) makeOval(x0, y0, quantSize, quantSize);
if(!isInvalid && selectionHasInvalidPixels(channels)) isInvalid=true;
```

The intended logic was: when edge-padding QC already marks a candidate invalid, do not create an oval and do not inspect oval pixels. However, the ImageJ macro interpreter evaluates both operands of `&&`. Therefore `selectionHasInvalidPixels()` was still executed even when `!isInvalid` was false. Because the oval had intentionally not been created, `Roi.getContainedPoints()` raised `No selection`.

The repair changes only this control-flow expression:

```ijm
if(!isInvalid){
    makeOval(x0, y0, quantSize, quantSize);
    if(selectionHasInvalidPixels(channels)) isInvalid=true;
}
```

The hard-invalid decision itself is unchanged: edge-padded candidates are still rejected; non-edge-padded candidates still undergo the same quantification-circle and background-annulus zero/NaN checks. No classifier feature, coefficient, threshold, detection, quantification, or randomization code was changed.

### 2.3 25/09/2026 surgical ROI-Manager lifecycle hotfix

After the threshold-preflight UI hardening, the real analysis could reach ROI review without the detected ROI list that drives the green/red overlay. This regression was introduced by one line in the final internal `v1.10.2` development step:

```ijm
if(isOpen("ROI Manager")) close("ROI Manager");
setBatchMode(true);
```

Closing the visible manager was intentional: it keeps the Swing `JList` out of the rapid reset/rebuild loop used by dataset threshold preflight and prevents the FlatLaf repaint race. The missing piece was **state restoration after the dry run**.

ImageJ uses a hidden RoiManager only when batch mode is active and no visible RoiManager exists. When batch mode ends, ImageJ clears its internal batch-mode RoiManager reference. The normal analysis later enters batch mode again, detects candidates, and expects the visible ROI Manager to preserve that list across `setBatchMode("exit and display")` so `reviewSynaptosomes()` can build the green/red Gallery overlay. Because the visible manager had never been reopened, the candidate list could be lost at that transition.

The repair is deliberately limited to restoring the pre-existing UI state after all threshold-preflight mutations are complete:

```ijm
labels=Array.copy(baseLabels);
setBatchMode("exit and display");

run("ROI Manager...");
roiManager("Reset");
```

The manager remains closed throughout the high-frequency threshold scan, so the FlatLaf mitigation is preserved. It is reopened only after the dry run has finished and is empty before the normal analysis begins. The normal processing path therefore once again has the same visible-manager invariant as the last known working internal `v1.10.1` implementation.

No candidate detection, hard-invalid decision, classifier feature, coefficient, score, threshold, quantification, export, or randomization code was changed.

### 2.4 Consolidated Version 13b changes

Relative to the first AutoROI iteration, Version 13b consolidates the following changes:

- optional automatic ROI discard with **User validated** and **Fully automatic** modes;
- mandatory hard rejection of invalid measurement pixels;
- logistic-regression discard score using local signal-to-noise and local background heterogeneity;
- batch-only **Analyze dataset and suggest threshold** preflight;
- conservative fully automatic threshold adaptation from the current dataset score distribution;
- run-parameter CSV written before processing for provenance;
- session-only persistence of accepted GUI values;
- Results → Randomizer synchronization hardening;
- safer pooled-output naming and exclusion of prior `_Pooled_` files from later pooling;
- dedicated threshold-analysis progress window;
- mitigation of the visible ROI Manager / FlatLaf list repaint race during threshold preflight;
- additional geometric edge-padding hard-invalid detection for crop padding that can lie outside the measurement circle and background annulus;
- repository-facing version provenance changed to `13b`.

`RandomizerColocalization_.class` and the scientific Randomizer invocation are not modified.

## 3. Data redaction policy for this release

All dataset-specific names are removed from the public/documented package. This includes original sample names, conditions, acquisition names, dates embedded in acquisition identifiers, anatomical labels, marker names, and source filenames whenever they could identify the source dataset.

Public identifiers use neutral deterministic labels only:

- `Archive_001` … `Archive_006`;
- `Acquisition_001` … `Acquisition_052`;
- `ROI_0001` … within each acquisition;
- `Channel_1`, `Channel_2`, …;
- `Validation_Dataset_A`, `Validation_Dataset_B`.

The redaction map from original identifiers to public identifiers is **not included** in the release package. Numeric measurements, manual keep/discard labels, classifier features, and validation counts are preserved.

## 4. Processing logic intentionally unchanged

The following scientific processing components are not redesigned by Version 13b:

- candidate spot detection;
- image reduction and normalization;
- Gallery construction/cutout layout;
- central quantification geometry;
- local-background annulus geometry;
- downstream intensity quantification;
- coordinate/distance calculations;
- control/scatter/distribution image generation;
- FCS-like/CytoFile export;
- Monte-Carlo/randomization calculations and scientific parameters.

The extension changes the green/kept versus red/discarded state of detected candidates and adds QC/provenance around that decision.

---

# 5. Stage 1 - deterministic hard validity rejection

Every candidate first passes technical validity QC. This is not a statistical or biological classification step.

A ROI is hard-discarded if either of the existing measurement regions contains an actual `NaN` or exact-zero invalid pixel in a measured channel. Version 13b additionally rejects geometric crop padding when a complete outer edge of the full detection square is zero/NaN across all measured channels.

The additional edge rule is deliberately narrow. Version 13b does **not** use the broader rule “any zero anywhere in the detection square = invalid,” because an isolated legitimate zero-valued pixel outside the measurement regions should not automatically reject an otherwise usable ROI.

Hard-invalid ROIs are stored in `hardDiscarded[]`, shown red, excluded from statistical scoring, and cannot be restored during manual review.

**Implementation:**

| Function | Approx. line | Purpose |
|---|---:|---|
| `identifyInvalidROIs()` | 714 | hard-validity mask |
| `tileHasInvalidEdgePadding()` | 762 | detection-square edge-padding check |
| `edgeIsAllInvalid()` | 771 | all-channel edge test |
| `selectionHasInvalidPixels()` | 783 | measurement-region NaN/zero test |

---

# 6. Stage 2 - statistical discard classifier

Only technically valid ROIs enter the classifier. The classifier uses measurements already available from the same central quantification circle and local background annulus used by the analysis.

For channel $c$, define the local signal-to-noise ratio as

$$
\mathrm{LocalSNR}_{c}
=
\frac{\mu_{\mathrm{center},c}-\mu_{\mathrm{background},c}}
     {\sigma_{\mathrm{background},c}}.
$$

The classifier uses the strongest focal evidence across channels:

$$
\mathrm{maxLocalSNR}
=
\max_c \left(\mathrm{LocalSNR}_{c}\right).
$$

For channel $c$, local background heterogeneity is expressed as the coefficient of variation

$$
\mathrm{BackgroundCV}_{c}
=
\frac{\sigma_{\mathrm{background},c}}
     {\left|\mu_{\mathrm{background},c}\right|}.
$$

Across $C$ measured channels, the classifier uses

$$
\mathrm{meanBackgroundCV}
=
\frac{1}{C}\sum_{c=1}^{C}\mathrm{BackgroundCV}_{c}.
$$

The fitted logistic model is

$$
z
=
-1.4169522
-0.4050303\,\mathrm{maxLocalSNR}
+42.6003835\,\mathrm{meanBackgroundCV}.
$$

The continuous discard score is the logistic transform

$$
\mathrm{discardScore}
=
\sigma(z)
=
\frac{1}{1+e^{-z}}.
$$

A low score is **keep-like** and a high score is **discard-like**. Operationally it is best described as a continuous discard score rather than as a universally calibrated biological probability.

The identical equation is used by the read-only threshold preflight and by real processing so that threshold estimation and final classification cannot silently diverge.

**Implementation:** `collectDiscardScores()` around line 395 and `automaticDiscardROIs()` around line 788.

## 6.1 Why `maxLocalSNR` was used

The QC classifier should not require every biological channel to be strongly positive. A genuine candidate may have strong focal signal in one measured channel and weak or absent signal in another. Using the maximum SNR lets one convincing focal signal support ROI validity instead of turning biological marker negativity into a QC failure.

## 6.2 Why `meanBackgroundCV` was used

Background CV measures local heterogeneity relative to the local mean and is therefore less tied to absolute fluorescence scale than raw background standard deviation. Averaging it across channels makes the background-quality term channel-symmetric.

---

# 7. How the classifier coefficients were obtained

The values

$$
\beta_0=-1.4169522,\qquad
\beta_1=-0.4050303,\qquad
\beta_2=42.6003835
$$

were not hand-selected. They are the back-transformed coefficients of a class-balanced, L2-regularized logistic regression fitted to the original manual ROI decisions. The complete training material required to reproduce that fit is bundled in this release under neutral identifiers.

## 7.1 Training corpus and manual labels

The calibration corpus contains **6,341 manually reviewed ROI decisions from 52 acquisitions grouped in 6 archives**:

- **5,618** manual keeps;
- **723** manual discards.

For ROI $i$,

$$
y_i=
\begin{cases}
0, & \text{manual keep},\\
1, & \text{manual discard}.
\end{cases}
$$

The manual label can be reconstructed from the saved analysis result membership. As an independent audit, the same labels were reconstructed from the saved ROI stroke state; agreement was **6,341/6,341** with zero mismatches.

The historical coefficient fit used **all 6,341 manual labels**. The later Version 13b hard-invalid gate is a separate runtime QC stage and was not retroactively used to remove rows from the historical fit. This distinction is necessary to reproduce the deployed coefficients exactly.

## 7.2 Historical feature extraction used for fitting

For the classifier fit, each 48 × 48 px detection tile was evaluated using pixel-centre geometry. Let

$$
r(x,y)=\sqrt{(x+0.5-24)^2+(y+0.5-24)^2}.
$$

The central measurement mask was

$$
r\le 12,
$$

and the historical local-background annulus was

$$
12<r\le 23.
$$

Background standard deviation used the sample standard deviation, i.e. $N-1$ in the denominator. From the per-channel measurements, the two model predictors are

$$
x_{i1}=\mathrm{maxLocalSNR}_i,
\qquad
x_{i2}=\mathrm{meanBackgroundCV}_i.
$$

## 7.3 Standardization before logistic regression

The two features were standardized before fitting:

$$
\widetilde{x}_{ij}
=
\frac{x_{ij}-\mu_j}{s_j}.
$$

For the 6,341-row training corpus, the recovered standardization parameters are

$$
\boldsymbol{\mu}
=
\begin{bmatrix}
6.0313528861\\
0.0792368816
\end{bmatrix},
\qquad
\mathbf{s}
=
\begin{bmatrix}
3.2184054224\\
0.1485571140
\end{bmatrix}.
$$

Standardization is why the large-looking raw CV coefficient should not be interpreted as being roughly 100 times more important than the SNR coefficient: the two raw predictors occupy very different numerical ranges.

## 7.4 Class balancing and regularization

The training labels are imbalanced, with many more keeps than discards. The fit therefore used balanced class weights

$$
w_k=\frac{N}{K N_k},
$$

where $N=6341$, $K=2$, and $N_k$ is the number of observations in class $k$. This gives approximately

$$
w_{\mathrm{keep}}=0.5643467426,
\qquad
w_{\mathrm{discard}}=4.3852005533.
$$

The exact recovered fitting configuration is:

```python
StandardScaler()
LogisticRegression(
    C=1.0,
    class_weight="balanced",
    solver="lbfgs",
    tol=1e-4,
    max_iter=100,
)
```

Conceptually, the standardized logistic model minimizes a class-weighted logistic loss with an L2 penalty on the feature coefficients:

$$
\mathcal{L}(\alpha,\boldsymbol{\gamma})
=
-\sum_i w_{y_i}
\left[
 y_i\log p_i+(1-y_i)\log(1-p_i)
\right]
+
\frac{\lambda_C}{2}\left\|\boldsymbol{\gamma}\right\|_2^2,
$$

with

$$
p_i
=
\frac{1}{1+
\exp\left[-\left(\alpha+\boldsymbol{\gamma}^{\mathsf T}\widetilde{\mathbf{x}}_i\right)\right]},
$$

where `C=1.0` sets the inverse regularization strength under the scikit-learn solver convention. The intercept is not regularized.

The recovered coefficients in standardized feature space are

$$
\alpha=-0.4843110806,
$$

$$
\boldsymbol{\gamma}
=
\begin{bmatrix}
-1.3035515811\\
6.3285900259
\end{bmatrix}.
$$

## 7.5 Back-transform to the raw feature units used by Fiji

The Fiji macro does not standardize each ROI explicitly, so the standardized model is algebraically converted back to raw units:

$$
\beta_j=\frac{\gamma_j}{s_j},
$$

and

$$
\beta_0
=
\alpha
-
\sum_j\frac{\gamma_j\mu_j}{s_j}.
$$

Running the bundled retrainer on the bundled redacted corpus produces

$$
\beta_0=-1.4169522023,
$$

$$
\beta_{\mathrm{SNR}}=-0.4050302588,
$$

$$
\beta_{\mathrm{CV}}=42.6003834983.
$$

Rounded to the precision stored in the macro, these are exactly

$$
\boxed{
\mathrm{logit}(\mathrm{discardScore})
=
-1.4169522
-0.4050303\,\mathrm{maxLocalSNR}
+42.6003835\,\mathrm{meanBackgroundCV}
}.
$$

The continuous discard score is then

$$
\mathrm{discardScore}
=
\frac{1}{1+e^{-z}}.
$$

## 7.6 Interpretation of the fitted coefficients

The negative SNR coefficient means stronger focal signal relative to local background decreases discard tendency:

$$
\beta_{\mathrm{SNR}}=-0.4050303<0.
$$

A one-unit increase in `maxLocalSNR`, holding background CV fixed, multiplies discard odds by

$$
e^{-0.4050303}\approx0.667,
$$

or roughly a 33% reduction in odds.

The positive CV coefficient means a more heterogeneous local background increases discard tendency:

$$
\beta_{\mathrm{CV}}=42.6003835>0.
$$

A more interpretable raw-unit change is +0.01 CV:

$$
e^{42.6003835\times0.01}\approx1.531,
$$

or roughly a 53% increase in discard odds, holding SNR fixed.

The intercept

$$
\beta_0=-1.4169522
$$

primarily positions the decision surface. At the hypothetical raw-feature origin,

$$
\sigma(-1.4169522)\approx0.195.
$$

That origin is not intended as a biological reference condition.

## 7.7 Archive-held-out validation

Validation holds out complete archives rather than randomly mixing ROIs from the same acquisition across training and test sets. This reduces leakage from acquisition-specific similarity.

| Held-out group | ROIs | Keeps | Discards | ROC AUC |
|---|---:|---:|---:|---:|
| `Archive_001` | 761 | 663 | 98 | 0.9658170961 |
| `Archive_002` | 2,257 | 1,957 | 300 | 0.9697104412 |
| `Archive_003` | 603 | 543 | 60 | 0.9716390424 |
| `Archive_004` | 487 | 453 | 34 | 0.9647448383 |
| `Archive_005` | 1,067 | 966 | 101 | 0.9708914991 |
| `Archive_006` | 1,166 | 1,036 | 130 | 0.9459162459 |

The pooled out-of-fold discrimination is

$$
\mathrm{ROC\ AUC}=0.9600094933.
$$

This is a discrimination metric, not proof that the 0–1 score is a universally calibrated biological probability.

## 7.8 Historical training geometry versus Fiji runtime geometry

A reproducibility audit identified a small but real implementation distinction: the historical coefficient fit used the mathematical annulus above, whereas the Fiji macro obtains the runtime background region through `Make Band...`. The resulting feature values are extremely highly correlated but are not pixel-for-pixel identical.

Across all 6,341 training ROIs:

$$
\rho(\mathrm{maxLocalSNR})=0.9999018222,
$$

$$
\rho(\mathrm{meanBackgroundCV})=0.9999241619.
$$

The bundled Python retrainer therefore exposes two explicit modes:

- `historical_classifier` - default; reproduces the Version 13b coefficients exactly;
- `imagej_runtime` - parity/sensitivity audit using reconstructed Fiji runtime band geometry.

As a sensitivity audit, refitting with runtime geometry gives coefficients close to, but not identical to, the historical model and a pooled held-out AUC of 0.9596766371. Version 13b **does not substitute those coefficients**. Changing the feature definition and coefficients together would constitute a new classifier version and should be independently validated.

## 7.9 Reproducibility correction relative to an earlier local retrainer prototype

Reconstruction of the complete original training corpus made it possible to identify the exact historical fitting protocol. An earlier local-purpose retrainer prototype had implemented a different future-refit workflow, including a different background-SD convention and a different fitting/row-selection policy. That prototype could be internally self-consistent but was **not** the provenance of the coefficients embedded in the macro.

The Version 13b package therefore supersedes that prototype for coefficient provenance. The bundled retrainer explicitly separates:

- exact historical coefficient reconstruction;
- current Fiji runtime-geometry auditing; and
- optional alternative refitting after hard-invalid exclusion.

No macro coefficient was changed as a result of this correction; instead, the documented training method is now the one that independently reproduces the already deployed numbers from the complete manual corpus.

---

# 8. Stage 3 - operating threshold

The fitted classifier outputs a continuous score. Green/red status is assigned only after applying an operating threshold $T$:

$$
\mathrm{discardScore}\ge T
\quad\Longrightarrow\quad
\mathrm{discard}.
$$

Therefore:

- lower $T$ = more aggressive discard;
- higher $T$ = more conservative discard.

Changing $T$ does not refit or change the logistic coefficients.

## 8.1 User validated mode

The review-oriented suggested threshold is

$$
T_{\mathrm{review}}=0.30.
$$

This is intended as automatic preselection followed by human review. The user may immediately validate the proposed gallery or enter the original click-to-toggle review loop. Hard-invalid ROIs remain locked red.

## 8.2 Fully automatic mode

For batch analyses, the read-only threshold preflight scores every technically valid candidate using the current GUI processing parameters. Let $\tilde{s}$ denote the median valid discard score across the dataset. Version 13b uses

$$
T_{\mathrm{auto}}
=
\min\left(
0.90,
\max\left(0.30,\tilde{s}+0.17\right)
\right).
$$

### Why the median

The median is robust to a minority of extreme poor-quality ROIs. A small number of scores near 1 cannot pull the dataset centre upward as strongly as a mean would.

### Why the +0.17 margin

The positive margin deliberately places the unattended automatic cutoff above the central score distribution. This makes fully automatic processing more conservative than the human-reviewed operating point and is designed to reduce silent removal of plausible biological ROIs.

### Why the 0.30–0.90 clamp

The lower bound prevents adaptation from becoming more aggressive than the review-oriented threshold. The upper bound prevents a shifted dataset from making automatic discard effectively unavailable.

### Limitation

Dataset-level adaptation cannot perfectly distinguish a global acquisition/background shift from a dataset containing a genuinely larger fraction of artifacts. A sufficiently poor dataset can raise the median and therefore make the automatic cutoff more permissive. The rule is intentionally simple and auditable until more independent blind manual data are available.

---

# 9. Redacted validation examples

The original dataset names are intentionally removed.

## Validation_Dataset_A

Recorded values:

| Metric | Value |
|---|---:|
| candidates | 2,368 |
| hard-invalid under previous measurement-region rule | 105 |
| geometric edge-padded candidates | 106 |
| median valid discard score | 0.1064 |
| User validated suggestion | 0.30 |
| raw fully automatic threshold | 0.2764 |
| final fully automatic threshold after lower clamp | 0.30 |

Numerically,

$$
0.1064+0.17=0.2764<0.30,
$$

so the lower clamp yields

$$
T_{\mathrm{auto}}=0.30.
$$

The two supplied analyses that both used 0.30 had identical saved ROI green/red status maps. Monte-Carlo randomization files are not expected to be byte-identical because the randomizer is stochastic.

## Validation_Dataset_B

Recorded values before the geometric edge-padding hardening:

| Metric | Value |
|---|---:|
| candidates | 1,975 |
| hard-invalid under previous measurement-region rule | 86 |
| geometric edge-padded candidates | 91 |
| edge-padded candidates missed by old hard rule | 5 |
| missed edge-padded candidates still green | 4 |
| median valid discard score | 0.2339 |
| User validated suggestion | 0.30 |
| fully automatic threshold before edge fix | 0.4039 |

Numerically,

$$
0.2339+0.17=0.4039.
$$

Because Version 13b excludes the additional edge-padded candidates before score pooling, the threshold preflight should be rerun rather than assuming 0.4039 remains exactly unchanged.

---

# 10. Threshold-preflight progress and FlatLaf hardening

The batch threshold preflight opens a lightweight ImageJ Text Window titled `Dataset threshold analysis progress`. The window is created explicitly before the first update and then refreshed in place with ImageJ's `\\Update:` Text Window command. It reports percentage, acquisition index, and processing stage while the existing Fiji status/progress UI remains active.

During testing, repeated ROI Manager reset/repopulation generated an AWT/FlatLaf list-paint exception. Version 13b closes the visible ROI Manager immediately before entering threshold-analysis batch mode, but only when that window exists:

```ijm
if(isOpen("ROI Manager")) close("ROI Manager");
setBatchMode(true);
```

This removes the visible Swing list from the high-frequency mutation path while preserving the hidden batch ROI Manager used during the dry-run. Normal interactive review behavior is unchanged.

**Implementation:** progress-window helper around lines 270–294; guarded ROI Manager close around line 316 (line numbers refer to the hotfixed Version 13b macro).

---

# 11. Run-parameter provenance

After the final GUI is accepted and before analysis processing starts, the macro writes a unique run-parameter file (`Run_Parameters.csv`, then numbered variants if needed).

The file records the accepted image/channel configuration, processing parameters, ROI automation state, review mode, operating threshold, threshold-preflight provenance when applicable, and randomization parameters.

Version 13b writes:

```text
Macro_version,13b
```

**Implementation:** `saveRunParameters()` around line 205.

---

# 12. Results → Randomizer synchronization hardening

The scientific Randomizer invocation and parameters are unchanged. Version 13b adds bounded waiting for expected Fiji table windows before rename/selection/save operations. This avoids intermittent failures where a CSV had been opened but the corresponding non-image window title had not yet been registered.

**Implementation:** `waitForWindow()` around line 508 and `closeWindowIfOpen()` around line 518.

---

# 13. Pooled output behavior

Existing `_Pooled_` files are excluded from subsequent pooling so that a previous aggregate cannot be pooled into a new aggregate. Pooled CytoFile and RandomizationResults outputs inherit the common acquisition/condition prefix when one exists.

---

# 14. Why the current classifier is frozen

The classifier coefficients should remain unchanged while additional independent manual data are collected because:

1. the current model is deliberately simple and interpretable;
2. the two retained features have a clear QC interpretation;
3. repeated refitting on automatic decisions would risk training the classifier on its own output;
4. technical crop failures are better handled by deterministic validity rules rather than by changing the statistical classifier;
5. threshold policy can be evaluated independently of coefficient fitting.

A future recalibration should use a larger independently manually annotated corpus and preserve acquisition grouping during validation.

---

# 15. Reproducible future recalibration

The release includes `tools/SynaptosomeClassifierRetrainer_Version13b.py`. Its default mode reproduces the historical Version 13b classifier from the redacted image/ROI/result triplets and exports the complete derived training table, coefficients, per-acquisition summaries, archive-held-out predictions, and model metadata.

For future work, the minimum retained row identity is

```text
archive_id
acquisition_id
roi_id
manual_label
maxLocalSNR
meanBackgroundCV
```

The bundled audit table additionally retains per-channel centre/background statistics and the current Version 13b hard-invalid flag.

For a future larger corpus, recommended validation principles remain:

- obtain independent manual labels rather than feeding automatic decisions back as ground truth;
- preserve acquisition/archive groups across validation folds;
- report coefficients, discrimination, precision-recall behavior, and calibration;
- compare operating thresholds by false-discard and missed-artifact rates;
- version the exact training-corpus checksum, feature definition, fitting code, software environment, and validation outputs;
- treat exclusion of hard-invalid rows from coefficient fitting as an explicit methodological change, not as a silent cleanup;
- consider fitting directly on the `imagej_runtime` geometry for a future classifier version, followed by fresh validation.

The retrainer provides `--exclude-hard-invalid` only as an explicit methodological alternative. It is **not** the historical Version 13b fit and does not reproduce the deployed coefficients.

---

# 16. Redacted original classifier training corpus included in this release

The final package contains the complete data actually required to reproduce classifier training, but all source-specific identifiers have been removed.

## 16.1 Redacted raw training inputs

`training_set/redacted_archives/` contains:

```text
Archive_001.zip
Archive_002.zip
Archive_003.zip
Archive_004.zip
Archive_005.zip
Archive_006.zip
```

Inside those archives, acquisitions are named only `Acquisition_001` … `Acquisition_052`. For each acquisition, the package retains exactly the classifier-relevant triplet:

```text
Acquisition_###___Gallery.zip
Acquisition_###___RoiSet.zip
Acquisition_###___Results.csv
```

Other downstream analysis artifacts are intentionally omitted from the public training corpus because they are not read by the classifier-fitting pipeline and therefore are not training inputs.

The redaction process preserves:

- the TIFF pixel payload used for feature extraction;
- every ImageJ ROI binary payload and therefore the manual green/red decisions;
- every numeric row/value in `Results.csv`;
- the grouping into 6 archives and 52 acquisitions.

It changes only identifying filenames/paths, ZIP metadata, and biological/channel names in tabular headers. Channel names become `Channel_1`, `Channel_2`, etc. No original-to-redacted lookup table is distributed.

A byte-level preservation audit confirmed:

- **52/52** Gallery TIFF payloads identical before versus after redaction;
- **6,341/6,341** ROI binary payloads identical;
- **52/52** `Results.csv` numeric/body tables identical after header redaction.

## 16.2 Derived reproducibility outputs

`training_set/reproducibility/` contains the outputs produced by rerunning the classifier script on the redacted raw training corpus, including:

- `training_rows_used_for_fit.csv` - the exact 6,341-row model-fitting table;
- `training_rows_audit.csv` - the same ROI-level features plus audit fields;
- `acquisition_summary.csv`;
- `archive_holdout_validation.csv`;
- `out_of_fold_predictions.csv`;
- `model_coefficients.csv`;
- `model.json`;
- `classifier_equation.txt`.

Corpus totals are:

| Item | Count |
|---|---:|
| archives | 6 |
| acquisitions | 52 |
| manual ROI decisions | 6,341 |
| manual keeps | 5,618 |
| manual discards | 723 |
| Version 13b hard-invalid audit flags | 300 |

The hard-invalid count is reported for audit. The historical coefficient fit still uses all 6,341 manual decisions, as explained in Section 7.

## 16.3 Raw versus redacted execution test

The bundled Python retrainer was run independently on both the identifying source corpus and the distributed redacted corpus.

After neutral identifier substitution:

- all per-ROI numeric/statistical fields and manual labels were exactly identical;
- the complete model-summary numeric output was exactly identical;
- fitted coefficients were exactly identical at the exported numeric precision;
- out-of-fold prediction differences were bounded by floating-point machine precision, with maximum absolute difference $4.44\times10^{-16}$;
- both runs produced pooled archive-held-out ROC AUC $0.9600094933$.

Therefore redaction changes identity only, not the training information or classifier result.

---

# 17. Implementation map

| Function / area | Approx. line | Purpose |
|---|---:|---|
| `GUI()` | 136 | acquisition parameters + AutoROI controls |
| `saveRunParameters()` | 205 | pre-run provenance CSV |
| `updateThresholdProgressWindow()` | 269 | dedicated threshold-preflight progress UI |
| `analyzeDatasetThreshold()` | 292 | read-only dataset score scan and threshold suggestion |
| visible ROI Manager close | 311 | FlatLaf/JList repaint-race mitigation during preflight |
| `collectDiscardScores()` | 395 | read-only classifier scoring |
| `waitForWindow()` / `closeWindowIfOpen()` | 508 / 518 | Results/Randomizer synchronization |
| `reviewSynaptosomes()` | 644 | mode routing and user validation |
| `identifyInvalidROIs()` | 714 | hard validity mask |
| `tileHasInvalidEdgePadding()` | 762 | full-tile edge-padding test |
| `edgeIsAllInvalid()` | 771 | all-channel edge check |
| `selectionHasInvalidPixels()` | 783 | measurement-region NaN/zero test |
| `automaticDiscardROIs()` | 788 | processing-time classifier and threshold application |

