import Link from "next/link";

const GITHUB_URL = "https://github.com/shreyeahhhh/EIDOS---Execution-Intelligence-Dynamic-Orchestration-System";

const PRODUCT_LINKS = [
  { href: "/#product", label: "Product" },
  { href: "/#how-it-works", label: "How it works" },
  { href: "/#architecture", label: "Architecture" },
];

export function SiteFooter() {
  return (
    <footer className="border-t border-border">
      <div className="mx-auto max-w-6xl px-6 py-14">
        <div className="grid gap-10 sm:grid-cols-[1.4fr_1fr_1fr]">
          <div>
            <p className="font-display text-lg text-ink">EIDOS</p>
            <p className="mt-3 max-w-sm text-sm leading-relaxed text-ink-muted">
              Execution Intelligence &amp; Dynamic Orchestration System — an execution-control architecture for
              validated, verifiable AI work.
            </p>
          </div>
          <div>
            <p className="text-xs font-medium tracking-wide text-ink-faint uppercase">Product</p>
            <ul className="mt-4 flex flex-col gap-2.5 text-sm">
              {PRODUCT_LINKS.map((link) => (
                <li key={link.href}>
                  <Link href={link.href} className="text-ink-muted transition-colors hover:text-ink">
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="text-xs font-medium tracking-wide text-ink-faint uppercase">Project</p>
            <ul className="mt-4 flex flex-col gap-2.5 text-sm">
              <li>
                <a href={GITHUB_URL} className="text-ink-muted transition-colors hover:text-ink" target="_blank" rel="noreferrer">
                  GitHub
                </a>
              </li>
              <li>
                <Link href="/login" className="text-ink-muted transition-colors hover:text-ink">
                  Sign in
                </Link>
              </li>
              <li>
                <Link href="/signup" className="text-ink-muted transition-colors hover:text-ink">
                  Create account
                </Link>
              </li>
            </ul>
          </div>
        </div>
        <div className="mt-12 flex flex-col gap-2 border-t border-border pt-6 text-xs text-ink-faint sm:flex-row sm:items-center sm:justify-between">
          <p>© 2026 EIDOS.</p>
          <p>Deterministic core. Bounded execution. Verified, not assumed.</p>
        </div>
      </div>
    </footer>
  );
}
