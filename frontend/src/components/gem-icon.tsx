// Faceted amber gem used for the credits balance (flat, Sketch-style diamond).
export function GemIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 22" className={className} aria-hidden="true">
      <polygon points="6,1 18,1 23,8 1,8" fill="#FBBF24" />
      <polygon points="6,1 12,1 9,8 1,8" fill="#F59E0B" />
      <polygon points="12,1 18,1 23,8 15,8" fill="#FCD34D" />
      <polygon points="1,8 9,8 12,21" fill="#F59E0B" />
      <polygon points="9,8 15,8 12,21" fill="#FDBA3B" />
      <polygon points="15,8 23,8 12,21" fill="#EA7A0C" />
    </svg>
  );
}
