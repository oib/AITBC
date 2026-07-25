import React from "react";
import { ThemeMode, useAitbcTheme } from "@aitbc/theme-provider";

const MODES: { label: string; value: ThemeMode }[] = [
  { label: "System", value: "system" },
  { label: "Light", value: "light" },
  { label: "Dark", value: "dark" },
  { label: "High contrast", value: "high-contrast" },
];

export function AppearancePanel() {
  const { preference, setMode, setReducedMotion, setHighContrast } = useAitbcTheme();

  return (
    <section aria-labelledby="appearance-heading" className="aitbc-appearance-panel">
      <h2 id="appearance-heading">Appearance</h2>

      <fieldset>
        <legend>Theme mode</legend>
        {MODES.map(({ label, value }) => (
          <label key={value} className="aitbc-radio-label">
            <input
              type="radio"
              name="aitbc-theme-mode"
              value={value}
              checked={preference.mode === value}
              onChange={() => setMode(value)}
            />
            {label}
          </label>
        ))}
      </fieldset>

      <label className="aitbc-toggle-label">
        <input
          type="checkbox"
          checked={preference.reducedMotion}
          onChange={(e) => setReducedMotion(e.target.checked)}
        />
        Reduce motion
      </label>

      <label className="aitbc-toggle-label">
        <input
          type="checkbox"
          checked={preference.highContrast}
          onChange={(e) => setHighContrast(e.target.checked)}
        />
        High contrast
      </label>
    </section>
  );
}
