import React from "react";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger";
}

export function Button({ variant = "primary", className = "", ...props }: ButtonProps) {
  const variantClass = `aitbc-button--${variant}`;
  return <button className={`aitbc-button ${variantClass} ${className}`.trim()} {...props} />;
}
