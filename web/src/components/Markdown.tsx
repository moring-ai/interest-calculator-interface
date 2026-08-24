import { Fragment, type ReactNode } from "react";

/**
 * Minimal Markdown renderer for agent replies.
 *
 * Deliberately not a full parser. The agent produces a narrow, predictable
 * subset -- headings, bold figures, and bullet lists -- and pulling in a
 * markdown library plus a sanitizer to render three constructs would be a lot
 * of dependency surface for text this constrained. Nothing here interprets
 * raw HTML, so model output cannot inject markup.
 */

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={i} className="tnum font-semibold" style={{ color: "var(--text)" }}>
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return (
        <code
          key={i}
          className="rounded px-1 py-0.5 text-[0.9em]"
          style={{ background: "var(--surface-2)", color: "var(--text)" }}
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}

export function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  const lines = text.split("\n");
  let bullets: string[] = [];
  let paragraph: string[] = [];

  const flushBullets = () => {
    if (!bullets.length) return;
    blocks.push(
      <ul key={`u${blocks.length}`} className="ml-1 space-y-1">
        {bullets.map((b, i) => (
          <li key={i} className="flex gap-2">
            <span aria-hidden style={{ color: "var(--text-faint)" }}>·</span>
            <span className="flex-1">{inline(b)}</span>
          </li>
        ))}
      </ul>,
    );
    bullets = [];
  };

  const flushParagraph = () => {
    if (!paragraph.length) return;
    blocks.push(
      <p key={`p${blocks.length}`} className="leading-relaxed">
        {inline(paragraph.join(" "))}
      </p>,
    );
    paragraph = [];
  };

  for (const raw of lines) {
    const line = raw.trimEnd();

    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      flushParagraph(); flushBullets();
      blocks.push(
        <h4
          key={`h${blocks.length}`}
          className="mt-1 text-[11px] font-semibold uppercase tracking-wide"
          style={{ color: "var(--text-faint)" }}
        >
          {inline(heading[2])}
        </h4>,
      );
      continue;
    }

    const bullet = line.match(/^\s*[-*+]\s+(.*)$/) ?? line.match(/^\s*\d+\.\s+(.*)$/);
    if (bullet) {
      flushParagraph();
      bullets.push(bullet[1]);
      continue;
    }

    if (!line.trim()) {
      flushParagraph(); flushBullets();
      continue;
    }

    flushBullets();
    paragraph.push(line);
  }
  flushParagraph();
  flushBullets();

  return <div className="space-y-2.5 text-sm" style={{ color: "var(--text)" }}>{blocks}</div>;
}
