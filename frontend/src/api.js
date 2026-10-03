import clausesData from './mock/clauses.json';

/**
 * Simulates an API call to a backend that analyses legal text.
 * Replace the body of this function with a real fetch() when the backend is ready.
 * @param {string} input - Raw agreement text pasted by the user
 * @returns {Promise<{clauses: Array, summary: string}>}
 */
export async function simplify(input) {
  // Simulate network latency
  await new Promise((resolve) => setTimeout(resolve, 1800));

  // Mock: return all clauses regardless of input
  const high = clausesData.filter((c) => c.risk_level === 'high').length;
  const medium = clausesData.filter((c) => c.risk_level === 'medium').length;
  const low = clausesData.filter((c) => c.risk_level === 'low').length;

  return {
    clauses: clausesData,
    summary: `${high} high-risk, ${medium} medium-risk and ${low} low-risk clauses found.`,
    counts: { high, medium, low, total: clausesData.length },
  };
}
