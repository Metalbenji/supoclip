import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { OUTPUT_ASPECT_RATIO_OPTIONS } from "@/lib/output-aspect-ratios";
import type {
  DefaultFramingMode,
  FaceAnchorProfile,
  FaceDetectionMode,
  FallbackCropPosition,
  OutputAspectRatio,
} from "../settings-section-types";

interface SettingsSectionFramingProps {
  isSaving: boolean;
  defaultFramingMode: DefaultFramingMode;
  faceDetectionMode: FaceDetectionMode;
  fallbackCropPosition: FallbackCropPosition;
  faceAnchorProfile: FaceAnchorProfile;
  defaultOutputAspectRatio: OutputAspectRatio;
  onDefaultFramingModeChange: (value: DefaultFramingMode) => void;
  onFaceDetectionModeChange: (value: FaceDetectionMode) => void;
  onFallbackCropPositionChange: (value: FallbackCropPosition) => void;
  onFaceAnchorProfileChange: (value: FaceAnchorProfile) => void;
  onDefaultOutputAspectRatioChange: (value: OutputAspectRatio) => void;
}

export function SettingsSectionFraming({
  isSaving,
  defaultFramingMode,
  faceDetectionMode,
  fallbackCropPosition,
  faceAnchorProfile,
  defaultOutputAspectRatio,
  onDefaultFramingModeChange,
  onFaceDetectionModeChange,
  onFallbackCropPositionChange,
  onFaceAnchorProfileChange,
  onDefaultOutputAspectRatioChange,
}: SettingsSectionFramingProps) {
  return (
    <div className="space-y-4">
      <div className="space-y-3 rounded-md border border-gray-200 bg-white p-4">
        <div>
          <p className="text-sm font-medium text-black">Output format</p>
          <p className="text-xs text-gray-500">
            Choose the default render aspect ratio for new tasks. Auto keeps the source video shape.
          </p>
        </div>
        <Select
          value={defaultOutputAspectRatio}
          onValueChange={(value) => onDefaultOutputAspectRatioChange(value as OutputAspectRatio)}
          disabled={isSaving}
        >
          <SelectTrigger className="bg-white">
            <SelectValue placeholder="Select output format" />
          </SelectTrigger>
          <SelectContent>
            {OUTPUT_ASPECT_RATIO_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label} · {option.description}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-3 rounded-md border border-gray-200 bg-white p-4">
        <div>
          <p className="text-sm font-medium text-black">Default crop mode</p>
          <p className="text-xs text-gray-500">
            Prefill new draft clips with your preferred framing behavior. Weak or missing face targets fall back to the saved crop position.
          </p>
        </div>
        <Select
          value={defaultFramingMode}
          onValueChange={(value) => onDefaultFramingModeChange(value as DefaultFramingMode)}
          disabled={isSaving}
        >
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

      <div className="space-y-3 rounded-md border border-gray-200 bg-white p-4">
        <div>
          <p className="text-sm font-medium text-black">Face detection mode</p>
          <p className="text-xs text-gray-500">
            Balanced is the default. More faces is more permissive for small or distant speakers.
          </p>
        </div>
        <Select
          value={faceDetectionMode}
          onValueChange={(value) => onFaceDetectionModeChange(value as FaceDetectionMode)}
          disabled={isSaving}
        >
          <SelectTrigger className="bg-white">
            <SelectValue placeholder="Select face detection mode" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="balanced">Balanced</SelectItem>
            <SelectItem value="more_faces">More faces</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-3 rounded-md border border-gray-200 bg-white p-4">
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

      <div className="space-y-3 rounded-md border border-gray-200 bg-white p-4">
        <div>
          <p className="text-sm font-medium text-black">Face layout benchmark</p>
          <p className="text-xs text-gray-500">
            Tells face scoring where a good face track usually lives. Use left-or-center for streams where your camera is mostly on the left and sometimes centered.
          </p>
        </div>
        <Select
          value={faceAnchorProfile}
          onValueChange={(value) => onFaceAnchorProfileChange(value as FaceAnchorProfile)}
          disabled={isSaving}
        >
          <SelectTrigger className="bg-white">
            <SelectValue placeholder="Select face layout benchmark" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="auto">Auto</SelectItem>
            <SelectItem value="left_or_center">Left or center</SelectItem>
            <SelectItem value="left_only">Left only</SelectItem>
            <SelectItem value="center_only">Center only</SelectItem>
            <SelectItem value="right_or_center">Right or center</SelectItem>
            <SelectItem value="right_only">Right only</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
