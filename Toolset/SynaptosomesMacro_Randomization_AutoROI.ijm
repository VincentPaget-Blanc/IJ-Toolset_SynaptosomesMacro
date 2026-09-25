// SynaptosomesMacro_Randomization_AutoROI — Version 13b
// Repository-facing release label; 13a was the first AutoROI iteration.
// Version 13b keeps the audited AutoROI processing logic and repository-facing version provenance.
// 25/09/2026 hotfixes: create the threshold progress Text Window before using \Update;
// restore the visible ROI Manager after the read-only threshold preflight; guard selection-dependent validity checks.

var LUTs=newArray("Green", "Magenta", "Blue");
var nLabels=2;
var in="";
var out="";
var labels=newArray();
var basename="Analysis";
var autoDiscardEnabled=false;
var autoDiscardMode="User validated";
var autoDiscardThreshold=0.90;
var hardDiscarded=newArray(); // Per-image mask: 1 = invalid (NaN/zero in a measurement region or geometric edge padding)
var thresholdProgressWindowTitle="Dataset threshold analysis progress";
var sessionParams=newArray(64, 3, 3, 5, 100, 32, 0.103, 10000, 0.217); // Session-only GUI values; initialized when this toolset is loaded
var sessionLabelNames=newArray("Label_1", "Label_2", "Label_3");
var sessionBatchPatterns=newArray("G Ex 470 Em QuadA", "R Ex 550 Em QuadA", "");
var resultsWindowWaitMs=10000; // Maximum wait for non-image table windows to be registered by Fiji
var thresholdAnalysisRequested=false; // One-shot batch preflight; never persisted across GUI reopenings unless reselected
var thresholdAnalysisCandidates=0;
var thresholdAnalysisInvalid=0;
var thresholdAnalysisSets=0;
var thresholdReviewSuggestion=0.30; // Review-oriented operating point validated on the supplied user-reviewed datasets
var thresholdAutoSafetyMargin=0.17; // Conservative margin above the current dataset median valid score
var thresholdAnalysisPerformedForRun=false; // Provenance only; does not affect processing
var thresholdAnalysisMedianForRun=NaN;
var thresholdAnalysisReviewForRun=NaN;
var thresholdAnalysisAutoForRun=NaN;


macro "Single Acquisition Action Tool - C555D31D3eD4eD5aD5eD6aD6eD7aD7eD8aD8eD91D9aD9eDa1Da2Da3DaaDaeDb2Db3DbeDc3DceCeeeD3fD4bD4fD5fD6fD7fD8fD95D9fDa5DafDbbDbfDcfCaaaD22D23D24D25D26D27D28D29D2aD2bD2cD2dD2eD32D33D34D35D36D37D38D39D3aD3bD3cD3dD4aD74Db6Db7Db9DbaDc2Dc4DcdDd3DdeC999D54D55D58D64D65D68D75D78D88D98Da8Dd4Dd5Dd6Dd7Dd8Dd9DdaDdbDdcDddCfffD2fD30D40D42D4dD50D52D5dD60D62D6dD70D72D7dD80D82D84D8dD90D9dDadDb5DbdDdfCcccD21D44D45D46D47D48D49D5bD6bD7bD85D8bD92D93D9bDa4DabDb1Db4Db8Dc5Dc6Dc7Dc8Dc9DcaDcbDccC777D41D51D56D57D59D61D66D67D69D71D76D77D79D81D86D87D89D96D97D99Da6Da7Da9"{
	prepare(true);
	saveRunParameters(true); // Final accepted GUI values, saved before any analysis processing
	process();
}

macro "Multiple Acquisitions Action Tool - C333D2fD3fD40D4fD50D5fD60D6fD70D7fD80D8fD90D93D94D9fDa0Da3Da4DafDb1Db2Db4DbfDc1Dc2DcdDd2CcccD12D35D36D37D38D39D3aD3bD41D4cD76D83D95Da5DacDb6Db7Db8Db9DbaDbbDbcDbdDbeDc0De2DedC999D23D24D25D26D27D28D29D2aD2bD2cD2dD2eD46D49D56D59D66D69D79D89D99Da2Da7DaaDabDb3Dc4Dd3Dd4Dd5Dd6Dd7Dd8Dd9DdaDdbDdcC777D31D48D4aD58D5aD68D6aD78D7aD88D8aD98D9aDc5Dc6Dc7Dc8Dc9DcaDcbDccDceCeeeD21D33D3cD3eD43D4eD51D53D5eD61D63D6eD71D73D75D7eD81D84D86D8eD91D96D9eDa6DaeDc3DdeCbbbD13D14D15D16D17D18D19D1aD1bD1cD1dD1eD1fD45D55D5cD65D6cD7cD8cD9cDa1Da8Da9Db5Dd1De3De4De5De6De7De8De9DeaDebDecC666D22D30D32D42D47D4bD52D57D5bD62D67D6bD72D77D7bD82D87D8bD92D97D9bDb0DcfDdd"{
	run("Close All");
	prepare(false);
	saveRunParameters(false); // Final accepted GUI values, saved before opening/processing the first acquisition

	channel1=getFileNamesContaining(in, labels[0]);

	for(i=0; i<channel1.length; i++){
		hasAllFiles=true;
		oldLabels=Array.copy(labels);
		firstLabel=labels[0];
		
		for(j=0; j<nLabels; j++){
			labels[2*j]=replace(channel1[i], firstLabel, labels[2*j]);
			hasAllFiles=hasAllFiles&&File.exists(in+labels[2*j]);
			if(!hasAllFiles){
				print("Missing file: "+labels[2*j]);
				break;
			}
		}
		
		if(hasAllFiles){
			for(j=0; j<nLabels; j++) open(in+labels[2*j]);
			basename=replace(channel1[i], firstLabel, "_");
			basename=substring(basename, 0, lastIndexOf(basename, "."));
			process();
		}
		labels=Array.copy(oldLabels);
	}

	poolCSVFiles(out, "CytoFile", true);
	poolCSVFiles(out, "RandomizationResults", true);

}

//-----------------------------------------
function init(){
	run("Set Measurements...", "decimal=4");
	close("Normalised_*");
	close("Gallery*");
	close("Detection*");
	close("Control*");
	close("Scatter*");
	close("Distribution*");
	roiManager("Reset");
	run("Clear Results");
	if(nImages!=0) run("Tile");
}

