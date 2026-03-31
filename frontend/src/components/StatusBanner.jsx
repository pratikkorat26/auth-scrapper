export default function StatusBanner({ type, message, kicker }) {
  if (!message) {
    return null;
  }

  const resolvedKicker = kicker || (type === "info" ? "Deployment note" : "Request issue");

  return (
    <section className={`banner banner-${type}`} aria-live="polite">
      <div className="banner-kicker">{resolvedKicker}</div>
      <p>{message}</p>
    </section>
  );
}
