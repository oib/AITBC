import React from "react";

export interface SkipLinkProps {
  targetId?: string;
  label?: string;
}

export function SkipLink({ targetId = "main-content", label = "Skip to main content" }: SkipLinkProps) {
  return (
    <a href={`#${targetId}`} className="aitbc-skip-link skip-link">
      {label}
    </a>
  );
}
