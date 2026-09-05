import { useMutation } from "@tanstack/react-query";
import { api } from "../lib/api";

export default function AccountMenu({ user }) {
  const signOut = useMutation({
    mutationFn: api.signOut,
    // Reload rather than just clearing the query cache: it guarantees no
    // component keeps a copy of the previous user's squad or history.
    onSettled: () => window.location.reload(),
  });

  if (!user) return null;

  return (
    <div className="account-menu" title={user.email}>
      <span className="account-email">{user.email}</span>
      <button
        className="logout-link"
        onClick={() => signOut.mutate()}
        disabled={signOut.isPending}
      >
        Sign out
      </button>
    </div>
  );
}