//-----------------------------------------
function prepare(isSingle){
	init();
	thresholdAnalysisPerformedForRun=false;
	thresholdAnalysisMedianForRun=NaN;
	thresholdAnalysisReviewForRun=NaN;
	thresholdAnalysisAutoForRun=NaN;

	nLabels=getNumber("Number of channels to analyse", nLabels);
	if(!isSingle) in=getDirectory("Where are the input files ?");
	out=getDirectory("Where to save the output files ?");

	labels=GUI(nLabels, isSingle);

	// Dataset threshold analysis is intentionally batch-only: it scans every acquisition with the
	// current GUI parameters, writes nothing, then reopens this same GUI with the suggestion.
	while(!isSingle && thresholdAnalysisRequested){
		thresholdAnalysisRequested=false;
		if(!autoDiscardEnabled){
			showMessage("Dataset threshold analysis", "Enable automatic ROI discard before requesting threshold analysis.");
		}else{
			suggestedThresholds=analyzeDatasetThreshold();
			if(!isNaN(suggestedThresholds[2])){
				thresholdAnalysisPerformedForRun=true;
				thresholdAnalysisReviewForRun=suggestedThresholds[0];
				thresholdAnalysisAutoForRun=suggestedThresholds[1];
				thresholdAnalysisMedianForRun=suggestedThresholds[2];
				if(autoDiscardMode=="Fully automatic") autoDiscardThreshold=suggestedThresholds[1];
				else autoDiscardThreshold=suggestedThresholds[0];

				message="Analyzed "+thresholdAnalysisSets+" acquisition(s), "+thresholdAnalysisCandidates+" candidate ROI(s).\n";
				message+="Hard-invalid ROI(s): "+thresholdAnalysisInvalid+".\n";
				message+="Median valid discard score: "+d2s(suggestedThresholds[2], 3)+".\n\n";
				message+="Suggested User validated threshold: "+d2s(suggestedThresholds[0], 2)+".\n";
				message+="Suggested Fully automatic threshold: "+d2s(suggestedThresholds[1], 2)+".\n\n";
				message+="The threshold field has been set for the selected mode. The GUI will reopen so it can be reviewed or edited before processing.";
				if(suggestedThresholds[2]>0.25) message+="\n\nNote: this dataset is above the median-score range directly validated so far; Fully automatic use is an extrapolation and User validated mode remains preferable.";
				if(thresholdAnalysisCandidates-thresholdAnalysisInvalid<100) message+="\n\nNote: fewer than 100 valid ROIs were available, so the dataset-level estimate is less stable.";
				showMessage("Dataset threshold analysis", message);
			}else{
				showMessage("Dataset threshold analysis", "No valid ROI scores could be collected with the current parameters. No threshold was changed.");
			}
			closeThresholdProgressWindow();
		}
		labels=GUI(nLabels, isSingle);
	}
}

//-----------------------------------------
function GUI(nLabels, isSingle){
	availableLUTs=getList("LUTs");

	if(isSingle){
		images=getImageList();
	}else{
		images=Array.copy(sessionBatchPatterns);
	}

	Dialog.create("Colocalisation on synaptosomes");
	Dialog.addMessage("---Images---");
	for(i=1; i<=nLabels; i++){
		if(isSingle){
			Dialog.addChoice("Image_for_label_"+i, images, images[i-1]);
		}else{
			Dialog.addString("FileName_contains", images[i-1]);
		}
		Dialog.addString("Name_for_label_"+i, sessionLabelNames[i-1]);
		Dialog.addChoice("LUT_for_label_"+i, availableLUTs, LUTs[(i-1)%LUTs.length]);
	}
	Dialog.addMessage("---Parameters---");
	Dialog.addNumber("Size_of_the_detection_square", sessionParams[0]);
	Dialog.addNumber("Radius_for_spots_filtering", sessionParams[1]);
	Dialog.addNumber("Noise_tolerance_for_spots_detection", sessionParams[2]);
	Dialog.addNumber("Min_size_for_spots_(pixels)", sessionParams[3]);
	Dialog.addNumber("Max_size_for_spots_(pixels)", sessionParams[4]);
	Dialog.addNumber("Size_of_the_quantification_circle_square", sessionParams[5]);
	Dialog.addNumber("Pixel_size_in_microns", sessionParams[6]);
	Dialog.addMessage("---ROI review---");
	Dialog.addCheckbox("Enable_automatic_ROI_discard", autoDiscardEnabled);
	Dialog.addChoice("Automatic_review_mode_(used_only_when_enabled)", newArray("User validated", "Fully automatic"), autoDiscardMode);
	Dialog.addNumber("Discard_score_threshold_(0-1;_used_only_when_enabled)", autoDiscardThreshold, 2, 6, "");
	if(!isSingle) Dialog.addCheckbox("Analyze_dataset_and_suggest_threshold", false);
	Dialog.addMessage("Automatic settings are used only when automatic ROI discard is enabled.\nScore >= threshold is pre-discarded; lower = more aggressive, higher = more conservative.\nROIs containing NaN/zero pixels in the quantification circle/background annulus, or all-channel zero/NaN padding on a detection-square edge, are always discarded.\nThreshold analysis (batch only) scans all acquisitions with the current parameters, writes nothing, then reopens this GUI with a suggestion.");
	Dialog.addMessage("---Randomization---");
	Dialog.addNumber("#_monte_carlo_simulations", sessionParams[7]);
	Dialog.addNumber("distance_max_colocalization_(microns)", sessionParams[8]);
	Dialog.show();

	params=newArray(2*nLabels+9);
	for(i=0; i<2*nLabels; i=i+2){
		if(isSingle){
			params[i]=Dialog.getChoice();
		}else{
			params[i]=Dialog.getString();
		}
		params[i+1]=Dialog.getString();
		if(!isSingle) sessionBatchPatterns[i/2]=params[i];
		sessionLabelNames[i/2]=params[i+1];
		LUTs[i/2]=Dialog.getChoice();
	}
	//The threshold is inserted between the 7 processing values and the 2 randomization values in the GUI,
	//so read these groups explicitly to preserve the original params[] layout used by the processing pipeline.
	for(i=2*nLabels; i<2*nLabels+7; i++) params[i]=Dialog.getNumber();
	autoDiscardThreshold=Dialog.getNumber();
	params[2*nLabels+7]=Dialog.getNumber();
	params[2*nLabels+8]=Dialog.getNumber();
	for(i=0; i<9; i++) sessionParams[i]=params[2*nLabels+i];
	autoDiscardEnabled=Dialog.getCheckbox();
	if(!isSingle) thresholdAnalysisRequested=Dialog.getCheckbox();
	else thresholdAnalysisRequested=false;
	autoDiscardMode=Dialog.getChoice();
	if(autoDiscardEnabled && (autoDiscardThreshold<0 || autoDiscardThreshold>1)) exit("Discard score threshold must be between 0 and 1.");
	
	return params;
}


