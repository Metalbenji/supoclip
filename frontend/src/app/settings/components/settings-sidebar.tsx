import type { SettingsSection } from "../settings-section-types";

interface SidebarSection {
  id: SettingsSection;
  label: string;
  description: string;
}

interface SettingsSidebarProps {
  sections: SidebarSection[];
  activeSection: SettingsSection;
  isSaving: boolean;
  onSectionSelect: (section: SettingsSection) => void;
}

export function SettingsSidebar({ sections, activeSection, isSaving, onSectionSelect }: SettingsSidebarProps) {
  return (
    <aside className="hidden md:block">
      <div className="sticky top-6 space-y-2 rounded-lg border border-gray-200 bg-white p-3">
        {sections.map((section) => {
          const isActive = section.id === activeSection;
          return (
            <button
              key={section.id}
              type="button"
              disabled={isSaving}
              onClick={() => onSectionSelect(section.id)}
              className={`w-full rounded-md border px-3 py-2 text-left transition-colors disabled:opacity-60 ${
                isActive
                  ? "border-[#1C1917] bg-[#1C1917] text-white"
                  : "border-transparent bg-gray-50 text-black hover:border-gray-300 hover:bg-white"
              }`}
            >
              <p className="text-sm font-semibold">{section.label}</p>
              <p className={`text-xs ${isActive ? "text-gray-200" : "text-gray-500"}`}>{section.description}</p>
            </button>
          );
        })}
      </div>
    </aside>
  );
}
