import { NavLink, type NavLinkProps } from "react-router-dom";

import { cn } from "../../lib/cn";

export function NavigationLink({ className, ...props }: NavLinkProps) {
  return (
    <NavLink
      className={({ isActive }) =>
        cn("navigation-link", isActive && "navigation-link--active", className)
      }
      {...props}
    />
  );
}
