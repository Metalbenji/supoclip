import { useMemo, useState } from "react";
import { AlertCircle } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { SavedWorkflow, WorkflowSelection } from "@/lib/processing-profiles";
import {
  getWorkflowSelectionDescription,
  getWorkflowSelectionLabel,
  getWorkflowSelectValue,
  matchesSavedWorkflow,
  parseWorkflowSelectValue,
  PROCESSING_PROFILE_PRESETS,
} from "@/lib/processing-profiles";

interface SettingsSectionWorkflowProps {
  isSaving: boolean;
  isLoadingWorkflows: boolean;
  savedWorkflows: SavedWorkflow[];
  selectedWorkflow: WorkflowSelection;
  workflowStatus: string | null;
  workflowError: string | null;
  reviewBeforeRenderEnabled: boolean;
  transitionsEnabled: boolean;
  timelineEditorEnabled: boolean;
  reviewAutoSelectStrongFaceEnabled: boolean;
  reviewAutoSelectStrongFaceMinScorePercent: number;
  transcriptionProvider: SavedWorkflow["transcriptionProvider"];
  whisperModelSize: SavedWorkflow["whisperModelSize"];
  defaultFramingMode: SavedWorkflow["defaultFramingMode"];
  faceDetectionMode: SavedWorkflow["faceDetectionMode"];
  fallbackCropPosition: SavedWorkflow["fallbackCropPosition"];
  faceAnchorProfile: SavedWorkflow["faceAnchorProfile"];
  onWorkflowSelectionChange: (selection: WorkflowSelection) => void;
  onSaveWorkflow: (name: string) => Promise<boolean>;
  onUpdateWorkflow: (workflowId: string) => Promise<boolean>;
  onRenameWorkflow: (workflowId: string, name: string) => Promise<boolean>;
  onDeleteWorkflow: (workflowId: string) => Promise<boolean>;
  onToggleReviewBeforeRender: () => void;
  onToggleTransitions: () => void;
  onToggleTimelineEditor: () => void;
  onToggleReviewAutoSelectStrongFace: () => void;
  onReviewAutoSelectStrongFaceMinScorePercentChange: (value: number) => void;
}

