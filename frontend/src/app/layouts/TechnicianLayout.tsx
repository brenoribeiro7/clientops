import { CalendarDays, UserRound } from "lucide-react";
import { Outlet } from "react-router-dom";

import { NavigationLink } from "../../components/shared/NavigationLink";
import { SkipLink } from "../../components/shared/SkipLink";

export function TechnicianLayout() {
  return (
    <div className="technician-shell">
      <SkipLink />
      <header className="technician-header">
        <span className="brand">ClientOps</span>
        <span className="role-label">Técnico</span>
      </header>
      <main id="main-content" className="technician-main">
        <Outlet />
      </main>
      <nav className="technician-nav" aria-label="Navegação do técnico">
        <NavigationLink to="/tech/today">
          <CalendarDays aria-hidden="true" size={20} />
          Hoje
        </NavigationLink>
        <NavigationLink to="/tech/account">
          <UserRound aria-hidden="true" size={20} />
          Conta
        </NavigationLink>
      </nav>
    </div>
  );
}
