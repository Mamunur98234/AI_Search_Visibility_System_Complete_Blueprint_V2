/** Renders an external URL from crawled (untrusted) data. Only http(s) URLs become links. */
export function SafeLink({ url, children }: { url: string; children?: React.ReactNode }) {
  const ok = /^https?:\/\//i.test(url);
  if (!ok) return <span className="break">{children ?? url}</span>;
  return (
    <a href={url} target="_blank" rel="noopener noreferrer nofollow" className="break">
      {children ?? url}
    </a>
  );
}