//-----------------------------------------
function saveRunParameters(isSingle){
	// Audit-only CSV written once, after the final GUI is accepted and before analysis processing starts.
	// No processing parameter is modified here.
	content="Parameter,Value\n";
	content+="Macro_version,"+csvValue("13b")+"\n";
	if(isSingle) content+="Analysis_mode,"+csvValue("Single Acquisition")+"\n";
	else content+="Analysis_mode,"+csvValue("Multiple Acquisitions")+"\n";
	if(!isSingle) content+="Input_folder,"+csvValue(in)+"\n";
	content+="Output_folder,"+csvValue(out)+"\n";
	content+="Number_of_channels,"+csvValue(nLabels)+"\n";

	for(i=0; i<nLabels; i++){
		if(isSingle) content+="Channel_"+(i+1)+"_image,"+csvValue(labels[2*i])+"\n";
		else content+="Channel_"+(i+1)+"_filename_contains,"+csvValue(labels[2*i])+"\n";
		content+="Channel_"+(i+1)+"_label_name,"+csvValue(labels[2*i+1])+"\n";
		content+="Channel_"+(i+1)+"_LUT,"+csvValue(LUTs[i])+"\n";
	}

	content+="Size_of_the_detection_square,"+csvValue(labels[2*nLabels])+"\n";
	content+="Radius_for_spots_filtering,"+csvValue(labels[2*nLabels+1])+"\n";
	content+="Noise_tolerance_for_spots_detection,"+csvValue(labels[2*nLabels+2])+"\n";
	content+="Min_size_for_spots_pixels,"+csvValue(labels[2*nLabels+3])+"\n";
	content+="Max_size_for_spots_pixels,"+csvValue(labels[2*nLabels+4])+"\n";
	content+="Size_of_the_quantification_circle_square,"+csvValue(labels[2*nLabels+5])+"\n";
	content+="Pixel_size_in_microns,"+csvValue(labels[2*nLabels+6])+"\n";
	content+="Enable_automatic_ROI_discard,"+csvValue(autoDiscardEnabled)+"\n";
	content+="Automatic_review_mode,"+csvValue(autoDiscardMode)+"\n";
	content+="Discard_score_threshold,"+csvValue(autoDiscardThreshold)+"\n";
	content+="Dataset_threshold_analysis_performed,"+csvValue(thresholdAnalysisPerformedForRun)+"\n";
	if(thresholdAnalysisPerformedForRun){
		content+="Threshold_analysis_acquisitions,"+csvValue(thresholdAnalysisSets)+"\n";
		content+="Threshold_analysis_candidates,"+csvValue(thresholdAnalysisCandidates)+"\n";
		content+="Threshold_analysis_hard_invalid_ROIs,"+csvValue(thresholdAnalysisInvalid)+"\n";
		content+="Threshold_analysis_median_valid_score,"+csvValue(thresholdAnalysisMedianForRun)+"\n";
		content+="Threshold_analysis_suggested_user_validated,"+csvValue(thresholdAnalysisReviewForRun)+"\n";
		content+="Threshold_analysis_suggested_fully_automatic,"+csvValue(thresholdAnalysisAutoForRun)+"\n";
	}
	content+="Monte_carlo_simulations,"+csvValue(labels[2*nLabels+7])+"\n";
	content+="Distance_max_colocalization_microns,"+csvValue(labels[2*nLabels+8])+"\n";

	logPath=nextRunParameterLogPath();
	File.saveString(content, logPath);
	print("Run parameters saved: "+logPath);
}

//-----------------------------------------
function csvValue(value){
	text=""+value;
	text=replace(text, "\"", "\"\"");
	return "\""+text+"\"";
}

//-----------------------------------------
function nextRunParameterLogPath(){
	path=out+"Run_Parameters.csv";
	index=2;
	while(File.exists(path)){
		path=out+"Run_Parameters_"+index+".csv";
		index++;
	}
	return path;
}

//-----------------------------------------
function updateThresholdProgressWindow(progress, currentSet, totalSets, stage){
	if(progress<0) progress=0;
	if(progress>1) progress=1;
	barWidth=28;
	filled=floor(progress*barWidth+0.5);
	bar="";
	for(pb=0; pb<barWidth; pb++){
		if(pb<filled) bar+="#";
		else bar+="-";
	}
	percent=round(progress*100);
	text="Dataset threshold analysis\n\n["+bar+"] "+percent+"%\n";
	if(totalSets>0) text+="Acquisition "+currentSet+" / "+totalSets+"\n";
	text+="Stage: "+stage+"\n\nRead-only preflight: no analysis output is written.";
	progressWindow="["+thresholdProgressWindowTitle+"]";
	if(!isOpen(thresholdProgressWindowTitle))
		run("Text Window...", "name="+progressWindow+" width=52 height=7 monospaced");
	print(progressWindow, "\\Update:"+text);
}

//-----------------------------------------
function closeThresholdProgressWindow(){
	if(isOpen(thresholdProgressWindowTitle))
		print("["+thresholdProgressWindowTitle+"]", "\\Close");
}

