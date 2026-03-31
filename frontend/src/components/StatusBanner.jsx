export default function StatusBanner({ type, message }) {
  if (!message) {
    return null;
  }

  return (
    <section className={`banner banner-${type}`} aria-live="polite">
      <div className="banner-kicker">Request issue</div>
      <p>{message}</p>
    </section>
  );
}
