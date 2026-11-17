import type { Metadata } from "next";

export const metadata: Metadata = { title: "About AISVBot", robots: { index: true, follow: false } };

export default function BotPage() {
  return (
    <main className="centered">
      <article className="card auth-card">
        <h1>About AISVBot</h1>
        <p>
          AISVBot is the crawler of the AI Search Visibility platform. It only crawls websites whose owners have verified
          control of the domain in their workspace and requested a technical audit.
        </p>
        <ul>
          <li>Identifies itself with the user agent token <code>AISVBot</code>.</li>
          <li>Obeys robots.txt, including <code>User-agent: AISVBot</code> groups and <code>Crawl-delay</code>.</li>
          <li>Requests one page at a time per host, with a delay between requests and strict page/depth limits.</li>
          <li>Stays on the verified hostname, does not execute JavaScript, and does not submit forms or log in.</li>
        </ul>
        <p>To block it, add to your robots.txt:</p>
        <pre className="card small">User-agent: AISVBot{"\n"}Disallow: /</pre>
      </article>
    </main>
  );
}