//-----------------------------------------
function analyzeDatasetThreshold(){
	// Dry-run for Multiple Acquisitions only. Reuses the existing preprocessing/detection/Gallery
	// construction and validity geometry, but does not quantify, save, pool or randomize anything.
	baseLabels=Array.copy(labels);
	channel1=getFileNamesContaining(in, baseLabels[0]);
	allScores=newArray(0);
	thresholdAnalysisCandidates=0;
	thresholdAnalysisInvalid=0;
	thresholdAnalysisSets=0;

	totalThresholdSets=channel1.length;
	if(totalThresholdSets>0){
		showStatus("Threshold analysis: preparing 1/"+totalThresholdSets);
		showProgress(0);
		updateThresholdProgressWindow(0, 1, totalThresholdSets, "Preparing");
	}

	// Keep the dry-run ROI list off the visible Swing ROI Manager. In batch mode ImageJ
	// then uses its hidden batch RoiManager, avoiding UI list repaint races while ROIs are reset/rebuilt.
	if(isOpen("ROI Manager")) close("ROI Manager");
	setBatchMode(true);
	for(a=0; a<channel1.length; a++){
		if(totalThresholdSets>0){
			showStatus("Threshold analysis: "+(a+1)+"/"+totalThresholdSets+" - loading images");
			showProgress((a+0.05)/totalThresholdSets);
			updateThresholdProgressWindow((a+0.05)/totalThresholdSets, a+1, totalThresholdSets, "Loading images");
		}
		labels=Array.copy(baseLabels);
		hasAllFiles=true;
		firstLabel=labels[0];

		for(j=0; j<nLabels; j++){
			labels[2*j]=replace(channel1[a], firstLabel, labels[2*j]);
			if(!File.exists(in+labels[2*j])){
				hasAllFiles=false;
				print("Threshold analysis - missing file: "+labels[2*j]);
			}
		}

		if(hasAllFiles){
			for(j=0; j<nLabels; j++) open(in+labels[2*j]);
			if(totalThresholdSets>0){
				showStatus("Threshold analysis: "+(a+1)+"/"+totalThresholdSets+" - preprocessing");
				showProgress((a+0.20)/totalThresholdSets);
				updateThresholdProgressWindow((a+0.20)/totalThresholdSets, a+1, totalThresholdSets, "Preprocessing");
			}
			reduce(labels, nLabels);
			normaliseImages(labels, nLabels);
			if(totalThresholdSets>0){
				showStatus("Threshold analysis: "+(a+1)+"/"+totalThresholdSets+" - detecting ROIs");
				showProgress((a+0.45)/totalThresholdSets);
				updateThresholdProgressWindow((a+0.45)/totalThresholdSets, a+1, totalThresholdSets, "Detecting ROIs");
			}
			detectSpots(labels, nLabels);
			dimensions=overlayAndCutOut(labels, nLabels);

			if(dimensions[0]!=0 && dimensions[1]!=0){
				if(totalThresholdSets>0){
					showStatus("Threshold analysis: "+(a+1)+"/"+totalThresholdSets+" - scoring ROIs");
					showProgress((a+0.75)/totalThresholdSets);
					updateThresholdProgressWindow((a+0.75)/totalThresholdSets, a+1, totalThresholdSets, "Scoring ROIs");
				}
				thresholdAnalysisSets++;
				thresholdAnalysisCandidates+=roiManager("Count");
				generateROIs(roiManager("Count"), labels[labels.length-9], dimensions);
				identifyInvalidROIs(labels[labels.length-9], dimensions);
				for(k=0; k<hardDiscarded.length; k++) if(hardDiscarded[k]==1) thresholdAnalysisInvalid++;
				setScores=collectDiscardScores(labels[labels.length-9], dimensions);
				allScores=Array.concat(allScores, setScores);
			}

			run("Close All");
			roiManager("Reset");
			run("Clear Results");
		}
		if(totalThresholdSets>0){
			showProgress((a+1)/totalThresholdSets);
			showStatus("Threshold analysis: "+(a+1)+"/"+totalThresholdSets+" complete");
			updateThresholdProgressWindow((a+1)/totalThresholdSets, a+1, totalThresholdSets, "Acquisition complete");
		}
	}
	labels=Array.copy(baseLabels);
	setBatchMode("exit and display");

	// The threshold preflight deliberately closes the visible ROI Manager to avoid the FlatLaf
	// repaint race during repeated dry-run list mutations. Leaving batch mode discards ImageJ's
	// hidden batch RoiManager, so restore an empty visible manager before returning to the GUI.
	// The normal processing path relies on this visible manager surviving its own batch-mode
	// detection step so the detected ROI list is still available for interactive review.
	run("ROI Manager...");
	roiManager("Reset");

	if(totalThresholdSets>0) showProgress(1);

	if(allScores.length==0){
		showStatus("Threshold analysis finished: no valid ROI scores collected");
		if(totalThresholdSets>0) updateThresholdProgressWindow(1, totalThresholdSets, totalThresholdSets, "Finished - no valid ROI scores");
		return newArray(NaN, NaN, NaN);
	}

	medianScore=arrayMedian(allScores);
	reviewThreshold=thresholdReviewSuggestion;
	fullyAutomaticThreshold=medianScore+thresholdAutoSafetyMargin;
	if(fullyAutomaticThreshold<0.30) fullyAutomaticThreshold=0.30;
	if(fullyAutomaticThreshold>0.90) fullyAutomaticThreshold=0.90;

	showStatus("Threshold analysis complete: "+thresholdAnalysisSets+" acquisitions, "+allScores.length+" valid ROIs");
	if(totalThresholdSets>0) updateThresholdProgressWindow(1, totalThresholdSets, totalThresholdSets, "Complete");
	return newArray(reviewThreshold, fullyAutomaticThreshold, medianScore);
}

//-----------------------------------------
function collectDiscardScores(boxSize, dimensions){
	// Read-only counterpart of automaticDiscardROIs(): same score equation and same measurement
	// regions, but it only returns scores for valid ROIs and never changes their keep/discard state.
	selectWindow("Gallery");
	getDimensions(width, height, channels, slices, frames);
	quantSize=labels[labels.length-4];
	getPixelSize(unit, pixelWidth, pixelHeight);
	bandWidth=(boxSize/2-quantSize/2-1)*pixelWidth;
	scores=newArray(0);

	for(i=0; i<roiManager("Count"); i++){
		if(hardDiscarded[i]==0){
			xCell=i%dimensions[0];
			yCell=floor(i/dimensions[0]);
			x0=xCell*boxSize+boxSize/2-quantSize/2;
			y0=yCell*boxSize+boxSize/2-quantSize/2;
			maxLocalSNR=-1e30;
			sumBackgroundCV=0;

			for(c=1; c<=channels; c++){
				Stack.setChannel(c);
				makeOval(x0, y0, quantSize, quantSize);
				getStatistics(centerArea, centerMean);

				run("Make Band...", "band="+bandWidth);
				getStatistics(backgroundArea, backgroundMean, backgroundMin, backgroundMax, backgroundStd);

				if(backgroundStd>0) localSNR=(centerMean-backgroundMean)/backgroundStd;
				else if(centerMean>backgroundMean) localSNR=1e30;
				else localSNR=0;

				if(abs(backgroundMean)>1e-12) backgroundCV=backgroundStd/abs(backgroundMean);
				else if(backgroundStd>0) backgroundCV=1e30;
				else backgroundCV=0;

				if(localSNR>maxLocalSNR) maxLocalSNR=localSNR;
				sumBackgroundCV+=backgroundCV;
			}

			meanBackgroundCV=sumBackgroundCV/channels;
			logit=-1.4169522-0.4050303*maxLocalSNR+42.6003835*meanBackgroundCV;
			discardScore=1/(1+exp(-logit));
			scores=Array.concat(scores, discardScore);
		}
	}

	Stack.setChannel(1);
	run("Select None");
	roiManager("Deselect");
	return scores;
}

//-----------------------------------------
function arrayMedian(values){
	sorted=Array.copy(values);
	Array.sort(sorted);
	n=sorted.length;
	middle=floor(n/2);
	if(n%2==1) return sorted[middle];
	return (sorted[middle-1]+sorted[middle])/2;
}

