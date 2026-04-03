import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { DefaultFramingMode, FaceDetectionMode, FallbackCropPosition, ProcessingProfile } from "../settings-section-types";
import { getProcessingProfilePreset, PROCESSING_PROFILE_PRESETS } from "@/lib/processing-profiles";

interface SettingsSectionVideoProps {
  isSaving: boolean;
  reviewBeforeRenderEnabled: boolean;
  transitionsEnabled: boolean;
  timelineEditorEnabled: boolean;
  defaultProcessingProfile: ProcessingProfile;
  defaultFramingMode: DefaultFramingMode;
  faceDetectionMode: FaceDetectionMode;
  fallbackCropPosition: FallbackCropPosition;
  onToggleReviewBeforeRender: () => void;
  onToggleTransitions: () => void;
  onToggleTimelineEditor: () => void;
  onDefaultProcessingProfileChange: (value: ProcessingProfile) => void;
  onDefaultFramingModeChange: (value: DefaultFramingMode) => void;
  onFaceDetectionModeChange: (value: FaceDetectionMode) => void;
  onFallbackCropPositionChange: (value: FallbackCropPosition) => void;
}

export function SettingsSectionVideo({
  isSaving,
  reviewBeforeRenderEnabled,
  transitionsEnabled,
  timelineEditorEnabled,
  defaultProcessingProfile,
  defaultFramingMode,
  faceDetectionMode,
  fallbackCropPosition,
  onToggleReviewBeforeRender,
  onToggleTransitions,
  onToggleTimelineEditor,
  onDefaultProcessingProfileChange,
  onDefaultFramingModeChange,
  onFaceDetectionModeChange,
  onFallbackCropPositionChange,
}: SettingsSectionVideoProps) {
  const selectedProfile = getProcessingProfilePreset(defaultProcessingProfile);
  return (
    <div className="space-y-4">
      <div className="space-y-3 rounded-md border border-gray-200 bg-white p-3">
        <div>
          <p className="text-sm font-medium text-black">Default processing profile</p>
          <p className="text-xs text-gray-500">
            Preset that the home page starts from when you create a new task.
          </p>
        </div>
        <Select
          value={defaultProcessingProfile}
          onValueChange={(value) => onDefaultProcessingProfileChange(value as ProcessingProfile)}
          disabled={isSaving}
        >
          <SelectTrigger className="bg-white">
            <SelectValue placeholder="Select processing profile" />
          </SelectTrigger>
          <SelectContent>
            {Object.values(PROCESSING_PROFILE_PRESETS).map((profile) => (
              <SelectItem key={profile.id} value={profile.id}>
                {profile.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-gray-500">{selectedProfile.description}</p>
      </div>
      <div className="space-y-3 rounded-md border border-gray-200 bg-white p-3">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-black">Review before render</p>
            <p className="text-xs text-gray-500">Pause after AI analysis so you can trim, reorder, and approve draft clips.</p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={reviewBeforeRenderEnabled}
            onClick={onToggleReviewBeforeRender}
            disabled={isSaving}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors disabled:opacity-50 ${
              reviewBeforeRenderEnabled ? "bg-blue-600" : "bg-gray-300"
            }`}
          >
            <span
              className={`inline-block h-5 w-5 transform rounded-full bg-white transition-transform ${
                reviewBeforeRenderEnabled ? "translate-x-5" : "translate-x-1"
              }`}
            />
          </button>
        </div>
      </div>
      <div className="space-y-3 rounded-md border border-gray-200 bg-white p-3">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-black">Enable transitions</p>
            <p className="text-xs text-gray-500">Add transition effects between consecutive generated clips.</p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={transitionsEnabled}
            onClick={onToggleTransitions}
            disabled={isSaving}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors disabled:opacity-50 ${
              transitionsEnabled ? "bg-blue-600" : "bg-gray-300"
            }`}
          >
            <span
              className={`inline-block h-5 w-5 transform rounded-full bg-white transition-transform ${
                transitionsEnabled ? "translate-x-5" : "translate-x-1"
              }`}
            />
          </button>
        </div>
      </div>
      <div className="space-y-3 rounded-md border border-gray-200 bg-white p-3">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-black">Enable timeline editor in review</p>
            <p className="text-xs text-gray-500">
              Show the source video timeline with draggable clip ranges by default for new tasks.
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={timelineEditorEnabled}
            onClick={onToggleTimelineEditor}
            disabled={isSaving}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors disabled:opacity-50 ${
              timelineEditorEnabled ? "bg-blue-600" : "bg-gray-300"
            }`}
          >
            <span
              className={`inline-block h-5 w-5 transform rounded-full bg-white transition-transform ${
                timelineEditorEnabled ? "translate-x-5" : "translate-x-1"
              }`}
            />
          </button>
        </div>
      </div>
      <div className="space-y-3 rounded-md border border-gray-200 bg-white p-3">
        <div>
          <p className="text-sm font-medium text-black">Default crop mode</p>
          <p className="text-xs text-gray-500">
            Prefill new draft clips with your preferred framing behavior. Weak or missing face targets fall back to the saved crop position.
          </p>
        </div>
        <Select value={defaultFramingMode} onValueChange={(value) => onDefaultFramingModeChange(value as DefaultFramingMode)} disabled={isSaving}>
          <SelectTrigger className="bg-white">
            <SelectValue placeholder="Select default crop mode" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="auto">Auto</SelectItem>
            <SelectItem value="prefer_face">Prefer face</SelectItem>
            <SelectItem value="fixed_position">Fixed position</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-3 rounded-md border border-gray-200 bg-white p-3">
        <div>
          <p className="text-sm font-medium text-black">Face detection mode</p>
          <p className="text-xs text-gray-500">
            Balanced is the default. More faces is more permissive for small or distant speakers.
          </p>
        </div>
        <Select value={faceDetectionMode} onValueChange={(value) => onFaceDetectionModeChange(value as FaceDetectionMode)} disabled={isSaving}>
          <SelectTrigger className="bg-white">
            <SelectValue placeholder="Select face detection mode" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="balanced">Balanced</SelectItem>
            <SelectItem value="more_faces">More faces</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-3 rounded-md border border-gray-200 bg-white p-3">
        <div>
          <p className="text-sm font-medium text-black">Fallback crop position</p>
          <p className="text-xs text-gray-500">
            Used when face-aware framing is weak or disabled. Left-center works well for solo stream layouts with the camera offset from center.
          </p>
        </div>
        <Select
          value={fallbackCropPosition}
          onValueChange={(value) => onFallbackCropPositionChange(value as FallbackCropPosition)}
          disabled={isSaving}
        >
          <SelectTrigger className="bg-white">
            <SelectValue placeholder="Select fallback crop position" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="center">Center</SelectItem>
            <SelectItem value="left_center">Left-center</SelectItem>
            <SelectItem value="right_center">Right-center</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
