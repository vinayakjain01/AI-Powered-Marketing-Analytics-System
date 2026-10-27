import { useEffect, useState } from "react";
import { BarChart3, Database, MessageSquareText, TrendingUp } from "lucide-react";
import Ask from "./pages/Ask";
import Dashboard from "./pages/Dashboard";
import Schema from "./pages/Schema";

const PAGES = [
  { id: "dashboard", label: "Dashboard", icon: BarChart3, view: Dashboard },
  { id: "ask", label: "Ask AI", icon: MessageSquareText, view: Ask },
  { id: "schema", label: "Data", icon: Database, view: Schema },
] as const;
type PageId = (typeof PAGES)[number]["id"];

function fromHash(): PageId {
  const id = window.location.hash.replace("#/", "");
  return PAGES.some((p) => p.id === id) ? (id as PageId) : "dashboard";
}

export default function App() {
  const [page, setPage] = useState<PageId>(fromHash);
  useEffect(() => {
    const on = () => setPage(fromHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const Current = PAGES.find((p) => p.id === page)!.view;

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand"><span className="brand-mark"><TrendingUp size={18} aria-hidden /></span>Marketing Insights</div>
        <nav className="tabs" aria-label="Main">
          {PAGES.map(({ id, label, icon: Icon }) => (
            <button key={id} className="tab" aria-current={page === id ? "page" : undefined}
              onClick={() => { window.location.hash = `#/${id}`; }}>
              <Icon size={16} aria-hidden />{label}
            </button>
          ))}
        </nav>
      </header>
      <main><Current /></main>
    </div>
  );
}