//-----------------------------------------
function process(){
	setBatchMode(true);
	imgSize=reduce(labels, nLabels);
	normaliseImages(labels, nLabels);
	detectSpots(labels, nLabels);
	dimensions=overlayAndCutOut(labels, nLabels);
	setBatchMode("exit and display");

	if(dimensions[0]!=0 && dimensions[1]!=0){
		reviewSynaptosomes(labels[labels.length-9], dimensions);
		quantify(labels, nLabels);
		generateControlImage(labels, nLabels);
		run("Tile");
		plotData(labels, nLabels);
		saveAll(out, basename);
		exportAsFCS(labels, nLabels, out, basename);

		saveAs("Results", out+basename+"_Results.csv");

		//Keep the original Results -> Randomizer hand-off, adding only bounded synchronization.
		closeWindowIfOpen("Analysis_Results.csv");
		closeWindowIfOpen("Randomizer_Results");
		closeWindowIfOpen(basename+"_Results.csv");

		open(out+basename+"_Results.csv");
		if(!waitForWindow(basename+"_Results.csv", resultsWindowWaitMs))
			exit("The saved results table was not registered by Fiji within "+(resultsWindowWaitMs/1000)+" s:\n"+basename+"_Results.csv");
		Table.rename("Analysis_Results.csv"); //Original rename semantics: standardize the title expected by the randomization plugin.
		if(!waitForWindow("Analysis_Results.csv", resultsWindowWaitMs))
			exit("Analysis_Results.csv was not registered by Fiji within "+(resultsWindowWaitMs/1000)+" s. Randomization was not started.");
		closeWindowIfOpen(basename+"_Results.csv"); //Older Fiji versions may leave the imported table duplicated after rename.
		
		run("RandomizerColocalization ", "image_width_(microns)="+imgSize[0]+" image_height_(microns)="+imgSize[1]+" distance_max_colocalization_(microns)="+labels[2*nLabels+8]+" #_monte_carlo_simulations="+labels[2*nLabels+7]+" name_of_label_1="+labels[1]+" name_of_label_2="+labels[3]);
		
		if(!waitForWindow("Randomizer_Results", resultsWindowWaitMs))
			exit("Randomizer_Results was not registered by Fiji within "+(resultsWindowWaitMs/1000)+" s. The analysis results remain saved.");
		selectWindow("Randomizer_Results");
		saveAs("Results", out+basename+"_RandomizationResults.csv");

		closeWindowIfOpen("Randomizer_Results");
		closeWindowIfOpen("Analysis_Results.csv");

		run("Close All");
		run("Clear Results");
	}else{
		exit("No synapsome found:\nTry adapting detection parameters");
	}
}

//-----------------------------------------
function waitForWindow(title, timeoutMs){
	elapsed=0;
	while(!isOpen(title) && elapsed<timeoutMs){
		wait(100);
		elapsed+=100;
	}
	return isOpen(title);
}

//-----------------------------------------
function closeWindowIfOpen(title){
	if(isOpen(title)){
		selectWindow(title);
		run("Close");
	}
}

//-----------------------------------------
function reduce(labels, nLabels){
	for(i=0; i<2*nLabels; i=i+2){
		selectWindow(labels[i]);
		getDimensions(width, height, channels, slices, frames);
		if(slices>1){
			run("Z Project...", "projection=[Sum Slices]");
			rename("Proj");
			close(labels[i]);
			selectWindow("Proj");
			rename(labels[i]);
		}
	}

	//Returns the image's size in microns
	return newArray(width*labels[labels.length-3], height*labels[labels.length-3]);
}

//-----------------------------------------
function normaliseSingleImage(){
	run("Select None");
	run("Duplicate...", "title=Normalised_"+getTitle);
	getStatistics(area, mean, min, max, std, histogram);
	run("32-bit");
	run("Subtract...", "value="+mean);
	run("Divide...", "value="+std);
}

//-----------------------------------------
function normaliseImages(labels, nLabels){
	for(i=0; i<2*nLabels; i=i+2){
		selectWindow(labels[i]);
		normaliseSingleImage();
	}
}

//-----------------------------------------
function detectSpots(labels, nLabels){
	size=labels[2*nLabels];
	radius=labels[2*nLabels+1];
	noise=labels[2*nLabels+2];
	min=labels[2*nLabels+3];
	max=labels[2*nLabels+4];

	run("Images to Stack", "method=[Copy (center)] name=Normalised_Channels title=Normalised_ use");
	run("Z Project...", "projection=[Sum Slices]");
	rename("Normalised_Channels_Combined");
	run("Gaussian Blur...", "sigma="+radius);
	run("Median...", "radius="+radius);
	run("Find Maxima...", "noise="+noise+" output=[Point Selection]");
	Roi.getCoordinates(xpoints, ypoints);
	roiManager("Reset");
	index=1;

	for(i=0; i<xpoints.length; i++){
		doWand(xpoints[i], ypoints[i], noise, "Legacy");
		getRawStatistics(area);
		
		if(area>min && area<max){
			makeRectangle(xpoints[i]-size/2, ypoints[i]-size/2, size, size);
			Roi.setName("Detection_"+(index++));
			roiManager("Add");
		}
	}
	close("Normalised_Channels*");
}

//-----------------------------------------
function overlayAndCutOut(labels, nLabels){
	arg="";
	for(i=0; i<nLabels; i++) arg+="c"+(i+1)+"=["+labels[2*i]+"] ";
	
	run("Merge Channels...", arg+"create keep");
	rename("Composite");

	applyLUTs();

	nCol=0;
	nRows=0;

	if(roiManager("Count")!=0){
		for(i=0; i<roiManager("Count"); i++){
			selectWindow("Composite");
			roiManager("Select", i);
			run("Duplicate...", "title=Detection_"+(i+1)+" duplicate");
			if(i==0){
				rename("Detection_Stack");
			}else{
				run("Concatenate...", "  title=[Detection_Stack] image1=Detection_Stack image2=Detection_"+(i+1)+" image3=[-- None --]");
			}
		}

		nCol=floor(sqrt(roiManager("Count")));
		nRows=round(roiManager("Count")/nCol+0.5);
		run("Make Montage...", "columns="+nCol+" rows="+nRows+" scale=1");
		rename("Gallery");

		Stack.getDimensions(width, height, channels, slices, frames);
		for(i=1; i<=channels; i++){
			Stack.setChannel(i);
			run("Enhance Contrast", "saturated=0.35");
		}
	}

	close("Composite");
	close("Detection_Stack");

	return newArray(nCol, nRows);
}

//-----------------------------------------
function applyLUTs(){
	for(i=0; i<nLabels; i++){
		Stack.setChannel(i+1);
		run(LUTs[i]);
	}
}

