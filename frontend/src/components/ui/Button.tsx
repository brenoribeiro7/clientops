import { forwardRef, type ButtonHTMLAttributes } from "react";

import { cn } from "../../lib/cn";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary";
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, type = "button", variant = "primary", ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      className={cn("button", variant === "secondary" && "button--secondary", className)}
      type={type}
      {...props}
    />
  );
});
