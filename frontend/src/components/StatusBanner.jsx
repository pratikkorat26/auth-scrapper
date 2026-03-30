export default function StatusBanner({ type, message }) {
  if (!message) {
    return null;
  }

  return <div className={`banner banner-${type}`}>{message}</div>;
}