//-----------------------------------------
function reviewSynaptosomes(size, dimensions){
	leftButton=16;
	rightButton=4;
	shift=1;
	ctrl=2; 
	alt=8;
	x2=-1;
	y2=-1;
	z2=-1;
	flags2=-1;

	nCol=dimensions[0];
	nRows=dimensions[1];

	generateROIs(roiManager("Count"), size, dimensions);
	identifyInvalidROIs(size, dimensions); // Mandatory validity check, independent of automatic ROI review

	if(autoDiscardEnabled){
		automaticDiscardROIs(size, dimensions, autoDiscardThreshold);
		if(autoDiscardMode=="Fully automatic"){
			showStatus("Automatic ROI selection validated");
		}else{
			selectWindow("Gallery");
			updateDisplay();
			wait(100); // Allow the ROI overlay repaint to complete before opening the validation dialog.
			validateAutomaticSelection=getBoolean("Automatic ROI selection\n\nGreen = kept, red = discarded.", "Validate and continue", "Edit selection");
			if(!validateAutomaticSelection) manualReviewLoop(size, dimensions, leftButton);
		}
	}else{
		manualReviewLoop(size, dimensions, leftButton);
	}

	selectWindow("Gallery");
	run("Select None");
	roiManager("Deselect");
	roiManager("Show All without labels");
	roiManager("Remove Channel Info");
	roiManager("Remove Slice Info");
	roiManager("Remove Frame Info");
	updateDisplay();
}

//-----------------------------------------
function manualReviewLoop(size, dimensions, leftButton){
	x2=-1;
	y2=-1;
	z2=-1;
	flags2=-1;

	selectWindow("Gallery");
	updateDisplay();
	setTool("rectangle");
	getCursorLoc(x, y, z, modifiers);
	while (!isKeyDown("space")){
		showStatus("Click on the synaptosome to change its status, then press space to validate");
		getCursorLoc(x, y, z, flags);
		if (x!=x2 || y!=y2 || z!=z2 || flags!=flags2) {
			if(flags& leftButton!=0) updateRoiStatus(x, y, size, dimensions);
		}
		x2=x; y2=y; z2=z; flags2=flags;
		wait(100);
	}
}

//-----------------------------------------
function identifyInvalidROIs(boxSize, dimensions){
	// Hard validity rule: retain the existing measurement-region NaN/zero check and additionally
	// reject geometric crop padding when an outer edge of the full detection square is entirely
	// NaN/zero across all measured channels. This catches edge padding that sits outside the
	// quantification circle/background annulus without making isolated zero pixels elsewhere fatal.
	selectWindow("Gallery");
	getDimensions(width, height, channels, slices, frames);
	quantSize=labels[labels.length-4];
	getPixelSize(unit, pixelWidth, pixelHeight);
	bandWidth=(boxSize/2-quantSize/2-1)*pixelWidth;
	hardDiscarded=newArray(roiManager("Count"));

	for(i=0; i<roiManager("Count"); i++){
		xCell=i%dimensions[0];
		yCell=floor(i/dimensions[0]);
		tileX=xCell*boxSize;
		tileY=yCell*boxSize;
		x0=tileX+boxSize/2-quantSize/2;
		y0=tileY+boxSize/2-quantSize/2;
		isInvalid=tileHasInvalidEdgePadding(tileX, tileY, boxSize, channels);

		// ImageJ macro logical AND evaluates both operands. Keep the selection-dependent
		// check inside this block so it is never called when edge padding already made
		// the candidate invalid and no oval selection was created.
		if(!isInvalid){
			makeOval(x0, y0, quantSize, quantSize);
			if(selectionHasInvalidPixels(channels)) isInvalid=true;
		}

		if(!isInvalid){
			run("Make Band...", "band="+bandWidth);
			if(selectionHasInvalidPixels(channels)) isInvalid=true;
		}

		if(isInvalid){
			hardDiscarded[i]=1;
			setRoiDiscarded(i, boxSize, dimensions);
		}
	}

	Stack.setChannel(1);
	run("Select None");
	roiManager("Deselect");
	roiManager("Show All without labels");
	updateDisplay();
}

//-----------------------------------------
function tileHasInvalidEdgePadding(x0, y0, boxSize, channels){
	if(edgeIsAllInvalid(x0, y0, 1, 0, boxSize, channels)) return true;
	if(edgeIsAllInvalid(x0, y0+boxSize-1, 1, 0, boxSize, channels)) return true;
	if(edgeIsAllInvalid(x0, y0, 0, 1, boxSize, channels)) return true;
	if(edgeIsAllInvalid(x0+boxSize-1, y0, 0, 1, boxSize, channels)) return true;
	return false;
}

//-----------------------------------------
function edgeIsAllInvalid(x0, y0, dx, dy, nPixels, channels){
	for(cPad=1; cPad<=channels; cPad++){
		Stack.setChannel(cPad);
		for(pPad=0; pPad<nPixels; pPad++){
			value=getPixel(x0+pPad*dx, y0+pPad*dy);
			if(!isNaN(value) && value!=0) return false;
		}
	}
	return true;
}

//-----------------------------------------
function selectionHasInvalidPixels(channels){
	Roi.getContainedPoints(xPoints, yPoints);

	for(cCheck=1; cCheck<=channels; cCheck++){
		Stack.setChannel(cCheck);
		for(p=0; p<xPoints.length; p++){
			value=getPixel(xPoints[p], yPoints[p]);
			if(isNaN(value)) return true;
			if(value==0) return true;
		}
	}
	return false;
}

//-----------------------------------------
function automaticDiscardROIs(boxSize, dimensions, threshold){
	// Calibrated from the supplied manual analyses. The score is symmetric across channels and
	// uses only the existing quantification circle and local background annulus on the Gallery.
	// logit(discardScore) = -1.4169522 - 0.4050303*maxLocalSNR + 42.6003835*meanBackgroundCV
	selectWindow("Gallery");
	getDimensions(width, height, channels, slices, frames);
	quantSize=labels[labels.length-4];
	getPixelSize(unit, pixelWidth, pixelHeight);
	bandWidth=(boxSize/2-quantSize/2-1)*pixelWidth;

	for(i=0; i<roiManager("Count"); i++){
		if(hardDiscarded[i]==0){
			xCell=i%dimensions[0];
			yCell=floor(i/dimensions[0]);
			x0=xCell*boxSize+boxSize/2-quantSize/2;
			y0=yCell*boxSize+boxSize/2-quantSize/2;
			maxLocalSNR=-1e30;
			sumBackgroundCV=0;

			for(c=1; c<=channels; c++){
				Stack.setChannel(c);
				makeOval(x0, y0, quantSize, quantSize);
				getStatistics(centerArea, centerMean);

				run("Make Band...", "band="+bandWidth);
				getStatistics(backgroundArea, backgroundMean, backgroundMin, backgroundMax, backgroundStd);

				if(backgroundStd>0) localSNR=(centerMean-backgroundMean)/backgroundStd;
				else if(centerMean>backgroundMean) localSNR=1e30;
				else localSNR=0;

				if(abs(backgroundMean)>1e-12) backgroundCV=backgroundStd/abs(backgroundMean);
				else if(backgroundStd>0) backgroundCV=1e30;
				else backgroundCV=0;

				if(localSNR>maxLocalSNR) maxLocalSNR=localSNR;
				sumBackgroundCV+=backgroundCV;
			}

			meanBackgroundCV=sumBackgroundCV/channels;
			logit=-1.4169522-0.4050303*maxLocalSNR+42.6003835*meanBackgroundCV;
			discardScore=1/(1+exp(-logit));
			if(discardScore>=threshold) setRoiDiscarded(i, boxSize, dimensions);
		}
	}

	Stack.setChannel(1);
	run("Select None");
	roiManager("Deselect");
	roiManager("Show All without labels");
	updateDisplay();
}

