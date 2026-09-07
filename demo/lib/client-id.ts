let fallbackSequence = 0;

/**
 * Browser-visible IDs also run on the Docker E2E hostname (`http://web`),
 * which is not a secure context and therefore does not expose
 * `crypto.randomUUID`.  Use the native UUID when available and a bounded,
 * collision-resistant local fallback for demo-only client identifiers.
 */
export function clientId(prefix = 'id'): string {
  const browserCrypto = globalThis.crypto;
  if (typeof browserCrypto?.randomUUID === 'function') {
    return `${prefix}-${browserCrypto.randomUUID()}`;
  }

  const sequence = fallbackSequence++;
  const timestamp = Date.now().toString(36);
  const randomValues = new Uint32Array(2);
  try {
    browserCrypto?.getRandomValues(randomValues);
  } catch {
    // The timestamp and process-local sequence remain sufficient for the
    // deterministic demo's local IDs when no browser entropy API exists.
  }
  const entropy = Array.from(randomValues)
    .map((value) => value.toString(36))
    .join('');
  return `${prefix}-${timestamp}-${sequence}-${entropy}`;
}
