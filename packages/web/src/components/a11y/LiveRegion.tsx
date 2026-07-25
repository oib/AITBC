import React from "react";

export interface LiveRegionProps {
  id?: string;
  children?: React.ReactNode;
  politeness?: "polite" | "assertive" | "off";
}

export function LiveRegion({
  id = "aitbc-live-region",
  children,
  politeness = "polite",
}: LiveRegionProps) {
  return (
    <div id={id} aria-live={politeness} aria-atomic="true" className="aitbc-live-region sr-only">
      {children}
    </div>
  );
}