//-----------------------------------------
function setRoiDiscarded(index, boxSize, dimensions){
	xCell=index%dimensions[0];
	yCell=floor(index/dimensions[0]);
	x1=xCell*boxSize;
	x2=(xCell+1)*boxSize;
	y1=yCell*boxSize;
	y2=(yCell+1)*boxSize;

	roiManager("Select", index);
	xCoord=newArray(x1, x2, x2, x1, x1, x2, x1, x2);
	yCoord=newArray(y1, y1, y2, y2, y1, y2, y2, y1);
	makeSelection("polygon", xCoord, yCoord);
	Roi.setStrokeColor("red");
	roiManager("Update");
	// roiManager("Update") associates the replacement ROI with the current hyperstack position.
	// Match the original manual-review path so auto-discarded ROIs remain visible on every Gallery channel.
	roiManager("Remove Channel Info");
	roiManager("Remove Slice Info");
	roiManager("Remove Frame Info");
}

//-----------------------------------------
function generateROIs(nRois, size, dimensions){
	roiManager("Reset");

	nCol=dimensions[0];
	
	nRows=nRois/nCol;
	index=0;

	for(j=0; j<nRows; j++){
		for(i=0; i<nCol; i++){
			makeOval(i*size, j*size, size, size);
			Roi.setStrokeColor("green");
			Roi.setName("Detection_"+(index+1));
			roiManager("Add");
			index++;
			if(index>nRois-1){
				i=nCol;
				j=nRows;
			}
		}
	}
	roiManager("Deselect");
	roiManager("Show All without labels");
	roiManager("Remove Channel Info");
	roiManager("Remove Slice Info");
	roiManager("Remove Frame Info");
}

//-----------------------------------------
function updateRoiStatus(x, y, boxSize, dimensions){
	x=floor(x/boxSize);
	y=floor(y/boxSize);
	index=x+y*dimensions[0];

	if(index<roiManager("Count")){
		if(index<hardDiscarded.length){
			if(hardDiscarded[index]==1){
				showStatus("ROI contains invalid measurement pixels or geometric edge padding and is always discarded");
				return;
			}
		}

		roiManager("Select", index);
		color=Roi.getStrokeColor;

		if(color=="yellow" || color=="red"){
			makeOval(x*boxSize, y*boxSize, boxSize, boxSize);
			Roi.setStrokeColor("green");
			roiManager("Update");
		}

		if(color=="green"){
			x1=x*boxSize;
			x2=(x+1)*boxSize;
			y1=y*boxSize;
			y2=(y+1)*boxSize;

			xCoord=newArray(x1, x2, x2, x1, x1, x2, x1, x2);
			yCoord=newArray(y1, y1, y2, y2, y1, y2, y2, y1);
			makeSelection("polygon", xCoord, yCoord);
			Roi.setStrokeColor("red");
			roiManager("Update");
		}
		run("Select None");
		roiManager("Deselect");
		roiManager("Show All without labels");
		roiManager("Remove Channel Info");
		roiManager("Remove Slice Info");
		roiManager("Remove Frame Info");
	}
}

//-----------------------------------------
function quantify(labels, nLabels){
	run("Clear Results");
	getDimensions(width, height, channels, slices, frames);
	size=labels[labels.length-4];
	pixelSize=labels[labels.length-3];
	
	for(i=0; i<roiManager("Count"); i++){
		roiManager("Select", i);
		name=Roi.getName;
		
		if(Roi.getStrokeColor=="green"){
			Roi.getBounds(xRoi, yRoi, widthRoi, heightRoi);
			
			lineNb=nResults;
			data=newArray(channels*2);
			index=0;
			
			getPixelSize(unit, pixelWidth, pixelHeight);

			//Get raw data
			for(j=1; j<=channels; j++){
				Stack.setChannel(j);
				makeOval(xRoi+widthRoi/2-size/2, yRoi+widthRoi/2-size/2, size, size);		

				List.setMeasurements;
				x=List.getValue("XM");
				y=List.getValue("YM");
				intensity=List.getValue("RawIntDen");
				area=List.getValue("Area");

				setResult("Label", lineNb, replace(name, "Detection_", ""));
				setResult("X_"+labels[(j-1)*2+1]+"_microns", lineNb, x); //In units
				setResult("Y_"+labels[(j-1)*2+1]+"_microns", lineNb, y); //In units
				setResult("Intensity_"+labels[(j-1)*2+1], lineNb, intensity);

				data[index++]=x;
				data[index++]=y;

				run("Make Band...", "band="+(widthRoi/2-size/2-1)*pixelWidth);
				List.setMeasurements;
				intensityBkgd=List.getValue("RawIntDen");
				areaBkgd=List.getValue("Area");
				intensityBkgd=intensityBkgd*area/areaBkgd;
				intensityBkgdCorr=intensity-intensityBkgd;
				
				setResult("Bkgd_Intensity_"+labels[(j-1)*2+1], lineNb, intensityBkgd);
				setResult("Bkgd_Corr_Intensity_"+labels[(j-1)*2+1], lineNb, intensityBkgdCorr);
			}

			for(j=1; j<=channels; j++){
				for(k=1; k<=channels; k++){
					if(k>j){
						x1=data[(j-1)*2];
						y1=data[(j-1)*2+1];
						x2=data[(k-1)*2];
						y2=data[(k-1)*2+1];

						distance=sqrt((x2-x1)*(x2-x1)+(y2-y1)*(y2-y1)); //No need to calibrate as the coordinates are calibrated
						setResult("Distance_"+labels[(j-1)*2+1]+"-"+labels[(k-1)*2+1]+"_microns", lineNb, distance);
					}
				}
			}
		}
	}
}

//-----------------------------------------
function generateControlImage(labels, nLabels){
	getDimensions(width, height, channels, slices, frames);
	newImage("Control", "16-bit composite-mode", width, height, channels, slices, frames);
	applyLUTs();
	setColor("white");
	size=labels[2*nLabels+1];

	for(i=0; i<nLabels; i++){
		Stack.setChannel(i+1);
		x=getColumnResults("X_"+labels[i*2+1]);
		y=getColumnResults("Y_"+labels[i*2+1]);
		for(j=0; j<x.length; j++) drawOval(x[j]-size/2, y[j]-size/2, size, size);
	}
	roiManager("Show All");
}

