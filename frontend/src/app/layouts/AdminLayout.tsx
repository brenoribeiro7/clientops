import { Outlet } from "react-router-dom";

import { NavigationLink } from "../../components/shared/NavigationLink";
import { SkipLink } from "../../components/shared/SkipLink";
import { Drawer } from "../../components/ui/Drawer";

function AdminNavigation() {
  return (
    <nav aria-label="Navegação administrativa">
      <NavigationLink to="/admin" end>
        Início
      </NavigationLink>
    </nav>
  );
}

export function AdminLayout() {
  return (
    <div className="admin-shell">
      <SkipLink />
      <aside className="admin-sidebar">
        <div className="brand">ClientOps</div>
        <AdminNavigation />
      </aside>
      <header className="mobile-header">
        <span className="brand">ClientOps</span>
        <Drawer label="Abrir menu administrativo">
          <AdminNavigation />
        </Drawer>
      </header>
      <main id="main-content" className="admin-main">
        <Outlet />
      </main>
    </div>
  );
}
