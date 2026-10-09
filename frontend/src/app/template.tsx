// A template re-mounts on every route change, so the page eases in each time.
export default function Template({ children }: { children: React.ReactNode }) {
  return <div className="page-enter">{children}</div>;
}