//-----------------------------------------
function plotData(labels, nLabels){
	for(i=0; i<nLabels; i++){
		for(j=0; j<nLabels; j++){
			if(j>i){
				xIntensity=getColumnResults("Intensity_"+labels[i*2+1]);
				yIntensity=getColumnResults("Intensity_"+labels[j*2+1]);
				Plot.create("Scatter Plot Raw Intensities "+labels[i*2+1]+" vs "+labels[j*2+1], "Intensity_"+labels[i*2+1], "Intensity_"+labels[j*2+1]);
				Plot.add("circles", xIntensity, yIntensity);
				Plot.show();

				xIntensity=getColumnResults("Bkgd_Corr_Intensity_"+labels[i*2+1]);
				yIntensity=getColumnResults("Bkgd_Corr_Intensity_"+labels[j*2+1]);
				Plot.create("Scatter Plot Bkgd corrected Intensities "+labels[i*2+1]+" vs "+labels[j*2+1], "Intensity_"+labels[i*2+1], "Intensity_"+labels[j*2+1]);
				Plot.add("circles", xIntensity, yIntensity);
				Plot.show();

				distances=getColumnResults("Distance_"+labels[i*2+1]+"-"+labels[j*2+1]+"_microns");
				xDistances=getHistogramX(distances, 128);
				yDistances=getHistogramY(distances, 128);
				Plot.create("Distribution distances "+labels[i*2+1]+" vs "+labels[j*2+1], "Distance", "Frequency", xDistances, yDistances);
				Plot.show();
			}
		}
	}
}



//-----------------------------------------
function getColumnResults(title){
	col=newArray(nResults);
	for(i=0; i<nResults; i++) col[i]=getResult(title, i);

	return col;
}

//-----------------------------------------
function getHistogramX(data, nBins){
	Array.getStatistics(data, min, max, mean, stdDev);
	histo=newArray(nBins+1);
	for(i=0; i<histo.length; i++) histo[i]=min+i*(max-min)/(nBins-1);

	return histo;
}

//-----------------------------------------
function getHistogramY(data, nBins){
	Array.getStatistics(data, min, max, mean, stdDev);
	histo=newArray(nBins+1);
	for(i=0; i<data.length; i++){
		position=(data[i]-min)/((max-min)/(nBins-1));
		histo[position]++;
	}

	return histo;
}

//-----------------------------------------
function exportAsFCS(labels, nLabels, out, basename){
	f=File.open(out+basename+"_CytoFile.txt");

	line="Label";
	for(j=0; j<nLabels; j++){
		line+=",Intensity_"+labels[j*2+1];
		line+=",Bkgd_Intensity_"+labels[j*2+1];
		line+=",Bkgd_Corr_Intensity_"+labels[j*2+1];
	}

	for(j=0; j<nLabels; j++){
		for(k=0; k<nLabels; k++){
			if(k>j) line+=",Distance_"+labels[j*2+1]+"-"+labels[k*2+1]+"_microns";
		}
	}
	
	print(f, line);

	for(i=0; i<nResults; i++){
		line=getResultString("Label", i);
		for(j=0; j<nLabels; j++){
			line+=","+round(getResult("Intensity_"+labels[j*2+1], i));
			line+=","+round(getResult("Bkgd_Intensity_"+labels[j*2+1], i));
			line+=","+round(getResult("Bkgd_Corr_Intensity_"+labels[j*2+1], i));
		}

		for(j=0; j<nLabels; j++){
			for(k=0; k<nLabels; k++){
				if(k>j) line+=","+getResult("Distance_"+labels[j*2+1]+"-"+labels[k*2+1]+"_microns", i);
			}
		}
		print(f, line);
	}
	File.close(f);
	result=File.rename(out+basename+"_CytoFile.txt", out+basename+"_CytoFile.csv");
}

//-----------------------------------------
function saveAll(dir, basename){
	format="ZIP";
	
	for(i=3; i<nImages; i++){
		selectImage(i);
		if(i>4) format="JPEG";
		saveAs(format, dir+basename+"_"+getTitle());
	}

	if(roiManager("Count")>0) roiManager("Save", dir+basename+"_RoiSet.zip");
}

//-----------------------------------------
function poolCSVFiles(dir, nameElement, hasHeader){
	csv=getFileNamesContaining(dir, nameElement);
	filesToPool=newArray(0);
	for(i=0; i<csv.length; i++) if(indexOf(csv[i], "_Pooled_")==-1) filesToPool=Array.concat(filesToPool, csv[i]);

	if(filesToPool.length>0){
		content=File.openAsString(dir+filesToPool[0]);
		for(i=1; i<filesToPool.length; i++){
			toPush=File.openAsString(dir+filesToPool[i]);
			if(hasHeader) toPush=substring(toPush, indexOf(toPush, "\n"));
			content+=toPush;
		}
		content=replace(content, "\n\n", "\n"); //To remove extra double carriage returns
		pooledPrefix=getCommonOutputPrefix(filesToPool, "_"+nameElement+".csv");
		if(lengthOf(pooledPrefix)>0) pooledName=pooledPrefix+"_Pooled_"+nameElement+".csv";
		else pooledName="_Pooled_"+nameElement+".csv";
		result=File.saveString(content, dir+pooledName);
	}
}

//-----------------------------------------
function getCommonOutputPrefix(files, suffix){
	prefix=replace(files[0], suffix, "");

	for(i=1; i<files.length; i++){
		current=replace(files[i], suffix, "");
		maxLength=minOf(lengthOf(prefix), lengthOf(current));
		j=0;
		while(j<maxLength){
			if(substring(prefix, j, j+1)==substring(current, j, j+1)) j++;
			else maxLength=j;
		}
		prefix=substring(prefix, 0, j);
	}

	trimTrailingUnderscores=true;
	while(lengthOf(prefix)>0 && trimTrailingUnderscores){
		if(substring(prefix, lengthOf(prefix)-1, lengthOf(prefix))=="_") prefix=substring(prefix, 0, lengthOf(prefix)-1);
		else trimTrailingUnderscores=false;
	}
	return prefix;
}


//-----------------------------------------
function getImageList(){
	images=newArray(nImages);
	for(i=0; i<nImages; i++){
		selectImage(i+1);
		images[i]=getTitle();
	}
	return images;
}

//-----------------------------------------
function getFileNamesContaining(dir, part){
	tmp=getFileList(dir);
	filesList=newArray(0);

	for(i=0; i<tmp.length; i++) if(indexOf(tmp[i], part)!=-1) filesList=Array.concat(filesList, tmp[i]);

	return filesList;
}