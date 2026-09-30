import { Outlet } from "react-router-dom";

import { SkipLink } from "../../components/shared/SkipLink";

export function PublicLayout() {
  return (
    <div className="public-shell">
      <SkipLink />
      <header className="public-header">
        <span className="brand">ClientOps</span>
      </header>
      <main id="main-content" className="public-main">
        <Outlet />
      </main>
    </div>
  );
}
