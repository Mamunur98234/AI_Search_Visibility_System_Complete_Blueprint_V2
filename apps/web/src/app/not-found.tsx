import Link from "next/link";

export default function NotFound() {
  return (
    <main className="centered">
      <div className="card auth-card">
        <h1>Page not found</h1>
        <p className="muted">The page you requested does not exist or you do not have access to it.</p>
        <Link href="/">Go to overview</Link>
      </div>
    </main>
  );
}