function ToggleCard(props: {
  label: string;
  description: string;
  checked: boolean;
  disabled: boolean;
  onToggle: () => void;
}) {
  const { label, description, checked, disabled, onToggle } = props;
  return (
    <div className="space-y-3 rounded-md border border-gray-200 bg-white p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-black">{label}</p>
          <p className="text-xs text-gray-500">{description}</p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={checked}
          onClick={onToggle}
          disabled={disabled}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors disabled:opacity-50 ${
            checked ? "bg-blue-600" : "bg-gray-300"
          }`}
        >
          <span
            className={`inline-block h-5 w-5 transform rounded-full bg-white transition-transform ${
              checked ? "translate-x-5" : "translate-x-1"
            }`}
          />
        </button>
      </div>
    </div>
  );
}

export function SettingsSectionWorkflow({
  isSaving,
  isLoadingWorkflows,
  savedWorkflows,
  selectedWorkflow,
  workflowStatus,
  workflowError,
  reviewBeforeRenderEnabled,
  transitionsEnabled,
  timelineEditorEnabled,
  reviewAutoSelectStrongFaceEnabled,
  reviewAutoSelectStrongFaceMinScorePercent,
  transcriptionProvider,
  whisperModelSize,
  defaultFramingMode,
  faceDetectionMode,
  fallbackCropPosition,
  faceAnchorProfile,
  onWorkflowSelectionChange,
  onSaveWorkflow,
  onUpdateWorkflow,
  onRenameWorkflow,
  onDeleteWorkflow,
  onToggleReviewBeforeRender,
  onToggleTransitions,
  onToggleTimelineEditor,
  onToggleReviewAutoSelectStrongFace,
  onReviewAutoSelectStrongFaceMinScorePercentChange,
}: SettingsSectionWorkflowProps) {
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [renameDialogOpen, setRenameDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [pendingName, setPendingName] = useState("");
  const [isSubmittingDialog, setIsSubmittingDialog] = useState(false);

  const currentValues = useMemo(
    () => ({
      reviewBeforeRenderEnabled,
      timelineEditorEnabled,
      transitionsEnabled,
      transcriptionProvider,
      whisperModelSize,
      defaultFramingMode,
      faceDetectionMode,
      fallbackCropPosition,
      faceAnchorProfile,
    }),
    [
      defaultFramingMode,
      faceAnchorProfile,
      faceDetectionMode,
      fallbackCropPosition,
      reviewBeforeRenderEnabled,
      timelineEditorEnabled,
      transcriptionProvider,
      transitionsEnabled,
      whisperModelSize,
    ],
  );
  const selectedSavedWorkflow =
    selectedWorkflow.kind === "saved"
      ? savedWorkflows.find((workflow) => workflow.id === selectedWorkflow.id) ?? null
      : null;
  const selectedSavedWorkflowChanged = selectedSavedWorkflow
    ? !matchesSavedWorkflow(currentValues, selectedSavedWorkflow)
    : false;
  const canSaveAsWorkflow = selectedWorkflow.kind !== "saved" || selectedSavedWorkflowChanged;
  const canUpdateSelectedWorkflow = Boolean(selectedSavedWorkflow && selectedSavedWorkflowChanged);

  const openSaveDialog = () => {
    setPendingName("");
    setSaveDialogOpen(true);
  };

  const openRenameDialog = () => {
    setPendingName(selectedSavedWorkflow?.name ?? "");
    setRenameDialogOpen(true);
  };

  const handleSaveWorkflow = async () => {
    setIsSubmittingDialog(true);
    const saved = await onSaveWorkflow(pendingName);
    setIsSubmittingDialog(false);
    if (saved) {
      setSaveDialogOpen(false);
      setPendingName("");
    }
  };

  const handleRenameWorkflow = async () => {
    if (!selectedSavedWorkflow) {
      return;
    }
    setIsSubmittingDialog(true);
    const renamed = await onRenameWorkflow(selectedSavedWorkflow.id, pendingName);
    setIsSubmittingDialog(false);
    if (renamed) {
      setRenameDialogOpen(false);
      setPendingName("");
    }
  };

  const handleDeleteWorkflow = async () => {
    if (!selectedSavedWorkflow) {
      return;
    }
    setIsSubmittingDialog(true);
    const deleted = await onDeleteWorkflow(selectedSavedWorkflow.id);
    setIsSubmittingDialog(false);
    if (deleted) {
      setDeleteDialogOpen(false);
    }
  };

  const handleUpdateWorkflow = async () => {
    if (!selectedSavedWorkflow) {
      return;
    }
    setIsSubmittingDialog(true);
    await onUpdateWorkflow(selectedSavedWorkflow.id);
    setIsSubmittingDialog(false);
  };

  return (
    <div className="space-y-4">
      <div className="space-y-4 rounded-md border border-gray-200 bg-white p-4">
        <div>
          <p className="text-sm font-medium text-black">Default workflow</p>
          <p className="text-xs text-gray-500">
            Workflows are shortcuts for your workflow, framing, and transcription defaults. Editing the linked fields below moves the visible state to Custom.
          </p>
        </div>

        <Select
          value={getWorkflowSelectValue(selectedWorkflow)}
          onValueChange={(value) => onWorkflowSelectionChange(parseWorkflowSelectValue(value))}
          disabled={isSaving || isLoadingWorkflows}
        >
          <SelectTrigger className="bg-white">
            <SelectValue placeholder="Select default workflow" />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectLabel>Built-in</SelectLabel>
              {Object.values(PROCESSING_PROFILE_PRESETS).map((profile) => (
                <SelectItem key={profile.id} value={`built_in:${profile.id}`}>
                  {profile.label}
                </SelectItem>
              ))}
            </SelectGroup>
            {savedWorkflows.length > 0 ? (
              <SelectGroup>
                <SelectLabel>Saved</SelectLabel>
                {savedWorkflows.map((workflow) => (
                  <SelectItem key={workflow.id} value={`saved:${workflow.id}`}>
                    {workflow.name}
                  </SelectItem>
                ))}
              </SelectGroup>
            ) : null}
            {selectedWorkflow.kind === "custom" ? (
              <SelectGroup>
                <SelectLabel>Current</SelectLabel>
                <SelectItem value="custom">Custom</SelectItem>
              </SelectGroup>
            ) : null}
          </SelectContent>
        </Select>

        <div
          className={`rounded-lg border px-4 py-3 ${
            selectedWorkflow.kind === "custom"
              ? "border-amber-500 bg-amber-100"
              : "border-dashed border-gray-300 bg-gray-50"
          }`}
        >
          <p
            className={`text-xs font-medium uppercase tracking-wide ${
              selectedWorkflow.kind === "custom" ? "text-amber-700" : "text-gray-500"
            }`}
          >
            Current default
          </p>
          <p className={`mt-1 text-sm font-semibold ${selectedWorkflow.kind === "custom" ? "text-amber-950" : "text-black"}`}>
            {getWorkflowSelectionLabel(selectedWorkflow, savedWorkflows)}
          </p>
          <p className={`mt-1 text-xs ${selectedWorkflow.kind === "custom" ? "text-amber-900" : "text-gray-600"}`}>
            {getWorkflowSelectionDescription(selectedWorkflow, savedWorkflows)}
          </p>
        </div>

        {workflowError ? (
          <Alert className="border-red-200 bg-red-50">
            <AlertCircle className="h-4 w-4 text-red-500" />
            <AlertDescription className="text-sm text-red-700">{workflowError}</AlertDescription>
          </Alert>
        ) : null}

        {workflowStatus ? (
          <Alert className="border-green-200 bg-green-50">
            <AlertDescription className="text-sm text-green-700">{workflowStatus}</AlertDescription>
          </Alert>
        ) : null}

        <div className="space-y-3 rounded-md border border-gray-200 bg-gray-50 p-4">
          <div>
            <p className="text-sm font-medium text-black">Workflow manager</p>
            <p className="text-xs text-gray-500">
              Save the current workflow, framing, and transcription bundle as a reusable workflow. Built-ins stay read-only.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" onClick={openSaveDialog} disabled={isSaving || !canSaveAsWorkflow}>
              Save as workflow
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => void handleUpdateWorkflow()}
              disabled={isSaving || isSubmittingDialog || !canUpdateSelectedWorkflow}
            >
              Update workflow
            </Button>
            <Button type="button" variant="outline" onClick={openRenameDialog} disabled={isSaving || !selectedSavedWorkflow}>
              Rename workflow
            </Button>
            <Button type="button" variant="outline" onClick={() => setDeleteDialogOpen(true)} disabled={isSaving || !selectedSavedWorkflow}>
              Delete workflow
            </Button>
          </div>
          <p className="text-xs text-gray-500">
            {selectedSavedWorkflow
              ? selectedSavedWorkflowChanged
                ? "The selected saved workflow no longer matches the fields below. Update it or save a new workflow."
                : "The fields below match the selected saved workflow."
              : selectedWorkflow.kind === "built_in"
                ? "Built-in workflows can be selected as defaults but cannot be renamed, updated, or deleted."
                : "Custom means your current defaults do not exactly match a built-in or saved workflow."}
          </p>
        </div>
      </div>

      <ToggleCard
        label="Review before render"
        description="Pause after analysis so you can trim, reorder, and approve draft clips before final renders are made."
        checked={reviewBeforeRenderEnabled}
        disabled={isSaving}
        onToggle={onToggleReviewBeforeRender}
      />

      <ToggleCard
        label="Timeline editor default"
        description="Show the source-video timeline with draggable ranges by default when review mode opens."
        checked={timelineEditorEnabled}
        disabled={isSaving}
        onToggle={onToggleTimelineEditor}
      />

      <ToggleCard
        label="Transitions"
        description="Add transition effects between consecutive generated clips."
        checked={transitionsEnabled}
        disabled={isSaving}
        onToggle={onToggleTransitions}
      />

      <div className="space-y-3 rounded-md border border-gray-200 bg-white p-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-black">Draft auto-selection</p>
            <p className="text-xs text-gray-500">
              In review mode, automatically start strong-face clips above the threshold as selected.
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={reviewAutoSelectStrongFaceEnabled}
            onClick={onToggleReviewAutoSelectStrongFace}
            disabled={isSaving}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors disabled:opacity-50 ${
              reviewAutoSelectStrongFaceEnabled ? "bg-blue-600" : "bg-gray-300"
            }`}
          >
            <span
              className={`inline-block h-5 w-5 transform rounded-full bg-white transition-transform ${
                reviewAutoSelectStrongFaceEnabled ? "translate-x-5" : "translate-x-1"
              }`}
            />
          </button>
        </div>

        {reviewAutoSelectStrongFaceEnabled ? (
          <div className="space-y-3 rounded-md border border-gray-100 bg-gray-50 p-3">
            <div className="flex items-center justify-between gap-3">
              <label className="text-sm font-medium text-black">
                Minimum review score: {reviewAutoSelectStrongFaceMinScorePercent}%
              </label>
              <Input
                type="number"
                min={0}
                max={100}
                step={1}
                value={reviewAutoSelectStrongFaceMinScorePercent}
                onChange={(event) => onReviewAutoSelectStrongFaceMinScorePercentChange(Number(event.target.value))}
                disabled={isSaving}
                className="h-8 w-24"
              />
            </div>
            <div className="px-2 pt-5">
              <Slider
                value={[reviewAutoSelectStrongFaceMinScorePercent]}
                onValueChange={(value) => onReviewAutoSelectStrongFaceMinScorePercentChange(value[0])}
                min={0}
                max={100}
                step={1}
                disabled={isSaving}
                className="w-full"
              />
            </div>
          </div>
        ) : null}
      </div>

      <AlertDialog open={saveDialogOpen} onOpenChange={setSaveDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Save Workflow</AlertDialogTitle>
            <AlertDialogDescription>
              Save the current workflow, framing, and transcription defaults as a reusable workflow.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <Input
            value={pendingName}
            onChange={(event) => setPendingName(event.target.value)}
            placeholder="Workflow name"
            disabled={isSubmittingDialog}
          />
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isSubmittingDialog}>Cancel</AlertDialogCancel>
            <Button type="button" onClick={() => void handleSaveWorkflow()} disabled={isSubmittingDialog || pendingName.trim().length === 0}>
              Save
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={renameDialogOpen} onOpenChange={setRenameDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Rename Workflow</AlertDialogTitle>
            <AlertDialogDescription>Update the display name for this saved workflow.</AlertDialogDescription>
          </AlertDialogHeader>
          <Input
            value={pendingName}
            onChange={(event) => setPendingName(event.target.value)}
            placeholder="Workflow name"
            disabled={isSubmittingDialog}
          />
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isSubmittingDialog}>Cancel</AlertDialogCancel>
            <Button type="button" onClick={() => void handleRenameWorkflow()} disabled={isSubmittingDialog || pendingName.trim().length === 0}>
              Rename
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Workflow</AlertDialogTitle>
            <AlertDialogDescription>
              Delete {selectedSavedWorkflow ? `"${selectedSavedWorkflow.name}"` : "this workflow"}? Existing tasks keep their saved workflow snapshot.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isSubmittingDialog}>Cancel</AlertDialogCancel>
            <Button type="button" variant="destructive" onClick={() => void handleDeleteWorkflow()} disabled={isSubmittingDialog || !selectedSavedWorkflow}>
              Delete
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
