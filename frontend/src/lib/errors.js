// FPL's transfer endpoint reports why it rejected a transfer under keys like
// "non_form_errors", sometimes as bare strings and sometimes as { message }
// objects, nested a few levels deep. Flatten whatever shape arrives so the user
// sees the actual reason instead of a bare "Transfer rejected (400)".
export function readableError(message) {
  let parsed;
  try {
    parsed = JSON.parse(message);
  } catch {
    return message;
  }

  const detail = parsed?.detail ?? parsed;
  if (typeof detail === "string") return detail;

  const headline = detail?.message || "Transfer rejected";
  const notes = [];

  const label = (key) => (key === "non_form_errors" || key === "detail" ? "" : key);
  const note = (path, text) => notes.push(path ? `${path}: ${text}` : text);

  const walk = (node, path) => {
    if (node == null) return;
    if (typeof node === "string") {
      note(path, node);
    } else if (Array.isArray(node)) {
      node.forEach((item) => walk(item, path));
    } else if (typeof node === "object") {
      if (node.message) {
        note(path, node.message);
        return;
      }
      Object.entries(node).forEach(([key, value]) => walk(value, label(key)));
    }
  };
  walk(detail?.fpl_response, "");

  const unique = [...new Set(notes)];
  return unique.length ? `${headline} — ${unique.join("; ")}` : headline;
}
