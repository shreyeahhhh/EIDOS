import Link from "next/link";

const GITHUB_URL = "https://github.com/shreyeahhhh/EIDOS---Execution-Intelligence-Dynamic-Orchestration-System";

const READING = [
  { href: "/#architecture", label: "The execution architecture" },
  { href: "/#how-it-works", label: "The Plan → Execute → Verify → Learn loop" },
  { href: "/#principles", label: "Engineering principles" },
];

export function BuildWithEidos() {
  return (
    <div className="grid gap-10 sm:grid-cols-[1fr_1fr]">
      <div>
        <h2 className="font-display text-2xl text-ink sm:text-3xl">Built as an engineering project, not a demo.</h2>
        <p className="mt-4 max-w-md text-sm leading-relaxed text-ink-muted">
          EIDOS is open on GitHub — the validator, the compiler, the runtime and the same source this page is served
          from.
        </p>
        <a
          href={GITHUB_URL}
          target="_blank"
          rel="noreferrer"
          className="mt-6 inline-flex items-center gap-2 text-sm font-medium text-accent hover:text-accent-strong"
        >
          View the source on GitHub →
        </a>
      </div>
      <div>
        <p className="text-xs font-medium tracking-wide text-ink-faint uppercase">On this page</p>
        <ul className="mt-4 flex flex-col gap-2.5 border-t border-border pt-4">
          {READING.map((item) => (
            <li key={item.href}>
              <Link href={item.href} className="text-sm text-ink-muted transition-colors hover:text-ink">
                {item.label}
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
