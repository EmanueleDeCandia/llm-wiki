import katex from 'katex';
import 'katex/dist/katex.min.css';
import { marked } from 'marked';
import { useEffect, useRef, type MouseEvent as ReactMouseEvent } from 'react';

/**
 * Rendering Markdown della piattaforma:
 * - LaTeX $inline$ e $$display$$ via KaTeX (invariante §1.5)
 * - [[Wikilink]] e [[path|label]] come collegamenti navigabili
 * - tabelle, elenchi, codice
 */

const esc = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

export function renderMarkdown(md: string, opts?: { wikilinkClass?: string }): string {
  // 1) Estrai il LaTeX PRIMA del markdown (sennò _ e * vengono mangiati)
  const math: { display: boolean; expr: string }[] = [];
  let text = md.replace(/\$\$([\s\S]+?)\$\$/g, (_m, expr) => {
    math.push({ display: true, expr });
    return `\u0001MATH${math.length - 1}\u0001`;
  });
  text = text.replace(/\$([^\n$]+?)\$/g, (_m, expr) => {
    math.push({ display: false, expr });
    return `\u0001MATH${math.length - 1}\u0001`;
  });

  // 2) Wikilink → ancore HTML (il markdown li lascerebbe letterali)
  text = text.replace(
    /\[\[([^\[\]|\n]+?)(?:\|([^\[\]\n]+?))?\]\]/g,
    (_m, target, label) =>
      `<a class="${opts?.wikilinkClass ?? 'wikilink'}" data-wikilink="${esc(
        target,
      )}" data-label="${esc(label || target)}">${esc(label || target)}</a>`,
  );

  // 3) Markdown
  let html: string;
  try {
    html = marked.parse(text, { async: false, breaks: true, gfm: true }) as string;
  } catch {
    html = `<pre>${esc(text)}</pre>`;
  }

  // 4) Ripristina il LaTeX
  html = html.replace(/\u0001MATH(\d+)\u0001/g, (_m, i) => {
    const item = math[Number(i)];
    try {
      return katex.renderToString(item.expr, {
        displayMode: item.display,
        throwOnError: false,
        strict: false,
      });
    } catch {
      return `<code>${esc(item.expr)}</code>`;
    }
  });
  return html;
}

export function MathPreview({ markdown, onWikilink }: { markdown: string; onWikilink?: (target: string) => void }) {
  const ref = useRef<HTMLDivElement>(null);

  const html = renderMarkdown(markdown);
  // React non esegue gli eventi inline in dangerouslySetInnerHTML: delega qui.
  const handler = (e: ReactMouseEvent) => {
    const el = (e.target as HTMLElement).closest('a.wikilink');
    if (el && onWikilink) {
      e.preventDefault();
      onWikilink(el.getAttribute('data-wikilink') || '');
    }
  };

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const click = (e: Event) => {
      const el = (e.target as HTMLElement).closest('a.wikilink');
      if (el && onWikilink) {
        (e as MouseEvent).preventDefault();
        onWikilink(el.getAttribute('data-wikilink') || '');
      }
    };
    node.addEventListener('click', click);
    return () => node.removeEventListener('click', click);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [html, onWikilink]);

  return <div ref={ref} onClick={handler} className="md-preview" dangerouslySetInnerHTML={{ __html: html }} />;
}
