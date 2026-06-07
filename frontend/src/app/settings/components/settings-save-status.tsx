import { AlertCircle, CheckCircle, CircleDot, Loader2 } from "lucide-react";

interface SettingsSaveStatusProps {
  isDirty: boolean;
  isSaving: boolean;
  saveError: string | null;
}

export function SettingsSaveStatus({ isDirty, isSaving, saveError }: SettingsSaveStatusProps) {
  if (isSaving) {
    return (
      <div className="inline-flex items-center gap-2 rounded-md border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        <span>Saving...</span>
      </div>
    );
  }

  if (saveError) {
    return (
      <div className="inline-flex items-center gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-700">
        <AlertCircle className="h-3.5 w-3.5" />
        <span>Error</span>
      </div>
    );
  }

  if (isDirty) {
    return (
      <div className="inline-flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700">
        <CircleDot className="h-3.5 w-3.5" />
        <span>Unsaved</span>
      </div>
    );
  }

  return (
    <div className="inline-flex items-center gap-2 rounded-md border border-green-200 bg-green-50 px-3 py-1.5 text-xs font-medium text-green-700">
      <CheckCircle className="h-3.5 w-3.5" />
      <span>Saved</span>
    </div>
  );
}
